"""`gsn_dot` must accept both of the ways it is meant to be called.

The annotation used to read `dict[str] = None`: a `dict` missing its value
parameter, and a None default on a type that does not admit None. Nothing
noticed until the suite was run with `--typeguard-packages=pgsn`, at which
point every call to `gsn_dot` failed, including the documented ones.
"""

import pgsn


def a_goal():
    return pgsn.goal(description="g", support=pgsn.undeveloped).fully_eval()


def test_layout_attrs_may_be_omitted():
    assert pgsn.gsn_dot(a_goal()).source


def test_layout_attrs_may_be_given():
    assert "rankdir=LR" in pgsn.gsn_dot(a_goal(), {"rankdir": "LR"}).source
