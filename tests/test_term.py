from src.pgsn import pgsn_term
from src.pgsn.dsl import *


def test_var():
    var_x = pgsn_term.Variable.named(name='x', meta_info={'name': 'x'})
    nameless_x = var_x.remove_name()
    assert (nameless_x.meta_info['name']== 'x')


def test_pgsn_term_id():
    x = variable('x')
    id_f = lambda_abs(x, x)
    t = id_f(id_f)
    assert t.eval() == id_f.eval()


def test_pgsn_term_const():
    c = constant('c')
    x = variable('x')
    id_f = lambda_abs(x, c)
    t = id_f(c)
    assert t.eval() == c.eval()


def test_pgsn_term_nested():
    x = variable('x')
    y = variable('y')
    z = variable('z')
    c = constant('c')
    d = constant('d')
    p1 = lambda_abs(x, lambda_abs(y, x))
    t = lambda_abs(y, lambda_abs(x, p1(x)(y)))
    assert t(c)(d).fully_eval() == d.fully_eval()


def test_pgsn_term_higher_order():
    x = variable('x')
    y = variable('y')
    z = variable('z')
    c = constant('c')
    d = constant('d')
    p1 = lambda_abs(x, lambda_abs(y, x))
    assert p1(c)(d).fully_eval() == c.fully_eval()
    t = lambda_abs(y, y(c)(d))(p1)
    assert t.fully_eval() == c.fully_eval()


class Id(ConstMixin, Unary):

    def _applicable(self, args):
        return True

    def _apply_arg(self, arg):
        return arg


def test_builtin():
    id_f = Id.named().fully_eval()
    c = constant('c').fully_eval()
    assert id_f.applicable_args((c,))
    assert id_f.apply_args((c,)) == (c, tuple())
    assert id_f(c).fully_eval() == c


def test_higher_order2():
    x = variable('x')
    y = variable('y')
    f = variable('f')
    a = constant('a')
    id = lambda_abs(x, x)
    g = lambda_abs_vars((f, y), f(y))
    assert g(id)(a).fully_eval() == a.fully_eval()
    h = lambda_abs(f, f(a))
    assert h(id).fully_eval() == a.fully_eval()


def test_eta_expansion():
    x = variable('x')
    y = variable('y')
    one = integer(1)
    two = integer(2)
    assert plus(one)(two).fully_eval().value == 3
    f = lambda_abs_vars((x, y), plus(x)(y))
    assert f(one)(two).fully_eval().value == 3


def test_self_reference():
    x = variable('x')
    y = variable('y')
    one = integer(1)
    two = integer(2)
    f = lambda_abs_vars((x, y),
                        let(
                            x, plus(x)(y),
                            plus(x)(y)
                        ))
    assert f(one)(two).fully_eval().value == 5

