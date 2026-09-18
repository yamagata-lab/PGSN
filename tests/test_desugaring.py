"""Shorthand is element-agnostic, and element-specific attributes are not
shorthand.

Desugaring runs as a pass of its own, before any element's own compiler sees
the document. What that buys is the property tested here: a shorthand expands
to the document the longhand *is*, on every element, including the elements
that carry attributes of their own. The two spellings therefore agree on what
they mean and on where they fail.
"""

import xml.etree.ElementTree as ET

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError, _desugar

RECORD = '<def name="r" as="dl"><dt key="k"/><dd>v</dd></def>'


def run(source: str, defs: str = ""):
    return pgsn.python_value(pgsn.load_xml_string(f"<PGSN>{defs}{source}</PGSN>"))


def expanded(source: str) -> str:
    root = ET.fromstring(f"<PGSN>{source}</PGSN>")
    _desugar(root)
    return ET.tostring(root[0], encoding="unicode")


def test_var_expands_beside_an_element_specific_attribute():
    """`template` is an attribute, not a child, so it is not in the way of a
    shorthand that stands for a child."""
    assert expanded('<apply template="f" var="x"/>') == expanded(
        '<apply template="f"><var name="x"/></apply>')


def test_the_two_spellings_fail_alike():
    """Neither is an application: a <var> in the argument list is not an
    argument. Which of the two is written no longer decides whether that is
    noticed."""
    for source in ('<apply template="f" var="x"/>',
                   '<apply template="f"><var name="x"/></apply>'):
        with pytest.raises(PGSNError, match="<arg> children"):
            run(source, '<def name="f">unused</def>')


def test_as_wraps_content_on_any_element():
    assert expanded('<arg as="ol"><li>a</li></arg>') == expanded(
        '<arg><ol><li>a</li></ol></arg>')


def test_a_receiver_can_be_written_as_shorthand():
    """`var` on a <get> is the receiver, because the receiver is what a child
    of <get> is. Nothing about <get> had to say so."""
    assert run('<get key="k" var="r"/>', RECORD) == "v"
    assert run('<get key="k"><var name="r"/></get>', RECORD) == "v"


def test_a_shorthand_cannot_sit_beside_the_content_it_stands_for():
    with pytest.raises(PGSNError, match="shorthand for the content"):
        run('<get key="k" var="r"><var name="r"/></get>', RECORD)
    with pytest.raises(PGSNError, match="shorthand for the receiver"):
        run('<get key="k" of="r"><var name="r"/></get>', RECORD)


# ------------------------------------------------------------------ #
# What the element's own compiler is left holding
# ------------------------------------------------------------------ #

def test_applying_a_function_to_nothing_is_the_function():
    """Application is binary, so an empty argument list applies nothing. It
    used to be rejected, which made `<apply>` the one construct that could not
    be written with the arguments it happened to have."""
    assert run('<def name="f" as="template">'
               '<param name="x" positional="true"/><var name="x"/></def>'
               '<apply><apply template="f"/><arg>hello</arg></apply>') == "hello"


def test_get_needs_a_key():
    """`of` on its own used to be dropped, and the error then complained that
    the <get> had no value -- about a receiver the document had supplied."""
    with pytest.raises(PGSNError, match="needs a 'key'"):
        run('<get of="r"/>', RECORD)


def test_send_needs_a_method():
    with pytest.raises(PGSNError, match="needs a 'method'"):
        run('<send to="r"/>', RECORD)
