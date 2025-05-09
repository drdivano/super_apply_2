# -*- coding: utf-8 -*-
import pprint
import time
from kubernetes import client
from kubernetes.client import CoreV1Api
from kube_deploy.log import CONSOLE, DEBUG, indent_multiline
from kube_deploy.options import Options
from kube_deploy.kube import ResourceAlreadyExists


def supports_versions(doc):
    if doc.kind == 'Service':
        return False
    if Options.force_version:
        return True
    if Options.no_version:
        return False
    return bool(doc.metadata.labels and doc.metadata.labels.get('version'))


class Resource:
    kind = NotImplemented
    api = NotImplemented
    _list = NotImplemented
    _read = NotImplemented
    _patch = NotImplemented
    _create = NotImplemented
    _delete = NotImplemented
    
    def __init__(self, doc):
        self.api = self.api()
        self.doc = doc

    @property
    def namespace(self):
        return self.doc.metadata.namespace

    @property
    def name(self):
        return self.doc.metadata.name

    @name.setter
    def name(self, value):
        self.doc.metadata.name = value


    @property
    def metadata(self):
        return self.doc.metadata

    @property
    def spec(self):
        return self.doc.spec

    @classmethod
    def read(cls, namespace, name, **kwargs):
        resp = cls._read(cls.api(), name=name, namespace=namespace, **kwargs)
        DEBUG(resp, level=2)
        return resp

    @classmethod
    def list(cls, namespace, **kwargs):
        resp = cls._list(cls.api(), namespace=namespace, **kwargs)
        DEBUG(resp, level=2)
        return resp

    def patch(self, **kwargs):
        if Options.dry_run:
            return {}
        cls = self.__class__
        old = cls._read(cls.api(), name=self.name, namespace=self.namespace, **kwargs)
        new = cls._patch(self.api, name=self.name, body=self.doc, namespace=self.namespace, **kwargs)
        DEBUG(new, level=2)
        if new.metadata.resource_version == old.metadata.resource_version:
            CONSOLE('# %s %s not modified' % (self.doc.kind, self.name))
        else:
            CONSOLE('# %s %s updated' % (self.doc.kind, self.name))
        return new

    def create(self, **kwargs):
        if Options.dry_run:
            return {}
        cls = self.__class__
        resp = cls._create(self.api, body=self.doc, namespace=self.namespace, **kwargs)
        DEBUG(resp, level=2)
        CONSOLE('# %s %s created' % (self.doc.kind, self.name))
        return resp

    def _delete_options(self, propagation_policy, grace_period_seconds):
        kwargs = {'body': client.V1DeleteOptions(propagation_policy=propagation_policy,
                                                 grace_period_seconds=grace_period_seconds)}
        return kwargs

    def delete(self, propagation_policy=None, grace_period=None, **kwargs):
        if Options.dry_run:
            return {}
        cls = self.__class__
        kwargs.update(self._delete_options(propagation_policy, grace_period))
        resp = cls._delete(self.api, name=self.name, namespace=self.namespace, **kwargs)
        DEBUG(resp, level=2)
        CONSOLE('# %s %s deleted' % (self.doc.kind, self.name or kwargs.get('label_selector')))
        return resp

    def apply(self):
        if Options.debug >= 2:
            doc = self.doc
            DEBUG('---')
            DEBUG(pprint.pformat(doc))
        self._apply_resource()

    @classmethod
    def _read_resource_if_exists(cls, namespace, name):
        try:
            return cls.read(namespace=namespace, name=name)
        except client.rest.ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def _apply_resource(self):
        resource_doc = self._read_resource_if_exists(self.namespace, self.name)
        if resource_doc is not None:
            # если ресурс - не версионный, то без перезаписи обновить его невозможно
            if supports_versions(resource_doc) and not Options.overwrite:
                raise ResourceAlreadyExists(self.name)
            self.metadata.uid = resource_doc.metadata.uid
            if not Options.dry_run:
                self.patch()
        else:
            if not Options.dry_run:
                resp = self.create()
                self.metadata.uid = resp.metadata.uid


