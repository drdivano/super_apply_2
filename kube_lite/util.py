import base64
import json
import duck_object

def to_base64(s):
    return base64.standard_b64encode(s.encode('ascii')).decode()

def from_base64(s):
    return base64.standard_b64decode(s).decode()

def to_json(doc):
    doc = duck_object.as_primitive(doc)
    try:
        return json.dumps(doc).encode()
    except Exception:
        from kube_lite.log import CONSOLE
        CONSOLE('# error while processing doc:', repr(doc))
        raise

