import time

from kube_lite import KubernetesApi, NotFoundError
from kube_lite.log import CONSOLE, DEBUG

class WaitTimeoutError(Exception):
    pass

def wait_until_deleted(kind, name, namespace, timeout=120):
    start_t = time.time()
    printed = False
    while 1:
        try:
            KubernetesApi.get(kind, name=name, namespace=namespace)
        except NotFoundError:
            break
        if not printed:
            CONSOLE('#### Waiting until server deletes %s %s/%s' % (kind, namespace, name))
            printed = True
        else:
            DEBUG('Waiting until server deletes %s %s/%s ' % (kind, namespace, name))
        if time.time() >= start_t + timeout:
            raise WaitTimeoutError(kind, name)
        time.sleep(1)