class Pod(Resource):
    kind = 'Pod'
    api = client.CoreV1Api

    _list = api.list_namespaced_pod
    _read = api.read_namespaced_pod
    _patch = api.patch_namespaced_pod
    _create = api.create_namespaced_pod
    _delete = api.delete_namespaced_pod

    def _print_state(self, pod_name, c_status, state_name, state, seen_messages):
        reason = state.get('reason')
        message = state.get('message')
        started_at = state.get('started_at')
        finished_at = state.get('finished_at')
        restart_count = state.get('restart_count')
        if state_name == 'terminated' and started_at is None:
            return
        status_change_key = (c_status.container_id, state_name, reason)
        message_key = (c_status.container_id, message)
        
        if status_change_key not in seen_messages:
            DEBUG(state)
            status_text = state_name
            if reason:
                status_text += ' // ' + reason
            CONSOLE('# Container %s/%s: %s' % (pod_name, c_status.name, status_text))
            seen_messages.add(status_change_key)
            
        if message and message_key not in seen_messages:
            CONSOLE(indent_multiline(message))
            seen_messages.add(message_key)
            
    def print_status(self, doc, seen_messages):
        for c_status in (doc.status.container_statuses or []) + (doc.status.init_container_statuses or []):

            if getattr(c_status.last_state, 'terminated', None):
                state = c_status.last_state.terminated
                self._print_state(doc.metadata.name, c_status, 'terminated',
                                  state and state.to_dict(), seen_messages)

            for state_name, state in c_status.state.to_dict().items():
                if state:
                    self._print_state(doc.metadata.name, c_status, state_name, state, seen_messages)


    def wait_for_container(self, container_name, expected_state, expected_exit_code=None, max_restarts=None, timeout=None):
        start_t = time.time()
        if timeout is None:
            timeout = Options.wait

        seen_messages = set()
        CONSOLE('#### Waiting for container %s/%s' % (self.name, container_name))
        while 1:
            pod_doc = CoreV1Api().read_namespaced_pod(name=self.name, namespace=self.namespace)
            self.print_status(pod_doc, seen_messages)
            for cs in pod_doc.status.container_statuses or []:
                if cs.name == container_name:
                    if max_restarts is not None and cs.restart_count >= max_restarts:
                        CONSOLE('#### Abort due to pod restart count: %s' % cs.restart_count)
                        return getattr(cs.state, expected_state)
                    if getattr(cs.state, expected_state, False):
                        if expected_exit_code is None or expected_exit_code == getattr(cs.state, expected_state).exit_code:
                            return getattr(cs.state, expected_state)

            if time.time() >= start_t + timeout:
                from kube_deploy.controller import WaitTimeoutError
                raise WaitTimeoutError(self.name)
            time.sleep(1)


    def read_log(self, container_name):
        return CoreV1Api().read_namespaced_pod_log(self.name, namespace=self.namespace, container=container_name)


class Deployment(Resource):
    kind = 'Deployment'
    api = client.ExtensionsV1beta1Api
    _list = api.list_namespaced_deployment
    _read = api.read_namespaced_deployment
    _patch = api.patch_namespaced_deployment
    _create = api.create_namespaced_deployment
    _delete = api.delete_namespaced_deployment


class ConfigMap(Resource):
    kind = 'ConfigMap'
    api = client.CoreV1Api
    _list = api.list_namespaced_config_map
    _read = api.read_namespaced_config_map
    _patch = api.patch_namespaced_config_map
    _create = api.create_namespaced_config_map
    _delete = api.delete_namespaced_config_map


class Service(Resource):
    kind = 'Service'
    api = client.CoreV1Api
    _list = api.list_namespaced_service
    _read = api.read_namespaced_service
    _patch = api.patch_namespaced_service
    _create = api.create_namespaced_service
    _delete = api.delete_namespaced_service

    def _delete_options(self, *args, **kwargs):
        return {}


RESOURCE_TYPES = {name: cls for name, cls in globals().items()
                  if isinstance(cls, type) and issubclass(cls, Resource) and cls is not Resource}
