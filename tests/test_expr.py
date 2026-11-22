"""Tests for the literal elements and the <expr> expression syntax."""

import xml.etree.ElementTree as ET

import pytest

import pgsn
from pgsn.pgsn_xml import PGSNError, _desugar


def run(source: str, defs: str = ""):
    """Evaluate a document consisting of `defs` followed by `source`."""
    return pgsn.python_value(pgsn.load_xml_string(f"<PGSN>{defs}{source}</PGSN>"))


def expr(source: str, defs: str = ""):
    """Evaluate a single <expr>. `<` must be written &lt; in XML."""
    return run(f"<expr>{source}</expr>", defs)


def expanded(source: str) -> str:
    """The XML an <expr> stands for, after desugaring."""
    root = ET.fromstring(f"<PGSN><expr>{source}</expr></PGSN>")
    _desugar(root)
    return ET.tostring(root[0], encoding="unicode")


DEFS = '<def name="n"><num>3</num></def><def name="who">world</def>'


# ------------------------------------------------------------------ #
# Literal elements
# ------------------------------------------------------------------ #

def test_num_is_an_integer():
    assert run("<num>42</num>") == 42
    assert run("<num>-7</num>") == -7
    assert run("<num>  8  </num>") == 8


def test_num_rejects_non_integers():
    for text in ("x", "1.5", "", "1 2"):
        with pytest.raises(PGSNError, match="not an integer|<num>"):
            run(f"<num>{text}</num>")


def test_bare_text_is_still_a_string():
    """Adding <num> must not change what a bare number in text means."""
    assert run("2024") == "2024"
    assert run("<ol><li>1</li></ol>") == ["1"]


def test_str_is_verbatim():
    """Unlike bare text, <str> keeps whitespace and does not interpolate."""
    assert run("<str> a {b} c </str>") == " a {b} c "
    assert run("<str></str>") == ""


def test_bare_text_is_stripped_and_interpolated():
    assert run(" plain ") == "plain"


def test_num_and_str_reject_children():
    with pytest.raises(PGSNError, match="not child elements"):
        run("<num><num>1</num></num>")
    with pytest.raises(PGSNError, match="not child elements"):
        run("<str><num>1</num></str>")


def test_reserved_alias_reaches_the_builtin():
    """`_plus` is what desugaring writes; a document cannot write it itself."""
    source = ('<apply><var name="_plus"/>'
              '<arg><num>1</num></arg><arg><num>2</num></arg></apply>')
    assert expr("1 + 2") == 3
    with pytest.raises(PGSNError, match="not a valid name"):
        run(source)


def test_builtin_element_is_gone():
    """`<builtin>` existed only to make operators unshadowable; the reserved
    alias does that now, so the element has no remaining purpose."""
    with pytest.raises(PGSNError, match="Unknown expression"):
        run('<builtin name="plus"/>')


# ------------------------------------------------------------------ #
# Arithmetic
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("source,expected", [
    ("1 + 2", 3),
    ("10 - 3 * 2", 4),
    ("(1 + 2) * 3", 9),
    ("7 // 2", 3),         # integer division; "/" is reserved for floats
    ("7 % 3", 1),
    ("-5 + 1", -4),
    ("- (2 * 3)", -6),
])
def test_arithmetic(source, expected):
    assert expr(source) == expected


def test_arithmetic_over_variables():
    assert expr("n * 2 + 1", DEFS) == 7


# ------------------------------------------------------------------ #
# Comparison and boolean operators
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("source,expected", [
    ("1 &lt; 2", True),
    ("2 &lt; 1", False),
    ("2 > 1", True),
    ("2 &lt;= 2", True),
    ("3 &lt;= 2", False),
    ("3 >= 4", False),
    ("2 >= 2", True),
    ("1 == 1", True),
    ("1 != 1", False),
])
def test_comparison(source, expected):
    assert expr(source) is expected


def test_comparison_written_with_cdata():
    """CDATA avoids escaping < for readers who prefer it."""
    assert run("<expr><![CDATA[1 < 2]]></expr>") is True


def test_equality_is_not_limited_to_integers():
    assert expr('"a" == "a"') is True
    assert expr('"a" == "b"') is False


