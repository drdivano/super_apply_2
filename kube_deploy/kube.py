# -*- coding: utf-8 -*-
import os
import sys
import urllib3

from kubernetes import config

from kube_deploy.options import Options
from kubernetes.config import list_kube_config_contexts

DEFAULT_KUBE_CONFIG = os.environ['HOME'] + '/.kube/config'
#TOKEN_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/token'
NAMESPACE_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'


class ResourceAlreadyExists(Exception):
    pass

class DeployTimeoutError(Exception):
    pass

class WaitTimeoutError(Exception):
    pass


def init_kube_connection():
    if 'KUBECONFIG' in os.environ:
        config.load_kube_config(os.environ['KUBECONFIG'])
    elif os.path.exists(DEFAULT_KUBE_CONFIG):
        config.load_kube_config(DEFAULT_KUBE_CONFIG)
    else:
        Options.parser.error('Kubernetes configuration not found in ~/.kube')
        # api_key = open(TOKEN_FILE).read()
        # kube_host = 'https://%(KUBERNETES_SERVICE_HOST)s:%(KUBERNETES_SERVICE_PORT)s' % os.environ
        #
        # kubernetes.client.configuration.api_key['authorization'] = api_key
        # kubernetes.client.configuration.host = kube_host
        # #kubernetes.client.configuration.verify_ssl = False
        # kubernetes.client.configuration.api_key_prefix['authorization'] = 'Bearer'
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_namespace():

    if Options.namespace:
        namespace = Options.namespace
    elif os.path.exists(NAMESPACE_FILE):
        with open(NAMESPACE_FILE) as f:
            namespace = f.read()
    else:
        __contexts, current_context = list_kube_config_contexts()
        namespace = current_context['context']['namespace']

    if not namespace:
        print('Unable to determine namespace from Kubernetes API. Use --namespace option.', file=sys.stderr)
        sys.exit(1)

    return namespace
