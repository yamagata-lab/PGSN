from pgsn.dsl import *


def test_record():
    x = constant('x')
    y = constant('y')
    z = constant('z')
    r = record({'x': x, 'y': y, 'z': z})
    k1 = string('x')
    k2 = string('w')
    assert r(k1).fully_eval() == x.fully_eval()
    stuck = r(k2).fully_eval()
    assert isinstance(stuck, App) and "error" in stuck.meta_info


x = variable('x')
y = variable('y')
z = variable('z')
a = variable('a')
b = constant('b')
c = constant('c')
label_1 = string('l1')
label_2 = string('l2')
r1 = record({'l1': a})
r2 = add_attribute(empty_record)(label_2)(r1)
r3 = overwrite_record(r1)(r2)
def test_self_reference1():
    assert set(r3.fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference2():
    f = lambda_abs_vars((x, y),
                        let(
                            y, add_attribute(y)(label_2)(x),
                            overwrite_record(x)(y)
                        )
                        )
    assert set(f(r1)(r2).fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference3():
    f1 = lambda_abs_vars((x, y),
                         overwrite_record(x)(add_attribute(y)(label_2)(x))
                         )
    assert set(f1(r1)(r2).fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference4():
    r = overwrite_record(r1)(add_attribute(r2)(label_2)(r1), )
    assert set(r.fully_eval().attributes().keys()) == {'l1', 'l2'}


"""
Field access on a record, directly and with the record or the label passed
through abstractions, so that the label reaches the record from an
environment.
"""

import pytest
from pgsn.dsl import (
    record, integer, string, variable, lambda_abs, lambda_abs_vars,
    lambda_abs_keywords, let, let_vars, boolean, true, false,
    if_then_else, equal, plus, integer as mk_int,
)
from pgsn.pgsn_term import (
    Term, Record, String, Integer, Boolean, App, Abs,
    LambdaInterpreterError,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def fully_eval(t: Term) -> Term:
    """Fully evaluate a named term and return the normal form."""
    return t.fully_eval()


# ---------------------------------------------------------------------------
# Baseline: direct field access without any lambda (should always pass)
# ---------------------------------------------------------------------------

class TestDirectFieldAccess:
    """Record field access with no abstraction in between."""

    def test_single_field_integer(self):
        """record({"foo": 1})("foo") => 1"""
        r = record({"foo": integer(1)})
        result = fully_eval(r(string("foo")))
        assert isinstance(result, Integer)
        assert result.value == 1

    def test_single_field_string(self):
        """record({"key": "hello"})("key") => "hello" """
        r = record({"key": string("hello")})
        result = fully_eval(r(string("key")))
        assert isinstance(result, String)
        assert result.value == "hello"

    def test_multiple_fields(self):
        """record({"a": 1, "b": 2})("b") => 2"""
        r = record({"a": integer(1), "b": integer(2)})
        result = fully_eval(r(string("b")))
        assert isinstance(result, Integer)
        assert result.value == 2

    def test_nested_record_access(self):
        """record({"outer": record({"inner": 42})})("outer")("inner") => 42"""
        inner = record({"inner": integer(42)})
        outer = record({"outer": inner})
        result = fully_eval(outer(string("outer"))(string("inner")))
        assert isinstance(result, Integer)
        assert result.value == 42


# ---------------------------------------------------------------------------
# Field access with the record or the label passed through an abstraction
# ---------------------------------------------------------------------------

class TestFieldAccessThroughAbstractions:
    """
    The record or the label reaches the projection as an argument, so the
    machine finds it in an environment rather than written in place.
    """

    def test_lambda_passes_key_directly(self):
        """(λx. record({"foo": 1})(x))("foo") => 1"""
        _x = variable("x")
        r = record({"foo": integer(1)})
        term = lambda_abs(_x, r(_x))(string("foo"))
        result = fully_eval(term)
        assert isinstance(result, Integer)
        assert result.value == 1

    def test_lambda_passes_key_multi_field(self):
        """(λk. record({"a": 10, "b": 20})(k))("b") => 20"""
        _k = variable("k")
        r = record({"a": integer(10), "b": integer(20)})
        term = lambda_abs(_k, r(_k))(string("b"))
        result = fully_eval(term)
        assert isinstance(result, Integer)
        assert result.value == 20

    def test_lambda_wraps_record_and_key(self):
        """(λr k. r(k))(record({"x": 99}))("x") => 99, two arguments deep."""
        _r = variable("r")
        _k = variable("k")
        r_val = record({"x": integer(99)})
        term = lambda_abs_vars((_r, _k), _r(_k))(r_val)(string("x"))
        result = fully_eval(term)
        assert isinstance(result, Integer)
        assert result.value == 99

    def test_let_binding_with_record_access(self):
        """
        let r = record({"v": 7}) in r("v") => 7

        let desugars to (λr. r("v"))(record({"v":7})), so the record
        reaches the projection as an argument.
        """
        _r = variable("r")
        r_val = record({"v": integer(7)})
        term = let(_r, r_val, _r(string("v")))
        result = fully_eval(term)
        assert isinstance(result, Integer)
        assert result.value == 7

    def test_let_vars_multiple_bindings(self):
        """
        let r = record({"n": 3}), s = string("n") in r(s) => 3
        """
        _r = variable("r")
        _s = variable("s")
        r_val = record({"n": integer(3)})
        term = let_vars(
            ((_r, r_val), (_s, string("n"))),
            _r(_s)
        )
        result = fully_eval(term)
        assert isinstance(result, Integer)
        assert result.value == 3

    def test_record_built_inside_lambda(self):
        """
        (λx. record({"val": x}))("hello")("val") => "hello"

        The record is constructed *inside* the lambda so it contains a
        free variable before reduction.  The field access must be
        composed *before* fully_eval because fully_eval returns a
        nameless term; mixing named and nameless terms in a single App
        is not supported (cast() passes Term arguments through unchanged
        without re-stamping is_named).
        """
        _x = variable("x")
        # Compose the whole expression in named form, then evaluate once.
        term = lambda_abs(_x, record({"val": _x}))(string("hello"))(string("val"))
        result = fully_eval(term)
        assert isinstance(result, String)
        assert result.value == "hello"

    def test_field_value_is_lambda(self):
        """
        (λk. record({"id": λy.y})(k))("id")("applied") => "applied"

        The field value is itself a lambda; after extraction it must be
        applicable.
        """
        _k = variable("k")
        _y = variable("y")
        identity = lambda_abs(_y, _y)
        r = record({"id": identity})
        term = lambda_abs(_k, r(_k))(string("id"))(string("applied"))
        result = fully_eval(term)
        assert isinstance(result, String)
        assert result.value == "applied"


# ---------------------------------------------------------------------------
# lambda_abs_keywords – high-level API that depends on record + field access
# ---------------------------------------------------------------------------

class TestKeywordArguments:
    """
    lambda_abs_keywords internally uses overwrite_record and record field
    access via String keys, with the record passed as an argument.
    """

    def test_single_keyword_arg(self):
        """mk(desc="hello")("desc") works after keyword-arg machinery."""
        _desc = variable("desc")
        mk = lambda_abs_keywords(
            {"desc": _desc},
            _desc  # body just returns the desc variable
        )
        result = fully_eval(mk(desc=string("hello")))
        assert isinstance(result, String)
        assert result.value == "hello"

    def test_two_keyword_args(self):
        """f(a=1, b=2) extracts both fields correctly."""
        _a = variable("a")
        _b = variable("b")
        f = lambda_abs_keywords(
            {"a": _a, "b": _b},
            plus(_a)(_b)
        )
        result = fully_eval(f(a=integer(3), b=integer(4)))
        assert isinstance(result, Integer)
        assert result.value == 7

    def test_keyword_arg_with_default(self):
        """Default values are filled in when the caller omits a key."""
        from pgsn.dsl import record as mk_record
        _x = variable("x")
        f = lambda_abs_keywords(
            {"x": _x},
            _x,
            defaults=mk_record({"x": integer(42)})
        )
        result = fully_eval(f(x=integer(99)))
        assert isinstance(result, Integer)
        assert result.value == 99


# ---------------------------------------------------------------------------
# Shift correctness – unit-level tests on the shift operation itself
# ---------------------------------------------------------------------------

class TestShiftCorrectness:
    """
    Shifting is what turning the machine's state back into a term does to a
    value read under binders, so it is checked on its own.
    """

    def test_constant_record_shift_or_none_returns_none(self):
        """
        A Record containing only constants has no free variables, so
        shift_or_none should return None (nothing to shift).
        """
        r = Record.nameless(attributes={"foo": Integer.nameless(value=1)})
        result = r.shift_or_none(1, 0)
        assert result is None, (
            "shift_or_none on a constant Record must return None; "
            "got {!r}".format(result)
        )

    def test_app_shift_uses_t2_not_t1(self):
        """
        App(Record, String).shift_or_none(d, c) must not overwrite t2
        with t1.  After the shift the App's second child must still be
        a String, not a Record.
        """
        rec = Record.nameless(attributes={"foo": Integer.nameless(value=1)})
        key = String.nameless(value="foo")
        app = App.nameless(t1=rec, t2=key)

        # shift_or_none may return None (nothing to shift) or a new App;
        # if it returns a new App, t2 must still be the String key.
        result = app.shift_or_none(-1, 0)
        if result is not None:
            assert isinstance(result, App), "Expected App, got {!r}".format(result)
            assert isinstance(result.t2, String), (
                "t2 was corrupted from String to {!r}".format(type(result.t2))
            )
            assert result.t2.value == "foo"