def test_ordering_is_limited_to_integers():
    """Comparing strings has no meaning, so the term is left unreduced."""
    with pytest.raises(ValueError, match="cannot be converted"):
        expr('"a" &lt; "b"')


@pytest.mark.parametrize("source,expected", [
    ("true and false", False),
    ("true or false", True),
    ("not true", False),
    ("true and true and false", False),
    ("1 &lt; 2 and 3 > 2", True),
    ("not 1 == 2", True),
    ("false or true and false", False),
])
def test_boolean_operators(source, expected):
    assert expr(source) is expected


def test_true_and_false_are_names():
    """They are the builtins `true` and `false`, reached by name where the
    <expr> stands, like any other name in an expression."""
    assert expanded("true") == '<var name="true" />'
    assert expr("flag and true", '<def name="flag"><expr>1 == 1</expr></def>') is True


# ------------------------------------------------------------------ #
# Strings and f-strings
# ------------------------------------------------------------------ #

def test_plain_string_literal_does_not_interpolate():
    assert expr('"plain {x}"') == "plain {x}"


def test_fstring_interpolates_variables():
    assert expr('f"hello {who}"', DEFS) == "hello world"


def test_fstring_fields_are_names_as_in_text():
    """An f-string writes its fields as bare text does: a field is a name."""
    assert expr('f"{who}"', DEFS) == run("{who}", DEFS)
    for field in ("n + 1", "n:>4", "who!r", "who=", ""):
        with pytest.raises(PGSNError, match="not a valid name"):
            expr(f'f"[{{{field}}}]"', DEFS)


def test_a_single_brace_is_an_error():
    with pytest.raises(PGSNError, match="does not close it"):
        expr('f"{who"', DEFS)
    with pytest.raises(PGSNError, match="closes no field"):
        expr('f"who}"', DEFS)


def test_string_literals_take_either_quote_and_escapes():
    assert expr("'single'") == "single"
    assert expr(r'"say \"hi\" \\ done"') == 'say "hi" \\ done'
    assert expr(r'"a\tb"') == "a\tb"
    with pytest.raises(PGSNError, match="is not an escape"):
        expr(r'"\q"')


def test_fstring_without_fields_is_a_plain_string():
    assert expr('f"nothing here"') == "nothing here"
    assert expanded('f"nothing here"') == "<str>nothing here</str>"


def test_fstring_escapes_literal_braces():
    assert expr('f"{{literal}} {n}"', DEFS) == "{literal} 3"


# ------------------------------------------------------------------ #
# What the syntax deliberately excludes
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("source", [
    "obj.field", "xs[0]", "lambda x: x", "[i for i in xs]", "x if y else z",
    "2 ** 3", "{1: 2}", "(1, 2)", "1 +", "(1", "3abc", "x = 1",
])
def test_what_the_grammar_does_not_have(source):
    with pytest.raises(PGSNError, match="Cannot parse <expr>"):
        expr(source)


def test_a_call_is_not_allowed():
    with pytest.raises(PGSNError, match="a call is not allowed"):
        expr("f(x)")


@pytest.mark.parametrize("word", ["and", "or", "not"])
def test_the_words_of_the_syntax_are_not_names(word):
    """Every name a <def> can bind can be written in an <expr>, so the words
    the expression syntax uses are kept out of names altogether."""
    with pytest.raises(PGSNError, match="words of the expression syntax"):
        run(f'<def name="{word}">x</def>x')


@pytest.mark.parametrize("name", ["lambda", "if", "class", "None", "True"])
def test_a_python_keyword_is_an_ordinary_name(name):
    """The grammar is PGSN's own, so Python's keywords mean nothing to it."""
    assert expr(f"{name} + 1", f'<def name="{name}"><num>1</num></def>') == 2


def test_true_division_is_reserved():
    """`/` is left free for a future floating point type."""
    with pytest.raises(PGSNError, match="'/' is not defined"):
        expr("7 / 2")


def test_chained_comparison_is_rejected():
    with pytest.raises(PGSNError, match="chained comparison"):
        expr("1 &lt; 2 &lt; 3")


