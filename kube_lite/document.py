from duck_object import DuckObject

class Document(DuckObject):
    def __init__(self, d=None, **kwargs):
        if d is None:
            d = {}
        for k, v in d.items():
            d[k] = v
        for k, v in kwargs.items():
            d[k] = v
        super().__init__(d)


class Metadata(DuckObject):
    def __init__(self, d=None, **kwargs):
        if d is None:
            d = {}
        if 'labels' not in d:
            d['labels'] = {}
        if 'annotations' not in d:
            d['annotations'] = {}
        d.update(kwargs)
        super().__init__(d)
