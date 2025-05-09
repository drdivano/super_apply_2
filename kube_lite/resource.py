from kube_lite.log import CONSOLE, DEBUG
from kube_lite import KubernetesApi, Options, NotFoundError
from kube_lite.wait import wait_until_deleted
from kube_lite.document import Document

class Reference:
    kind = NotImplemented
    def __init__(self, name: str, namespace: str):
        self.name = name
        self.namespace = namespace

    def delete(self, wait=True, ignore_not_found=False, **params):
        try:
            KubernetesApi.delete('pod', self.name, namespace=self.namespace, **params)
        except NotFoundError:
            if not ignore_not_found:
                raise
        CONSOLE('#### Deleted %s %s/%s' % (self.kind, self.namespace, self.name))
        if wait:
            self.wait_until_deleted()

    def wait_until_deleted(self, timeout: int = None):
        wait_until_deleted('pod', self.name, namespace=self.namespace, timeout=timeout or Options.wait)

    def read(self):
        doc = KubernetesApi.get(self.kind, self.name, namespace=self.namespace)
        return Document(doc)


class Resource:
    kind = NotImplemented

    def __init__(self, doc: Document):
        self.api = self.api()
        self.doc = doc

    @property
    def namespace(self):
        return self.doc.metadata.namespace

    @property
    def name(self):
        return self.doc.metadata.name

    @name.setter
    def name(self, value: str):
        self.doc.metadata.name = value

    @property
    def metadata(self):
        return self.doc.metadata
