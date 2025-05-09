from kube_lite.util import from_base64, to_base64

def test_b64():
    assert to_base64('123') == 'MTIz'
    assert '\n' not in to_base64('x' * 80)


def test_decode_b64():
    assert from_base64('MTIz') == '123'


