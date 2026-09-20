import pgsn
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


def test_subtype():
    """Structural: the labels decide, not where a class came from."""
    assert is_subtype(cls)(cls).fully_eval().value
    assert is_subtype(cls1)(cls).fully_eval().value
    assert is_subtype(cls2)(cls).fully_eval().value
    assert not is_subtype(cls)(cls2).fully_eval().value
    assert is_subtype(cls3)(cls2).fully_eval().value
    # cls3 declares a method, so nothing lacking it covers cls3.
    assert not is_subtype(cls2)(cls3).fully_eval().value
    # A type that demands nothing is satisfied by everything, itself included.
    # The inheritance-walking predicate this replaces answered False for
    # base_class in every direction, its own reflexive case among them.
    assert is_subtype(cls)(base_class).fully_eval().value
    assert is_subtype(base_class)(base_class).fully_eval().value


def test_a_subclass_may_default_an_inherited_attribute():
    """The invariants `DefineClass` checks are about what a definition adds.
    Giving an attribute declared by the parent a new default adds no
    attribute name of its own, and is allowed.
    """
    sub = define_class(inherit=cls, defaults=record({'a': false}))
    assert isinstance(sub.fully_eval(), PGSNClass)
    assert sub.fully_eval().attributes() == {'a'}
    assert not sub({}).fully_eval().attributes()['a'].value


def test_subtype_ignores_inheritance():
    """A class that inherits nothing from `cls` is still a subtype of it as
    long as it declares the same labels. That is the whole point of the
    change: `inherit` records where a class came from, not what it satisfies.
    """
    twin = define_class(inherit=base_class, defaults=defaults,
                        attributes=["a"], methods={})
    assert is_subtype(twin)(cls).fully_eval().value
    assert is_subtype(cls)(twin).fully_eval().value


def test_subtype_sees_past_unevaluated_defaults():
    """`goal_class` defaults `support` to an application, which the previous
    predicate could not compare, so it answered False for every goal. Labels
    are readable without reducing anything.
    """
    g = pgsn.goal(description="g", support=pgsn.undeveloped)
    assert is_subtype(type_of(g))(pgsn.goal_class).fully_eval().value


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
    assert isinstance(type_of(obj1).fully_eval(), PGSNClass)
    assert is_subtype(type_of(obj1))(cls).fully_eval().value


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
