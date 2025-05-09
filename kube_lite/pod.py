import time
from kube_lite.direct_api import KubernetesApi, NotFoundError
from kube_lite.log import DEBUG, CONSOLE, indent_multiline
from kube_lite.options import Options
from kube_lite.resource import Reference


def _print_state(pod_name, c_status, state_name, state, seen_messages):
    container_id = state.containerID or None
    reason = state.reason or None
    message = state.message or None
    started_at = state.startedAt or None
    finished_at = state.finishedAt or None
    if state_name == 'terminated' and started_at is None:
        return
    seen_key = (container_id, state_name, reason, message, started_at, finished_at)
    if seen_key not in seen_messages:
        DEBUG(state)
        status_text = state_name
        if reason:
            status_text += ' // ' + reason
        CONSOLE('# Container %s/%s: %s' % (pod_name, c_status.name, status_text))
        if message:
            CONSOLE(indent_multiline(message))
        seen_messages.add(seen_key)


def print_status(doc, seen_messages):
    for c_status in list(doc.status.containerStatuses or []) + \
                    list(doc.status.initContainerStatuses or []):
        terminated = c_status.lastState.terminated
        if terminated:
            state = terminated
            _print_state(doc.metadata.name, c_status, 'terminated', state, seen_messages)

        for state_name, state in c_status.state.items():
            if state:
                _print_state(doc.metadata.name, c_status, state_name, state, seen_messages)


class PodReference(Reference):
    kind = 'pod'

    def wait(self, container_name, expected_state='terminated', timeout=None):
        start_t = time.time()
        if timeout is None:
            timeout = Options.wait

        seen_messages = set()
        CONSOLE('#### Waiting for container %s/%s' % (self.name, container_name))
        while 1:
            pod_doc = KubernetesApi.get('pod', self.name, namespace=self.namespace)
            print_status(pod_doc, seen_messages)
            for cs in pod_doc.status.containerStatuses or []:
                if cs.name == container_name:
                    DEBUG('state=%s' % cs.state)
                    container_state = getattr(cs.state, expected_state, False)
                    if container_state:
                        return container_state

            if time.time() >= start_t + timeout:
                from kube_deploy.controller import WaitTimeoutError
                raise WaitTimeoutError(self.name)
            time.sleep(1)

    def read_log(self, container_name, **params):
        return KubernetesApi.read_pod_log(self.name, namespace=self.namespace, container=container_name, **params)
