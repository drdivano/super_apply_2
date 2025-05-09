from kube_lite.document import Document

def test_assign_subelement():
    d = Document()
    d.status.terminated = 'xxx'

    assert d == {'status': {'terminated': 'xxx'}}

def test_get_subelement():
    d = Document()
    v = d.level1.level2.level3
    assert v == None
    print(v)
    assert d.as_primitive() == {}

    d.level1.elem2 = 1
    assert d.as_primitive() == {'level1': {'elem2': 1}}

    v = d.level1.level2.level3
    assert not v
