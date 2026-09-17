"""Bare text is a string, wherever a value is expected.

The rule is one line long, but keeping it took a content model. What an
element holds is a sequence of items in document order — child elements and
the runs of text between them — and a value written after a binding is the
*tail* of that binding rather than the text of the element. Reading content in
one place is what makes the rule hold in every position rather than in the
positions someone remembered to handle.
"""

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError


def run(source: str):
    return pgsn.python_value(pgsn.load_xml_string(source))


def compiled(source: str):
    return pgsn.load_xml_string(source)


BINDING = '<def name="i"><num>2</num></def>'


# ------------------------------------------------------------------ #
# A block: bindings, then its value
# ------------------------------------------------------------------ #

def test_a_document_can_end_in_text():
    assert run(f"<PGSN>{BINDING}hello</PGSN>") == "hello"


def test_a_div_can_end_in_text():
    assert run(f"<PGSN><div>{BINDING}hello</div></PGSN>") == "hello"


def test_a_div_can_be_nothing_but_text():
    assert run("<PGSN><div>hello</div></PGSN>") == "hello"


def test_a_block_interpolates_like_any_other_text():
    """It is text in a value position, so `{name}` is filled in from scope."""
    assert run(f"<PGSN>{BINDING}item {{i}}</PGSN>") == "item 2"


def test_only_the_last_item_of_a_block_is_its_value():
    with pytest.raises(PGSNError, match="text where a binding was expected"):
        run(f"<PGSN>stray{BINDING}<var name='i'/></PGSN>")


# ------------------------------------------------------------------ #
# A template body is a block too
# ------------------------------------------------------------------ #

def test_a_template_body_can_be_text_after_a_param():
    assert run('<PGSN><def name="f" as="template">'
               '<param name="c" positional="true"/>component {c}</def>'
               '<apply template="f"><arg>A</arg></apply></PGSN>') == "component A"


def test_a_method_body_can_be_text_after_a_param():
    assert run('<PGSN><def name="C" as="class">'
               '<method name="m"><param name="x" positional="true"/>hi {x}</method>'
               '</def>'
               '<def name="o" as="object"><instanceOf var="C"/></def>'
               '<apply><send method="m" to="o"/><arg>you</arg></apply>'
               '</PGSN>') == "hi you"


# ------------------------------------------------------------------ #
# The function and the receiver are value positions as well
# ------------------------------------------------------------------ #

def test_the_function_position_reads_text():
    """Nothing useful comes of applying a string, but the document says what
    it says: the two spellings are the same term."""
    assert compiled("<PGSN><apply>f<arg>x</arg></apply></PGSN>") == compiled(
        "<PGSN><apply><str>f</str><arg>x</arg></apply></PGSN>")


def test_the_receiver_position_reads_text():
    assert compiled('<PGSN><send method="m">o</send></PGSN>') == compiled(
        '<PGSN><send method="m"><str>o</str></send></PGSN>')


def test_text_is_not_an_argument():
    with pytest.raises(PGSNError, match="found the text"):
        run('<PGSN><def name="f">u</def>'
            '<apply template="f">stray<arg>x</arg></apply></PGSN>')
