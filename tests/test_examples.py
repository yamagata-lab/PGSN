"""Every example still runs.

The examples are material rather than specification, so nothing here fixes
what they produce: their output is free to change with the language. What is
fixed is that they produce something. A document the front end refuses, or one
that stops reducing short of a value, is a broken example whatever changed it,
and the examples are the only place where the pieces are used together at the
size a reader will meet them.

Modules (`<PGSNModule>`) are skipped: they are meant to be imported, and
cannot be evaluated on their own.

An example that takes minutes rather than seconds is marked `slow` and left
out of a plain `pytest` run; see `pyproject.toml` for how to ask for it.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import pgsn

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# Named rather than measured, because a threshold would have to run the
# example to apply it. Paths are relative to `examples/`, which is also how
# the tests are named.
SLOW = {"EU_AI_ACT/eu_ai_act_full.xml"}

# The budget the `pgsn` command allows, so that a document it evaluates is
# one this test evaluates too. `fully_eval`'s own default is ten times
# smaller, and `EU_AI_ACT/eu_ai_act_full.xml` needs more than that.
STEPS = 1_000_000


def _entry_points() -> list:
    params = []
    for path in sorted(EXAMPLES.rglob("*.xml")):
        if ET.parse(path).getroot().tag != "PGSN":
            continue
        name = str(path.relative_to(EXAMPLES))
        params.append(pytest.param(
            path, id=name,
            marks=[pytest.mark.slow] if name in SLOW else []))
    return params


@pytest.mark.parametrize("path", _entry_points())
def test_an_example_evaluates(path):
    pgsn.python_value(pgsn.load_xml(path, steps=STEPS))


def test_the_two_figure6_documents_agree():
    """The pair exists to show that writing the figure out and generating it
    are the same document. If they ever differ, the example has stopped
    demonstrating what it is there for."""
    plain = pgsn.python_value(pgsn.load_xml(EXAMPLES / "Figure6/figure6_plain.xml"))
    generated = pgsn.python_value(
        pgsn.load_xml(EXAMPLES / "Figure6/figure6_programmatic.xml"))
    assert plain == generated
