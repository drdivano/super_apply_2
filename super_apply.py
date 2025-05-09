#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import subprocess
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(sys.argv[0]) + '/../lib/site-packages')
sys.path.insert(0, os.path.dirname(sys.argv[0]) + '/lib/site-packages')

from kubernetes.client.rest import ApiException
from kube_deploy.kube import init_kube_connection, get_namespace
from kube_deploy.controller import NamespaceController
from kube_deploy.log import setup_logging, CONSOLE, DEBUG, print_container_log
from kube_deploy.options import Options
from kube_deploy.resources import supports_versions, RESOURCE_TYPES, Pod

from dotdict import DotDict
import yaml

class SvnVersionError(Exception):
    pass

DOCKER_IMAGE_RE = re.compile(r'(.+)/([^/:@]+)([:@]..+)?')

Options.docker_image = None
Options.app_name = None
Options.resources = None
Options.force_version = None
Options.no_version = None
Options.overwrite = None
Options.replicas = None
Options.delete_old_versions = None
Options.set_annotation = []
Options.wait = None
Options.rename = True


def parse_cmd_line():
    parser = Options.parser
    parser.description = 'Deploy resources to Kubernetes'
    parser.add_argument('resources', nargs='+')

    parser.add_argument('--app-name', '-a', help='Set application name', required=True)

    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument('--no-version', action='store_true', help='Do not use resource versioning')
    version_group.add_argument('--set-version', metavar='VERSION', dest='force_version',
                               help='Set resource version to the supplied value')
    parser.add_argument('--overwrite', action='store_true', help='Replace existing resources')
    parser.add_argument('--replicas', type=int, default=1, metavar='N', help='Deploy this many replicas')
    parser.add_argument('--delete-old-versions', action='store_true')
    parser.add_argument('--set-annotation', '-A', metavar='KEY=VALUE', action='append',
                        help='Set annotation on Kubernetes resources')

    parser.add_argument('--namespace', '-n')
    parser.add_argument('--dry-run', action='store_true', help='Do not change Kubernetes objects')
    parser.add_argument('--wait', type=int, default=60, nargs='?', metavar='SECONDS',
                        help='Wait for deployment to have at least 1 ready pod')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--debug', '-d', type=int, default=0)

    parser.parse_args(namespace=Options)


def get_version(app, filename):
    if Options.no_version:
        version = None
    else:
        version = Options.force_version
    return version


def read_docs(app, filenames):
    docs = []
    for filename in filenames:
        file_version = get_version(app, filename)

        print('! file: %s\tversion: %s' % (filename, file_version))

        with open(filename) as f:
            for d in yaml.load_all(f):
                doc = DotDict(d)
                docs.append((file_version, doc))
    return docs


def index_resources(app, docs):
    annotations = dict(param.split('=', 1) for param in Options.set_annotation)
    for version, doc in docs:
        set_versions(doc, app, version)
        set_annotations(doc, annotations)
        if doc.kind == 'Deployment':
            set_annotations(doc.spec.template, annotations)
            app.index_deployment(doc)
        elif doc.kind == 'Services':
            app.index_service(doc)


def set_annotations(element, annotations):
    a = element.metadata.setdefault('annotations', DotDict())
    a.update(annotations)


def set_versions(doc, app, version):
    if 'version' in doc.metadata.get('labels', {}):
        doc.metadata['labels'].version = version

    return doc


def set_replicas(doc, replicas):
    if doc.kind == 'Deployment':
        doc.spec.replicas = replicas

def set_container_env(doc, env_var_name, value):
    for container in doc.spec.template.spec.containers + \
                     doc.spec.template.spec.get('initContainers', []):
        for env_var in container.get('env', []):
            if env_var.name == env_var_name:
                env_var.value = value


def get_selector(resource):
    update_id = resource.metadata.labels['update-id']
    app_name = resource.metadata.labels['app']
    return 'app=%s,update-id=%s' % (app_name, update_id)


class AppData:
    def __init__(self, options):
        self.deployments = {}
        self.services = {}
        self.app_name = options.app_name

    def index_deployment(self, doc):
        self.deployments[doc.metadata.name] = doc

    def index_service(self, doc):
        self.services[doc.metadata.name] = doc


    def link_deployments(self, service_doc):
        # привязываем deployment к service
        service_name = service_doc.metadata.name
        app_name = service_doc.metadata.labels['app']
        for deployment in self.deployments.values():
            if deployment.metadata.labels.get('app') == app_name:
                if supports_versions(deployment):
                    version = deployment.metadata.labels.get('version')
                    service_doc.spec.selector.version = version
                    CONSOLE('# Service %s: set labels.version = %s' % (service_name, version))
                else:
                    # приложение может не поддерживать версии
                    CONSOLE('# Service %s: no labels.version in resource definition' % service_name)
                    service_doc.spec.selector.pop('version', None)


def delete_old_versions(app, docs, site):
    for version, doc in docs:
        if version and supports_versions(doc):
            selector = 'app=%s,version!=%s' % (app.app_name, version)
            DEBUG('delete_old_versions', doc.kind, selector)
            site.delete_resources(RESOURCE_TYPES[doc.kind], selector)

def process_pod_results(pod):
    container_name = pod.spec.containers[0].name
    terminated = pod.wait_for_container(container_name, 'terminated', expected_exit_code=0, max_restarts=1)
    DEBUG('rc=', terminated.exit_code)
    log = pod.read_log(container_name)
    if terminated.exit_code == 0:
        print_container_log(log, pod.name, container_name)
        pod.delete()
    return terminated.exit_code


APPLY_ORDER = {'ConfigMap': 1,
               None: 10,
               'Deployment': 20,
               'Service': 30,}


def main():
    init_kube_connection()

    parse_cmd_line()
    setup_logging()
    namespace = get_namespace()

    site = NamespaceController(namespace)
    app = AppData(Options)

    docs = read_docs(app, Options.resources)

    index_resources(app, docs)

    update_id = str(uuid.uuid1())

    for version, doc in sorted(docs, key=lambda row: APPLY_ORDER.get(row[1].kind) or APPLY_ORDER[None]):
        doc.metadata.namespace = namespace
        resource_type = RESOURCE_TYPES[doc.kind]
        resource = resource_type(doc)

        if doc.kind == 'Deployment':
            doc.metadata.setdefault('labels', DotDict())['update-id'] = update_id
            doc.spec.template.metadata.setdefault('labels', DotDict())['update-id'] = update_id
            set_replicas(doc, Options.replicas)

        elif doc.kind == 'Pod':
            doc.metadata.setdefault('labels', DotDict())['update-id'] = update_id
            if Options.overwrite:
                #from kubernetes import client
                #api = client.CoreV1Api()
                #pod_doc = api.read_namespaced_pod(name=doc.metadata.name, namespace=site.namespace)
                try:
                    Pod(doc).delete()
                except ApiException as e:
                    if e.status != 404:
                        raise

        elif doc.kind == 'Service':
            app.link_deployments(doc)

        resource.apply()

        if doc.kind == 'Deployment':
            if Options.wait and not Options.dry_run:
                site.wait_for_deployment(get_selector(resource))

        elif doc.kind == 'Pod':
            if Options.wait and not Options.dry_run:
                process_pod_results(Pod(doc))

    if Options.delete_old_versions:
        delete_old_versions(app, docs, site)



if __name__ == '__main__':
    main()
