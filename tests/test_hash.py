"""A term can be hashed, and hashes as it compares.

Records, classes and objects hold plain dicts and sets. They are never changed
once the term is built -- each is copied when the term is made, and every
accessor hands out a copy -- which is what makes hashing them sound. The tests
below check that terms equal as they compare hash equal, and that nothing an
accessor hands out, or a caller keeps, reaches back into a term.
"""

from pgsn import pgsn_term
from pgsn.dsl import *

_self = variable('self')
_class = pgsn_term.PGSNClass.named(name="C", attributes={'a'},
                                   defaults={'a': integer(1)},
                                   methods={'m': lambda_abs(_self, _self('a'))})


def test_records_equal_whatever_the_order_hash_equal():
    r1 = record({'a': integer(1), 'b': integer(2)})
    r2 = record({'b': integer(2), 'a': integer(1)})
    assert r1 == r2
    assert hash(r1) == hash(r2)


def test_terms_holding_records_classes_and_objects_hash():
    obj = _class({}).fully_eval()
    terms = {record({'a': integer(1)}), list_term((record({}),)), base_class, _class, obj}
    assert len(terms) == 5


def test_a_record_does_not_share_the_dict_it_was_built_from():
    d = {'a': integer(1)}
    r = record(d)
    before = hash(r)
    d['b'] = integer(2)
    assert r == record({'a': integer(1)})
    assert hash(r) == before


def test_what_an_accessor_hands_out_is_a_copy():
    r = record({'a': integer(1)})
    r.attributes()['b'] = integer(2)
    assert r == record({'a': integer(1)})
    _class.attributes().add('x')
    _class.defaults()['x'] = integer(0)
    _class.methods()['x'] = integer(0)
    assert 'x' not in _class.attributes()
    assert 'x' not in _class.defaults()
    assert 'x' not in _class.methods()
