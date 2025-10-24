from pgsn.dsl import *

a = string('a')
b = string('b')
c = string('c')
defaults = record({'a': boolean(True)})
self = variable('self')
v = lambda_abs(self, if_then_else(self(a))(self(b))(self(c)))
# attrs1 = inherit(defaults)(record_term.record({'value': get_value_term}))
attrs1 = record({'a': true})
cls = define_class(inherit=base_class, defaults=defaults, attributes=["a"], methods={})
test = string('test')


cls1 = define_class(inherit=cls, attributes=[])
cls2 = define_class(inherit=cls, attributes=['b'])
cls3 = define_class(inherit=cls2, attributes=['c'], methods={'v': v})


def test_class():
    assert isinstance(base_class.fully_eval(), PGSNClass)
    assert isinstance(cls.fully_eval(), PGSNClass)
    assert isinstance(cls1.fully_eval(), PGSNClass)
    assert isinstance(cls2.fully_eval(), PGSNClass)
    assert isinstance(cls3.fully_eval(), PGSNClass)
    assert cls.fully_eval().attributes() == {'a'}
    assert set(cls3.fully_eval().methods().keys()) == {'v'}


def test_subclass():
    assert isinstance(cls1.fully_eval(), PGSNClass)
    assert is_subclass(cls)(cls).fully_eval().value
    assert is_subclass(cls1)(cls).fully_eval().value
    assert not is_subclass(base_class)(cls).fully_eval().value


obj1 = cls({})
obj2 = cls({'a': False})
obj3 = cls({'b': 1})
obj4 = cls2({'b': 1})
obj5 = cls3({'b': 1, 'c':2})
obj6 = cls3({'a': False, 'b': 1, 'c':2})



def test_obj_instance():
    assert isinstance(obj1.fully_eval(), PGSNObject)
    assert isinstance(obj2.fully_eval(), PGSNObject)
    assert not isinstance(obj3.fully_eval(), PGSNObject)
    assert isinstance(obj4.fully_eval(), PGSNObject)
    assert isinstance(obj5.fully_eval(), PGSNObject)
    assert isinstance(obj6.fully_eval(), PGSNObject)
    assert is_instance(obj1)(cls).fully_eval().value
    assert not is_instance(obj1)(cls1).fully_eval().value


def test_obj_values():
    assert obj1(a).fully_eval().value
    assert not obj2(a).fully_eval().value
    assert obj4(a).fully_eval().value
    assert obj4(b).fully_eval().value == 1
    assert obj5(a).fully_eval().value
    assert obj5(b).fully_eval().value == 1
    assert obj5(c).fully_eval().value == 2
    assert obj5(a).fully_eval().value
    assert obj5(b).fully_eval().value == 1
    assert obj5(c).fully_eval().value == 2
    assert not obj6(a).fully_eval().value
    assert obj6(b).fully_eval().value == 1
    assert obj6(c).fully_eval().value == 2
    assert obj1.a.fully_eval().value


def test_obj_methods():
    assert obj5('v').fully_eval().value == 1
    assert obj6('v').fully_eval().value == 2
    assert obj5.v.fully_eval().value == 1
    assert obj6.v.fully_eval().value == 2