def test_empty_and_malformed_expressions():
    with pytest.raises(PGSNError, match="is empty"):
        expr("")
    with pytest.raises(PGSNError, match="Cannot parse.*at the end"):
        expr("1 +")


def test_expr_rejects_child_elements():
    with pytest.raises(PGSNError, match="not child elements"):
        run("<expr><num>1</num></expr>")


# ------------------------------------------------------------------ #
# The expansion is ordinary XML
# ------------------------------------------------------------------ #

def test_expansion_uses_the_reserved_alias():
    """Operators must not be interceptable by a binding named `plus`."""
    assert expanded("1 + 2") == (
        '<apply><var name="_plus" />'
        "<arg><num>1</num></arg><arg><num>2</num></arg></apply>"
    )


def test_an_operator_ignores_a_rebinding_of_its_name():
    result = run('<def name="plus">not addition</def><expr>1 + 2</expr>')
    assert result == 3


def test_expansion_of_a_variable_uses_var():
    assert expanded("x") == '<var name="x" />'


def test_expansion_is_ordinary_xml_apart_from_the_reserved_names():
    """Everything <expr> writes could have been written by hand, except that
    it reaches the builtins through names a document is not allowed to use.

    Stripping the reserved prefix therefore turns the expansion into a
    document, and that document means the same thing — as long as nothing has
    rebound the names, which is the whole point of the prefix.
    """
    source = 'f"{n} items" == "3 items" and n + 1 > 2'
    hand_written = expanded(source).replace('name="_', 'name="')
    assert run(hand_written, DEFS) == expr(source, DEFS)

    with pytest.raises(PGSNError, match="not a valid name"):
        run(expanded(source), DEFS)


def test_expr_composes_with_the_rest_of_the_document():
    """A GSN description takes an <expr> like any other value."""
    result = run(
        '<def name="count"><num>2</num></def>'
        "<Goal><description><expr>f\"{count} components are safe\"</expr>"
        "</description><undeveloped/></Goal>")
    assert result["description"] == "2 components are safe"


def test_value_child_is_a_gsn_description():
    """A GSN header with no text takes a lone value child as its description."""
    result = run('<def name="i"><num>7</num></def>'
                 '<Solution><expr>f"test report {i}"</expr></Solution>')
    assert result["description"] == "test report 7"


def test_several_value_children_in_a_header_are_rejected():
    with pytest.raises(PGSNError, match="several value children"):
        run("<Solution><str>a</str><str>b</str></Solution>")


def test_generating_sub_goals_by_recursion():
    """Integer literals and comparison make counting arguments expressible."""
    result = run("""
      <def name="goals" recursive="true">
        <template><param name="i" positional="true"/>
          <apply><var name="if_then_else"/>
            <arg><expr>i == 0</expr></arg>
            <arg><ol/></arg>
            <arg><apply><var name="cons"/>
              <arg><Goal>
                <description><expr>f"requirement {i} is met"</expr></description>
                <Solution><expr>f"test report {i}"</expr></Solution>
              </Goal></arg>
              <arg><apply><var name="goals"/>
                    <arg><expr>i - 1</expr></arg></apply></arg>
            </apply></arg>
          </apply>
        </template>
      </def>
      <Goal>All requirements are met
        <Strategy>Argue over each requirement
          <subGoals><apply><var name="goals"/>
                     <arg><num>3</num></arg></apply></subGoals>
        </Strategy>
      </Goal>""")
    sub_goals = result["support"]["sub_goals"]
    assert len(sub_goals) == 3
    # The recursion conses i onto the goals for i-1, so it counts down.
    assert [g["description"] for g in sub_goals] == [
        "requirement 3 is met", "requirement 2 is met", "requirement 1 is met"]
    assert sub_goals[0]["support"]["description"] == "test report 3"


def test_expr_as_a_template_argument():
    result = run(
        '<def name="i"><num>1</num></def>'
        '<def name="label"><template><param name="k" positional="true"/>'
        '<expr>f"item {k}"</expr></template></def>'
        '<apply><var name="label"/><arg><expr>i + 1</expr></arg></apply>')
    assert result == "item 2"
