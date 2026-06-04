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


def test_record_shift_under_unused_lambda():
    """Regression: Record fields must be shifted during beta-reduction.

    Applying a lambda whose body returns a record left a free variable
    pointing at the wrong binder (a self-referential Abs) instead of the
    value, because Record shifting discarded its results. Here the bound
    variable is unused, which is the minimal trigger.
    """
    from pgsn.dsl import lambda_abs, let, record, string, variable, python_value

    _args = variable("args")
    # (λargs. let g = "hello" in {k: g})  applied to {}   — args is unused
    t = lambda_abs(_args, let(variable("greeting"), string("hello"),
                              record({"k": variable("greeting")})))
    # Before the fix this raised ValueError (an Abs cannot be normalized).
    result = t(record({})).fully_eval()
    assert python_value(result) == {"k": "hello"}

    """Regression test: with_inherit_chain must propagate to nested objects.

    Run where the patched PGSN build is importable:
        pytest test_inherit_chain_propagation.py -v

    Background
    ----------
    `gsn_tree` classifies each node by walking ``__parent_classes__`` (the class
    inheritance chain) and matching against GSN_TYPES. That chain is only attached
    by ``to_python`` when ``with_inherit_chain=True``. If the flag is not
    propagated into the recursive ``value_of`` calls, only the root object carries
    the chain; every nested support / sub_goal / evidence object loses it and is
    rendered as a bare ``<Record>`` instead of its GSN type, which breaks the
    diagram. This test guards that the chain reaches every nested GSN object.
    """

    from pgsn.gsn import goal, strategy, evidence
    from pgsn.dsl import python_value

    GSN_TYPES = {"Goal", "Strategy", "Evidence", "Context", "Assumption", "Undeveloped"}

    def _build():
        return goal(
            description="System is secure",
            support=strategy(
                description="Break into sub-goals",
                sub_goals=[
                    goal(description="Input validated",
                         support=evidence(description="Static analysis passed")),
                    goal(description="Output sanitized",
                         support=evidence(description="Fuzzing test succeeded")),
                ],
            ),
        )

    def _gsn_objects(data, path="root"):
        """Yield (path, dict) for every dict that is a PGSN object (has a __Cls__ key)."""
        if isinstance(data, dict):
            cls_keys = [k for k in data
                        if k.startswith("__") and k.endswith("__") and k != "__parent_classes__"]
            if cls_keys:
                yield path, data
            for k, v in data.items():
                if k.startswith("__") and k.endswith("__"):
                    continue
                yield from _gsn_objects(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                yield from _gsn_objects(item, f"{path}[{i}]")

    def test_inherit_chain_reaches_every_nested_object():
        data = python_value(_build().fully_eval(), with_inherit_chain=True)

        objects = list(_gsn_objects(data))
        # the example has 6 GSN objects: 3 Goals, 1 Strategy, 2 Evidence
        assert len(objects) == 6, f"expected 6 GSN objects, found {len(objects)}"

        for path, obj in objects:
            chain = obj.get("__parent_classes__")
            assert chain is not None, f"missing __parent_classes__ at {path}"
            # every object in this example resolves to a known GSN type via its chain
            gsn_type = next((c for c in chain if c in GSN_TYPES), None)
            assert gsn_type is not None, f"no GSN ancestor in chain at {path}: {chain}"

    def test_root_and_children_resolve_expected_types():
        data = python_value(_build().fully_eval(), with_inherit_chain=True)

        def gsn_type_of(d):
            return next((c for c in d.get("__parent_classes__", []) if c in GSN_TYPES), None)

        assert gsn_type_of(data) == "Goal"
        assert gsn_type_of(data["support"]) == "Strategy"
        subs = data["support"]["sub_goals"]
        assert [gsn_type_of(s) for s in subs] == ["Goal", "Goal"]
        assert [gsn_type_of(s["support"]) for s in subs] == ["Evidence", "Evidence"]

