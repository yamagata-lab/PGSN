"""Every example still runs.

The examples are material rather than specification, so nothing here fixes
what they produce: their output is free to change with the language. What is
fixed is that they produce something. A document the front end refuses, or one
that stops reducing short of a value, is a broken example whatever changed it,
and the examples are the only place where the pieces are used together at the
size a reader will meet them.

Modules (`<PGSNModule>`) are skipped: they are meant to be imported, and
cannot be evaluated on their own.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import pgsn

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _entry_points() -> list:
    # Ids are paths relative to `examples/`.
    params = []
    for path in sorted(EXAMPLES.rglob("*.xml")):
        if ET.parse(path).getroot().tag != "PGSN":
            continue
        params.append(pytest.param(path, id=str(path.relative_to(EXAMPLES))))
    return params


@pytest.mark.parametrize("path", _entry_points())
def test_an_example_evaluates(path):
    pgsn.python_value(pgsn.load_xml(path))


def test_the_two_figure6_documents_agree():
    """The pair exists to show that writing the figure out and generating it
    are the same document. If they ever differ, the example has stopped
    demonstrating what it is there for."""
    plain = pgsn.python_value(pgsn.load_xml(EXAMPLES / "Figure6/figure6_plain.xml"))
    generated = pgsn.python_value(
        pgsn.load_xml(EXAMPLES / "Figure6/figure6_programmatic.xml"))
    assert plain == generated
