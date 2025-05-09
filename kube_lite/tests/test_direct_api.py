import os
import pytest
from kube_lite.direct_api import KubernetesApi
from kube_lite.api_resources import parse_api_resources
from kube_lite.document import Document
from kube_lite.pod import PodReference

NAMESPACE = 'unittest'

# не вызывается из pytest, нужно разобраться
#@pytest.fixture(scope="session")
def init_kube():
    KubernetesApi.init_from_kubeconfig()
    __dirname = os.path.dirname(__file__)
    os.system('kubectl apply -f %s' % __dirname)

init_kube()

## kubectl get secrets test-token-xxxxxxx -o jsonpath={..token} | base64 -d > token.txt
#
# import base64
# import json
# import subprocess
#
# def _init_using_token():
#     text = subprocess.check_output(['kubectl', '-n', 'default', '-o', 'json', 'get', 'secrets'])
#     doc = json.loads(text)
#     for secret in doc['items']:
#         if secret['metadata']['name'].startswith('default-token-'):
#             ca_cert = base64.decodebytes(secret['data']['ca.crt'].encode())
#             token = base64.decodebytes(secret['data']['token'].encode())
#             open('ca.crt', 'wb').write(ca_cert)
#             open('token.txt', 'wb').write(token)
#
#     KubernetesApi.CA_CERT_PATH = 'ca.crt'
#     KubernetesApi.init(host='192.168.11.61', port=6443, token=open('token.txt').read())


def test_list():
    response = KubernetesApi.get('configmap', namespace=NAMESPACE)
    print('\nconfigmaps:')
    for item in response['items']:
        print('  ', item.metadata.name)


def test_replace_configmap():
    doc = Document()
    doc.apiVersion = 'v1'
    doc.kind = 'ConfigMap'
    doc.metadata = Document(name='test',
                            namespace=NAMESPACE)
    doc.data = Document(key='value999')
    response = KubernetesApi.replace(doc)
    print(response)

def test_parse_api_resources():
    text = """\
NAME                              SHORTNAMES         APIGROUP                       NAMESPACED   KIND                             VERBS
bindings                                                                            true         Binding                          [create]
componentstatuses                 cs                                                false        ComponentStatus                  [get list]
configmaps                        cm                                                true         ConfigMap                        [create delete deletecollection get list patch update watch]
"""
    parsed = parse_api_resources(text)
    print(list(parsed))

def test_init_from_kubeconfig():
    KubernetesApi.init_from_kubeconfig()
    print('### token', KubernetesApi.TOKEN)
    response = KubernetesApi.get('node')
    print('\nnodes:')
    for item in response['items']:
        print('  ', item.metadata.name)

def test_pod_logs():
    pod = PodReference(name='test-pod-log', namespace=NAMESPACE)
    text = pod.read_log('test', tail_lines=10)
    print(repr(text))

def test_pod_create_delete():
    pod_doc = Document({
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "test",
            "namespace": NAMESPACE
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "test",
                    "image": "busybox:1",
                    "command": [
                        "echo",
                        "hello123"
                    ]
                }
            ]
        }
    })
    KubernetesApi.create(pod_doc)
    pod = PodReference(name='test', namespace=NAMESPACE)
    from kube_lite.options import Options
    Options.verbose = 1
    Options.debug = 0
    pod.wait('test')
    KubernetesApi.delete('pod', 'test', namespace=NAMESPACE)
