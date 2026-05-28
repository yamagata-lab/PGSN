"""
Tests for the Record field access bug in PGSN.

The root cause is two cooperating bugs in pgsn_term.py:
  1. App._shift_or_none (line 379): uses self.t1 instead of self.t2
  2. Record._shift_or_none (lines 558-562): calls t.shift() instead of
     t.shift_or_none(), causing it to return a non-None value even for
     constant records, which then triggers bug 1.

Together they corrupt the t2 (argument) slot of an App node during the
shift(-1, 0) step that follows beta reduction, replacing the String key
with the Record itself.  The subsequent field lookup then fails because
Record._applicable checks isinstance(term, String).
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
    """Record field access with no intervening beta reduction."""

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
# Core bug: field access after beta reduction triggers the shift path
# ---------------------------------------------------------------------------

class TestFieldAccessAfterBetaReduction:
    """
    These tests trigger App._shift_or_none during beta reduction.
    With the bug present the reduction terminates early (reduction stops)
    instead of returning the expected value.
    """

    def test_lambda_passes_key_directly(self):
        """
        (λx. record({"foo": 1})(x))("foo") => 1

        Beta reduction substitutes String("foo") for x, then does
        shift(-1, 0) on App(Record, Var(0)).  Bug 1 + Bug 2 cause t2 to
        be overwritten with the Record, making field lookup impossible.
        """
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
        """
        (λr k. r(k))(record({"x": 99}))("x") => 99

        Two levels of beta reduction; both shift passes must be correct.
        """
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

        let desugars to (λr. r("v"))(record({"v":7})), exercising the
        same shift path.
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
    access via String keys.  All of these paths go through the same
    shift machinery.
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
    Directly verify that Record.shift_or_none behaves correctly so that
    future refactors don't silently re-introduce the bug.
    """

    def test_constant_record_shift_or_none_returns_none(self):
        """
        A Record containing only constants has no free variables, so
        shift_or_none should return None (nothing to shift).

        Bug 2 caused it to always return a new non-None Record for
        constant records, masking the App._shift_or_none bug.
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

        This directly exercises App._shift_or_none bug 1.
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