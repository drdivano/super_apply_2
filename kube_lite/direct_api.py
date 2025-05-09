from urllib.parse import urlparse

import requests
import json

from kube_lite.options import Options
from kube_lite.util import to_json

from .log import DEBUG
from .api_resources import KINDS
from .document import Document

TOKEN_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/token'


class KubernetesError(Exception):
    def __init__(self, method, path, response):
        super().__init__()
        self.method = method
        self.path = path
        self.response = response

    def __str__(self):
        try:
            result = ['%s %s status_code=%s reason=%s' % (self.method, self.path, self.response.status_code, self.response.reason)]
            if self.response.headers.get('content-type') == 'application/json':
                d = json.loads(self.response.text)
                result.append('message=' + d.get('message', ''))
            else:
                result.append('text=%s' % self.response.text)
            return ' '.join(result)
        except Exception:
            import traceback
            traceback.print_exc()
            raise

class NotFoundError(KubernetesError):
    pass


class KubernetesApi(object):
    API_HOST = 'kubernetes.default.svc'
    API_PORT = 443
    TOKEN = None
    CA_CERT_PATH = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'
    CLIENT_CERT = None

    @classmethod
    def get_api_path(cls, doc, name=None):
        resource_info = KINDS[doc.kind]
        if resource_info.namespaced:
            path = 'namespaces/%s/%s' % (doc.metadata.namespace, resource_info.name)
        else:
            path = '%s' % (resource_info.name)
        if name:
            path = '%s/%s' % (path, name)
        return path

    @classmethod
    def init(cls, host=None, port=None, token=None):
        if host:
            cls.API_HOST = host
        if port:
            cls.API_PORT= port
        if token:
            cls.TOKEN = token
        if token is None:
            with open(TOKEN_FILE) as f:
                cls.TOKEN = 'Bearer ' + f.read()

    @classmethod
    def init_from_kubeconfig(cls):
        import kubernetes
        from kubernetes.client.configuration import configuration
        kubernetes.config.load_kube_config()
        cls.CA_CERT_PATH = configuration.ssl_ca_cert
        cls.CLIENT_CERT = (configuration.cert_file, configuration.key_file)
        host_uo = urlparse(configuration.host)
        cls.API_HOST = host_uo.hostname
        cls.API_PORT = host_uo.port
        cls.TOKEN = configuration.get_api_key_with_prefix('authorization')

    @classmethod
    def call(cls, method, path, data=None, api=None, params=None, dry_run=False):
        if data:
            DEBUG('--- Request:', level=2)
            DEBUG(data, level=2)

        headers = {'Content-Type': 'application/json'}
        if cls.TOKEN:
            headers['Authorization'] = cls.TOKEN

        if not api:
            api = 'api/v1'
        elif '/' not in api:
            api = 'api/' + api
        else:
            api = 'apis/' + api
        path = '/%s/%s' % (api, path)
        url = 'https://%s:%s%s' % (cls.API_HOST, cls.API_PORT, path)
        request = requests.Request(url=url, method=method, headers=headers, data=data, params=params)
        session = requests.Session()

        if dry_run:
            return requests.Response()
        else:
            r = session.send(request.prepare(), verify=cls.CA_CERT_PATH, cert=cls.CLIENT_CERT)

        DEBUG('--- Response:', level=2)
        DEBUG(r.text, level=2)

        if 200 <= r.status_code <= 299:
            return r
        else:
            DEBUG('Kubernetes API error: %s (%s): %s' % (path, r.status_code, r.text))
            if r.status_code == 404:
                error_cls = NotFoundError
            else:
                error_cls = KubernetesError
            raise(error_cls(method=method, path=path, response=r))


    @classmethod
    def get(cls, kind, name=None, namespace=None, api=None, params=None):
        k = KINDS[kind.lower()]
        path = k.name
        if namespace:
            path = 'namespaces/%s/%s' % (namespace, path)
        if name:
            path += '/' + name
        r = cls.call('GET', path, api=api, params=params)
        return Document(json.loads(r.text))

    @classmethod
    def replace(cls, doc: Document):
        path = cls.get_api_path(doc, name=doc.metadata.name)
        api = doc.apiVersion
        data = to_json(doc)
        r = cls.call('PUT', path, data=data, api=api, dry_run=Options.dry_run)
        doc = Document(json.loads(r.text))

        return doc

    @classmethod
    def create(cls, doc: Document):
        path = cls.get_api_path(doc)
        api = doc.apiVersion
        data = to_json(doc)
        r = cls.call('POST', path, data=data, api=api, dry_run=Options.dry_run)
        doc = Document(json.loads(r.text))
        return doc

    @classmethod
    def delete(cls, kind, name, namespace=None, api=None,
               grace_period_seconds=None, orphan_dependents=None, propagation_policy=None):
        query_params = {}

        if grace_period_seconds is not None:
            query_params['gracePeriodSeconds'] = grace_period_seconds
        if orphan_dependents is not None:
            query_params['orphanDependents'] = orphan_dependents
        if propagation_policy is not None:
            query_params['propagationPolicy'] = propagation_policy

        k = KINDS[kind.lower()]
        path = k.name
        if namespace:
            path = 'namespaces/%s/%s' % (namespace, path)
        if name:
            path += '/' + name

        if not Options.dry_run:
            cls.call('DELETE', path, api=api, params=query_params, dry_run=Options.dry_run)

    @classmethod
    def read_pod_log(cls, name, namespace, container=None, tail_lines=None):
        query_params = {}
        if container:
            query_params['container'] = container
        if tail_lines:
            query_params['tailLines'] = tail_lines
        # see kubernetes/client/apis/core_v1_api.py
        # if 'follow' in params:
        #     query_params['follow'] = params['follow']
        # if 'limit_bytes' in params:
        #     query_params['limitBytes'] = params['limit_bytes']
        # if 'pretty' in params:
        #     query_params['pretty'] = params['pretty']
        # if 'previous' in params:
        #     query_params['previous'] = params['previous']
        # if 'since_seconds' in params:
        #     query_params['sinceSeconds'] = params['since_seconds']
        # if 'timestamps' in params:
        #     query_params['timestamps'] = params['timestamps']

        path = 'namespaces/%s/pods/%s/log' % (namespace, name)
        r = cls.call('GET', path, params=query_params)
        return r.text
