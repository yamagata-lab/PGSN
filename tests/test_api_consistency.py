"""The public API and the XML builtin table must not drift apart.

`pgsn.__all__` and `pgsn_xml._BUILTINS` expose the same standard library of
PGSN terms through two different front ends.  Nothing links them at runtime, so
a name added to one is easily forgotten in the other.  These tests pin the
relationship down: every term-valued name is available under the same spelling
on both sides, with no exceptions beyond the GSN class aliases below.

Only *term-valued* names are compared.  The public API additionally exports
Python functions that build terms out of Python values (`string`, `record`,
`lambda_abs`, ...); XML has syntax for those instead of names, so they have no
counterpart in the builtin table.
"""

import pgsn
from pgsn import dsl, gsn
from pgsn.pgsn_term import Term
from pgsn.pgsn_xml import _BUILTINS, compile_pgsn_string


# XML spells the GSN class values in the same case as the tags they describe.
# Each alias must denote the very same term as its snake_case counterpart.
XML_CLASS_ALIASES = {
    "Goal": "goal_class",
    "Strategy": "strategy_class",
    "Evidence": "evidence_class",
    "Context": "context_class",
    "Assumption": "assumption_class",
    "GSN": "gsn_class",
    "Support": "support_class",
}


def public_terms() -> dict[str, Term]:
    """The term-valued part of the public API."""
    return {name: getattr(pgsn, name) for name in pgsn.__all__
            if isinstance(getattr(pgsn, name), Term)}


def module_terms(module) -> set[str]:
    """The public term-valued names defined by an internal module."""
    return {name for name in dir(module)
            if not name.startswith("_")
            and isinstance(getattr(module, name), Term)}


def test_every_public_term_is_available_to_xml():
    missing = set(public_terms()) - set(_BUILTINS)
    assert missing == set(), (
        f"exported from pgsn but not usable in XML: {sorted(missing)}. "
        "Add them to _BUILTINS.")


def test_every_xml_builtin_is_publicly_exported():
    extra = set(_BUILTINS) - set(pgsn.__all__) - set(XML_CLASS_ALIASES)
    assert extra == set(), (
        f"usable in XML but not exported from pgsn: {sorted(extra)}. "
        "Add them to __all__, or record them in XML_CLASS_ALIASES.")


def test_both_front_ends_bind_the_same_terms():
    """Same name, same term — not merely the same set of names."""
    mismatched = {name for name, term in public_terms().items()
                  if _BUILTINS[name] is not term}
    assert mismatched == set(), (
        f"bound to different terms in XML than in Python: {sorted(mismatched)}")


def test_xml_class_aliases_denote_the_same_terms():
    for alias, canonical in XML_CLASS_ALIASES.items():
        assert alias in _BUILTINS, f"XML alias {alias!r} is gone"
        assert _BUILTINS[alias] is getattr(pgsn, canonical), (
            f"XML alias {alias!r} no longer denotes {canonical!r}")


def test_every_term_defined_in_dsl_is_exposed():
    """A term added to dsl.py must reach both front ends, not just one."""
    missing = module_terms(dsl) - set(pgsn.__all__)
    assert missing == set(), (
        f"defined in dsl.py but not exported: {sorted(missing)}")


def test_every_term_defined_in_gsn_is_exposed():
    missing = module_terms(gsn) - set(pgsn.__all__)
    assert missing == set(), (
        f"defined in gsn.py but not exported: {sorted(missing)}")


def test_version_is_a_string():
    """`pgsn.__version__` comes from the installed package metadata.

    In a source tree that was never installed there is no metadata to read, and
    the fallback marks that case rather than hard-coding a number that would
    then have to be kept in step with pyproject.toml.
    """
    assert isinstance(pgsn.__version__, str)
    assert pgsn.__version__
    assert "__version__" in pgsn.__all__


def test_builtin_terms_are_terms():
    not_terms = {name for name, value in _BUILTINS.items()
                 if not isinstance(value, Term)}
    assert not_terms == set()


def test_builtin_name_resolves_to_the_public_term():
    """`<var name="..."/>` substitutes the builtin term itself.

    `repeat` is used here because it is the most recent addition.  The result
    is not evaluated: `repeat` counts down with `minus`, and XML has no integer
    literal syntax — a bare `3` in a document compiles to the *string* "3" — so
    the arithmetic builtins cannot yet be exercised from XML at all.
    """
    compiled = compile_pgsn_string('<PGSN><var name="repeat"/></PGSN>')
    assert compiled is pgsn.repeat
