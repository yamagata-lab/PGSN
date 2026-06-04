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