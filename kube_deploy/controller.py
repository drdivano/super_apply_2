import time

from kube_deploy.kube import ResourceAlreadyExists, DeployTimeoutError, WaitTimeoutError
from kube_deploy.log import CONSOLE, DEBUG
from kube_deploy.options import Options
from kube_deploy.resources import RESOURCE_TYPES, supports_versions, Deployment, Pod
from kubernetes import client


# def owned_by_uid(doc, owner_uid):
#     return any(True for owner_ref in doc.metadata.owner_references
#                 if owner_ref.uid == owner_uid)


class NamespaceController:
    def __init__(self, namespace):
        self.namespace = namespace


    def delete_resources(self, resource_type, selector, propagation_policy='Background', grace_period=None):
        list_resp = resource_type.list(label_selector=selector, namespace=self.namespace)
        for item in list_resp.items:
            if not item.kind:
                item.kind = resource_type.kind
            resource = resource_type(item)
            resource.delete(propagation_policy=propagation_policy, grace_period=grace_period)


    def print_pod_errors(self, selector, seen_messages):
        api = client.CoreV1Api()
        response = api.list_namespaced_pod(namespace=self.namespace,
                                           label_selector=selector)
        for pod_doc in response.items:
            Pod(pod_doc).print_status(pod_doc, seen_messages)


    def wait_for_deployment(self, selector, timeout=None, min_ready_replicas=1):
        if timeout is None:
            timeout = Options.wait
        api = client.ExtensionsV1beta1Api()
        start_t = time.time()

        seen_messages = set()

        CONSOLE('#### Waiting for deployment(s) to start:', selector)
        while 1:
            rs = self._get_spawned_replica_set(selector)
            if rs:
                response = api.read_namespaced_replica_set_status(rs.metadata.name, namespace=self.namespace)
                if (response.status.ready_replicas or 0) >= min_ready_replicas:
                    return
                DEBUG('Waiting for %s: ready_replicas=%s' % (rs.metadata.name, response.status.ready_replicas))
                self.print_pod_errors(selector, seen_messages)

            if time.time() >= start_t + timeout:
                raise DeployTimeoutError(selector)
            time.sleep(1)

    def _get_pods(self, selector):
        api = client.CoreV1Api()
        response = api.list_namespaced_pod(namespace=self.namespace,
                                           label_selector=selector)
        return response.items[-1] if response.items else None

    def wait_for_pod(self, selector, timeout=None):
        if timeout is None:
            timeout = Options.wait
        api = client.CoreV1Api()
        start_t = time.time()
        seen_messages = set()

        CONSOLE('#### Waiting for pod to complete:', selector)
        while 1:
            pod = self._get_pods(selector)
            if pod:
                response = api.read_namespaced_pod_status(pod.metadata.name, namespace=self.namespace)
                if response.status.phase == 'Succeeded':
                    return
                DEBUG('Waiting for %s: phase=%s' % (pod.metadata.name, response.status.phase))
                self.print_pod_errors(selector, seen_messages)

            if time.time() >= start_t + timeout:
                raise WaitTimeoutError(selector)
            time.sleep(1)


    def _get_spawned_replica_set(self, selector):
        api = client.ExtensionsV1beta1Api()
        response = api.list_namespaced_replica_set(namespace=self.namespace,
                                                   label_selector=selector)
        return response.items[-1] if response.items else None


    def wait_until_deleted(self, resource_type, selector, timeout=120):
        start_t = time.time()
        printed = False
        while 1:
            resp = resource_type.list(namespace=self.namespace, label_selector=selector)
            if not resp.items:
                break
            if not printed:
                CONSOLE('Waiting for %s %s to terminate' % (resource_type.kind, selector))
                printed = True
            else:
                DEBUG('Waiting for %s %s to terminate' % (resource_type.kind, selector))
            if time.time() >= start_t + timeout:
                raise WaitTimeoutError(resource_type.kind, selector)
            time.sleep(1)
