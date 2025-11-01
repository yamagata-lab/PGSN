from pgsn.dsl import *
from pgsn import pgsn_term


def test_list():
    c = constant('c')
    d = constant('d')
    t = cons(c)(empty)
    t1 = head(t)
    t2 = cons(d)(t)
    t3 = tail(t2)
    assert t.fully_eval().terms[0] == c.fully_eval()
    assert t1.fully_eval() == c.fully_eval()
    assert t2.fully_eval().terms == (d.remove_name(), c.remove_name())
    assert t3.fully_eval() == t.fully_eval()
    assert index(t2)(integer(0)).fully_eval() == d.fully_eval()
    assert index(t2)(integer(1)).fully_eval() == c.fully_eval()
    assert t3.fully_eval() == t.fully_eval()


def test_concat():
    a = constant('a')
    b = constant('b')
    c = constant('c')
    d = constant('d')
    t1 = cons(a, empty)
    t2 = list_term((b, c, d))
    t = concat(t1, t2)
    assert t(0).fully_eval() == a.fully_eval()
    assert t(1).fully_eval() == b.fully_eval()
    assert t(2).fully_eval() == c.fully_eval()
    assert t(3).fully_eval() == d.fully_eval()


def test_integer():
    i1 = integer(1)
    i2 = integer(1)
    i = plus(i1)(i2)
    assert i.fully_eval().value == 2
    i = minus(i1)(i2)
    assert i.fully_eval().value == 0
    i = times(i1)(i2)
    assert i.fully_eval().value == 1
    i = div(i1)(i2)
    assert i.fully_eval().value == 1
    i = mod(i1)(i2)
    assert i.fully_eval().value == 0


def test_repeat():
    x = variable("x")
    plus_1 = lambda_abs(x, plus(x)(1))
    i = repeat(plus_1)(0)(0)
    assert i.fully_eval().value == 0
    i = repeat(plus_1)(0)(1)
    assert i.fully_eval().value == 1
    i = repeat(plus_1)(0)(2)
    assert i.fully_eval().value == 2


def test_fold():
    i1 = integer(1)
    i2 = integer(1)
    ll = cons(i1)(cons(i2)(empty))
    i = integer_sum(ll)
    assert i.fully_eval().value == 2


def test_map():
    i1 = integer(1)
    i2 = integer(2)
    ll = cons(i1)(cons(i2)(empty))
    plus_one = plus(i1)
    ll_1 = map_term(plus_one)(ll)
    assert len(ll_1.fully_eval().terms) == 2
    assert ll_1.fully_eval().terms[0].value == 2
    assert ll_1.fully_eval().terms[1].value == 3


def test_multi_arg_function():
    x = variable('x')
    y = variable('y')
    a = variable('a')
    b = variable('b')
    default = integer(1)
    defaults = record({'b': default})
    f = lambda_abs_vars((x, y), lambda_abs_keywords(arguments={'a': a, 'b': b}, defaults=defaults, body=plus(x)(b)))
    f1 = lambda_abs(x, lambda_abs_keywords(arguments={'a': a}, defaults=empty_record, body=plus(x)(a)))
    zero = integer(0)
    one = integer(1)
    two = integer(2)
    three = integer(2)
    r = record({'a': zero})
    assert f1(one)(r).fully_eval().value == 1
    assert f(one)(two)(r).fully_eval().value == 2
    r1 = record({'a': zero, 'b': zero})
    assert f(one)(two)(r1).fully_eval().value == 1
    r2 = record({})
    assert isinstance(f1(one)(two)(r2).fully_eval(), pgsn_term.App)
    assert f1(one, a=zero).fully_eval().value == 1
    assert f(one, two, a=zero).fully_eval().value ==2
    assert f(one, two, a=zero, b=zero).fully_eval().value == 1


def test_let():
    x = variable('x')
    identity = lambda_abs(x, x)
    t = x(x)
    t1 = let(x, identity, t)
    assert t1.fully_eval() == identity.fully_eval()


def test_let2():
    x = variable('x')
    y = variable('y')
    one = integer(1)
    two = integer(2)
    t = lambda_abs_vars((x, y),
                        (lambda_abs(x, plus(x)(y))(plus(x)(x)))
                        )
    assert t(one)(two).fully_eval().value == 4
    t1 = lambda_abs_vars((x, y),
                         let(x, plus(x)(x),
                             plus(x)(y)
                             )
                         )
    assert t1(one)(two).fully_eval().value == 4


def test_bool():
    c = constant('c')
    d = constant('d')
    true = boolean(True)
    false = boolean(False)
    assert if_then_else(true)(c)(d).fully_eval() == c.fully_eval()
    assert if_then_else(false)(c)(d).fully_eval() == d.fully_eval()
    assert guard(true)(c).fully_eval() == c.fully_eval()
    assert guard(false)(c).fully_eval() != c.fully_eval()


def test_equal():
    s1 = string('s1')
    s2 = string('s2')
    assert equal(s1)(s1).fully_eval().value
    assert not equal(s1)(s2).fully_eval().value


def test_record():
    zero = integer(0)
    one = integer(1)
    two = integer(2)
    a = string('a')
    b = string('b')
    c = string('c')
    r = add_attribute(empty_record)(a)(zero)
    r = add_attribute(r)(b)(one)
    assert isinstance(r.fully_eval(), pgsn_term.Record)
    assert r(b).fully_eval().value == 1
    assert has_label(r)(b).fully_eval().value
    assert not has_label(r)(c).fully_eval().value
    assert has_label(remove_attribute(r)(b))(a).fully_eval().value
    assert not has_label(remove_attribute(r)(b))(b).fully_eval().value
    assert list_labels(r).fully_eval() == pgsn_term.List.named(terms=(a, b)).fully_eval()
    r1 = record({'c': two})
    assert overwrite_record(r)(r1)(a).fully_eval().value == 0
    assert overwrite_record(r)(r1)(c).fully_eval().value == 2
    r2 = record({'b': two})
    assert overwrite_record(r)(r2)(b).fully_eval().value == 2


class Id(pgsn_term.ConstMixin, pgsn_term.Unary):
    arity = 1

    def _applicable(self, args):
        return True

    def _apply_arg(self, arg):
        return arg


def test_pgsn_term_nested2():
    id_f = Id.named()
    x = variable('x')
    y = variable('y')
    z = variable('z')
    a = constant('a')
    b = constant('b')
    label = string('ll')
    t = lambda_abs_vars(
        (x, y),
        let(x, id_f(x), id_f(x)))
    assert t(a)(b).fully_eval() == a.fully_eval()
    t2 = lambda_abs_vars((x, y), t(x)(y))
    assert t2(a)(b).fully_eval() == a.fully_eval()
    t3 = lambda_abs_vars(
        (x, y),
        let(
            x, add_attribute(empty_record)(label)(x),
            overwrite_record(x)(y)
        )
    )
    r = record({'a': a})
    label_a = string('a')
    assert t3(empty_record)(r)(label_a).fully_eval() == a.fully_eval()
    assert has_label(t3(empty_record)(r))(label).fully_eval()
    assert t3(empty_record)(r)(label).fully_eval() == empty_record.fully_eval()


x = variable('x')
y = variable('y')
z = variable('z')
f = lambda_abs(x, x)
label_a = string('a')
label_f = string('f')
r1 = record({'a': true})
r2 = record({'f': f})
r3 = add_attribute(empty_record)(label_a)(true)
r4 = add_attribute(empty_record)(label_f)(f)


def test_overwrite_record_fun():
    assert set(overwrite_record(r1)(empty_record). \
               fully_eval().attributes().keys()) == {'a'}
    assert set(overwrite_record(r2)(empty_record). \
               fully_eval().attributes().keys()) == {'f'}


eta = lambda_abs_vars((y, z), overwrite_record(y)(z))


def test_overwrite_record_eta():
    assert set(eta(r1)(empty_record). \
               fully_eval().attributes().keys()) == {'a'}
    assert set(eta(r2)(empty_record). \
               fully_eval().attributes().keys()) == {'f'}


def test_add_attribute_record_fun():
    assert set(r3.fully_eval().attributes().keys()) == {'a'}
    assert set(r4.fully_eval().attributes().keys()) == {'f'}
    assert set(add_attribute(r3)(label_a)(true). \
               fully_eval().attributes().keys()) == {'a'}
    assert set(add_attribute(r4)(label_f)(f). \
               fully_eval().attributes().keys()) == {'f'}


id_f = Id.named()

def test_value_of():
    assert pgsn_term.value_of(integer(1)) == 1
    assert pgsn_term.value_of(true)
    assert pgsn_term.value_of(string('hoge')) == 'hoge'
    assert pgsn_term.value_of(id_f(['gaga', 'piyo'])) == ['gaga', 'piyo']
    assert pgsn_term.value_of(id_f({'gaga':1, 'piyo':2})) == {'gaga':1, 'piyo':2}


def test_format():
    f_string = string('{x}, {y}, {z}')
    assert pgsn_term.value_of(format_string(f_string, {'x':1, 'y': 'hoge', 'z': [1, 2]})) == '1, hoge, [1, 2]'
