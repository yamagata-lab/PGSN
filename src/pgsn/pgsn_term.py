from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar
from typing import TypeAlias

import cattrs.preconf.json
from attrs import define, field, frozen, evolve
from cattrs.strategies import include_subclasses, configure_tagged_union

from pgsn import helpers

Term: TypeAlias = "Term"


def naming_context(names: set[str]) -> list[str]:
    return sorted(list(names))


class LambdaInterpreterError(Exception):
    pass


# Raised by a builtin that declines its arguments. The evaluator catches these
# where it applies a builtin, leaves the application as it stands and records
# the message in the term's meta_info, so they never escape evaluation. They
# are for mistakes in the document; a fault of the interpreter itself raises
# anything else and is not caught.
class PGSNRuntimeError(Exception):
    pass


# `cause` is why the argument the builtin refused is not a value, when that is
# the reason it was refused: a list that never came because a label was
# missing further in is reported as that missing label, not as a list that did
# not come.
class PGSNTypeError(PGSNRuntimeError):
    def __init__(self, message: str, cause: str | None = None):
        super().__init__(message)
        self.cause = cause


class PGSNIndexError(PGSNRuntimeError):
    pass


class PGSNKeyError(PGSNRuntimeError):
    pass


class PGSNValueError(PGSNRuntimeError):
    pass


# The evaluation budget every entry point starts from. One number, because a
# budget that varies with the way in was a way for a document to evaluate
# through the command and not through the library: `eu_ai_act_full.xml` needs
# more than a hundred thousand reductions and got them from `pgsn doc` alone.
# It bounds reductions, not time, and a caller who knows better passes its own.
DEFAULT_STEPS = 1_000_000


Castable: TypeAlias = "Term | int | str | bool | list | tuple | dict"


# A Python value passed where a term is expected. A tuple is a list, as it is
# for `list_term`. Anything else is a mistake in the calling program, and is
# reported as one.
def cast(x: Castable, is_named: bool) -> Term:
    match x:
        case Term():
            return x
        case str():
            return String.build(is_named=is_named, value=x)
        case bool():
            return Boolean.build(is_named=is_named, value=x)
        case int():
            return Integer.build(is_named=is_named, value=x)
        case list() | tuple():
            y = tuple(cast(z, is_named=is_named) for z in x)
            return List.build(is_named=is_named, terms=y)
        case dict():
            for k in x:
                if not isinstance(k, str):
                    raise TypeError(f"record labels must be strings, got {type(k).__name__}")
            y = {k: cast(z, is_named=is_named) for k, z in x.items()}
            return Record.build(is_named=is_named, attributes=y)
        case _:
            raise TypeError(f"a Python {type(x).__name__} cannot be made into a PGSN term: "
                            f"use str, int, bool, list, tuple, dict or a term")


class ConstMixin(ABC):

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        return None

    def _compute_free_bound(self) -> int:
        return 0

    def _free_variables(self) -> set[str]:
        return set()

    def _remove_name_with_context(self, context: list[str]) -> Term:
        return self.evolve(is_named=False)


@frozen(kw_only=True, cache_hash=True)
class Term(ABC):
    meta_info: dict = field(default={}, eq=False)
    is_named: bool = field(validator=helpers.not_none)
    # Cache for free_bound(). Terms are immutable, so it is computed at most once.
    _free_bound: int | None = field(default=None, init=False, eq=False, repr=False)

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return cls(is_named=is_named, **kwarg)

    @classmethod
    def nameless(cls, **kwarg) -> Term:
        return cls.build(is_named=False, **kwarg)

    @classmethod
    def named(cls, **kwarg) -> Term:
        return cls.build(is_named=True, **kwarg)

    # meta_info is changed in place, on a frozen term: it takes no part in
    # equality, the hash included, so the term stays the same term. The dict is
    # replaced rather than updated, because terms built without meta_info share
    # the default one, and a caller's dict may be shared as well.
    def add_metainfo(self, k:str, v:str):
        if self.meta_info.get(k) != v:
            object.__setattr__(self, "meta_info", self.meta_info | {k: v})

    # Keeps the reason evaluation stopped at this term, under "error". Being
    # stuck is not progress, so the term is annotated in place rather than
    # evolved.
    def mark_stuck(self, e: PGSNRuntimeError):
        self.add_metainfo("error", f"{type(e).__name__}: {e}")
        cause = getattr(e, "cause", None)
        if cause is not None:
            self.add_metainfo("cause", cause)

    def evolve(self, **kwarg):
        return self._evolve(**kwarg)

    def _evolve(self, **kwarg):
        return evolve(self, **kwarg)

    # The weak normal form, computed by the call-by-need machine below.
    # `steps` bounds two transitions of the machine together: an abstraction
    # taking an argument, and a builtin being applied.
    def fully_eval(self, steps=DEFAULT_STEPS) -> Term:
        t = self if not self.is_named else self.remove_name()
        machine = _Machine(steps)
        thunk = _new_thunk(t, None)
        machine.normalize(thunk)
        return machine.readback(thunk)

    # One more than the largest de Bruijn index free in this term, 0 if closed.
    @abstractmethod
    def _compute_free_bound(self) -> int:
        pass

    def free_bound(self) -> int:
        assert not self.is_named
        if self._free_bound is None:
            object.__setattr__(self, "_free_bound", self._compute_free_bound())
        return self._free_bound

    @abstractmethod
    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        pass

    def shift_or_none(self, num: int, cutoff: int) -> Term | None:
        assert not self.is_named
        # No free index reaches the cutoff, so nothing moves.
        if self.free_bound() <= cutoff:
            return None
        shifted = self._shift_or_none(num, cutoff)
        if shifted is None:
            return None
        assert not shifted.is_named
        return shifted

    def shift(self, num: int, cutoff: int) -> Term:
        return helpers.default(self.shift_or_none(num, cutoff), self)

    @abstractmethod
    def _free_variables(self) -> set[str]:
        pass

    def free_variables(self) -> set[str]:
        assert self.is_named
        return self._free_variables()

    @abstractmethod
    def _remove_name_with_context(self, context: list[str]) -> Term:
        pass

    def remove_name_with_context(self, context: list[str]) -> Term:
        assert self.is_named
        nameless = self._remove_name_with_context(context)
        assert not nameless.is_named
        return nameless

    def my_naming_context(self) -> list[str]:
        assert self.is_named
        return naming_context(self.free_variables())

    def remove_name(self) -> Term:
        assert self.is_named
        return self.remove_name_with_context(self.my_naming_context())

    def __call__(self, *args: Castable, **kwargs: Castable) -> Term:
        arg_terms = list(map(lambda x: cast(x, is_named=self.is_named), args))
        kwarg = Record.build(is_named=self.is_named,
                             attributes={k: cast(v, is_named=self.is_named) for k, v in kwargs.items()})
        t = self
        for arg in arg_terms:
            t = App.build(t1=t, t2=arg, is_named=self.is_named)
        if len(arg_terms) > 0 and kwargs == {}:
            return t
        return App.build(t1=t, t2=kwarg, is_named=self.is_named)

    def __getitem__(self, item):
        return self(item)

    def __getattr__(self, name):
        # Attribute access is sugar for record lookup: `t.description` means
        # `t("description")`. Dunder names are excluded, because returning a
        # Term for any `__x__` makes every introspection protocol misbehave —
        # `inspect.unwrap` follows `__wrapped__` forever, and copy, pickle and
        # pytest's collector are misled the same way.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return self(name)


@frozen
class Variable(Term):
    num: int | None = field(default=None)
    name: str | None = field(default=None)

    @num.validator
    def _check_num(self, _, v):
        assert self.is_named or (v is not None and v >= 0)

    @name.validator
    def _check_name(self, _, name):
        assert not self.is_named or name is not None

    def _evolve(self, num: int | None = None, name: str | None = None):
        if num is None and name is not None:
            return evolve(self, num=None, name=name, is_named=True)
        if num is not None and name is None:
            return evolve(self, num=num, name=None, is_named=False)
        else:
            assert False

    def _free_variables(self) -> set[str]:
        return {self.name}

    def _compute_free_bound(self) -> int:
        return self.num + 1

    def _shift_or_none(self, d, cutoff):
        if self.num < cutoff:
            return None
        else:
            return self.evolve(num=self.num+d)

    # The name is kept in meta_info, so that a variable left unbound can still
    # be reported by name once the term has been evaluated.
    def _remove_name_with_context(self, context: list[str]) -> Term:
        num = context.index(self.name)
        nameless = self.evolve(num=num)
        nameless.add_metainfo("name", self.name)
        return nameless


@frozen
class Abs(Term):
    v: Variable | None = field()
    t: Term = field(validator=helpers.not_none)

    @v.validator
    def _check_v(self, attribute, value):
        if self.is_named:
            assert value is not None and value.is_named and isinstance(value, Variable)
        else:
            assert value is None

    @t.validator
    def _check_t(self, _, value):
        assert value.is_named == self.is_named

    def _evolve(self, t: Term, v: Variable | None = None):
        if v is None and not t.is_named:
            return evolve(self, v=v, t=t, is_named=False)
        elif v is not None and v.is_named and t.is_named:
            return evolve(self, v=v, t=t, is_named=True)
        else:
            assert False

    def _compute_free_bound(self) -> int:
        # Index 0 in the body is bound by this abstraction.
        return max(self.t.free_bound() - 1, 0)

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        t_shifted = self.t.shift_or_none(num, cutoff + 1)
        if t_shifted is None:
            return None
        return self.evolve(t=t_shifted)

    def _free_variables(self) -> set[str]:
        f_vars = self.t.free_variables()
        return f_vars - {self.v.name}

    def _remove_name_with_context(self, context: list[str]) -> Term:
        new_context = [self.v.name] + context
        name_less_t = self.t.remove_name_with_context(new_context)
        return self.evolve(t=name_less_t, v=None)


@frozen
class App(Term):

    t1: Term = field(validator=helpers.not_none)
    t2: Term = field(validator=helpers.not_none)

    @t1.validator
    def _check_t1(self, _, v):
        assert v.is_named == self.is_named

    @t2.validator
    def _check_t2(self, _, v):
        assert v.is_named == self.is_named

    def _evolve(self, t1: Term | None = None, t2: Term | None = None):
        if t1 is None:
            t1 = self.t1
        if t2 is None:
            t2 = self.t2
        if t1.is_named and t2.is_named:
            return evolve(self, t1=t1, t2=t2, is_named=True)
        elif not t1.is_named and not t2.is_named:
            return evolve(self, t1=t1, t2=t2, is_named=False)
        else:
            assert False

    def _compute_free_bound(self) -> int:
        return max(self.t1.free_bound(), self.t2.free_bound())

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        t1_shifted_or_none = self.t1.shift_or_none(num, cutoff)
        t2_shifted_or_none = self.t2.shift_or_none(num, cutoff)
        if t1_shifted_or_none is None and t2_shifted_or_none is None:
            return None
        t1_shifted = helpers.default(t1_shifted_or_none, self.t1)
        t2_shifted = helpers.default(t2_shifted_or_none, self.t2)
        return self.evolve(t1=t1_shifted, t2=t2_shifted)

    def _free_variables(self) -> set[str]:
        return self.t1.free_variables() | self.t2.free_variables()

    def _remove_name_with_context(self, context: list[str]) -> Term:
        nameless_t1 = self.t1.remove_name_with_context(context)
        nameless_t2 = self.t2.remove_name_with_context(context)
        return self.evolve(t1=nameless_t1, t2=nameless_t2)


@frozen
class Builtin(Term, ABC):

    # How many arguments the builtin takes. A builtin of a fixed arity sets it
    # on its class; one whose arity depends on what it was built for computes
    # it from its fields.
    arity: ClassVar[int]

    # The result of applying the builtin to exactly `arity` arguments, a term
    # the evaluator goes on to evaluate. When the arguments do not meet its
    # preconditions it raises a PGSNRuntimeError, which leaves the application
    # stuck.
    #
    # The evaluator applies a builtin once, when the application is needed and
    # every argument has been evaluated to a weak head normal form. Data and
    # constants are handed over as themselves; anything else -- a function, an
    # application that cannot proceed, a free variable -- as the thunk of the
    # call-by-need machine below, so that a function keeps its environment.
    # The fields of data are thunks, possibly not evaluated yet. A builtin that
    # needs what a field holds returns a term that applies a builtin to the
    # field, and so has it evaluated as an argument in turn.
    @abstractmethod
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        pass

    def apply_args(self, args: tuple[Term, ...]) -> Term:
        assert not self.is_named and all(not arg.is_named for arg in args)
        assert len(args) == self.arity
        reduced = self._apply_args(args)
        assert not reduced.is_named
        return reduced

    # The builtin as messages name it. A builtin that is a step of another
    # takes the name of that one.
    def _reported_name(self) -> str:
        return type(self).__name__

    # Only type names go into the message: printing the argument would cost a
    # traversal. A thunk is named after its value.
    def _type_error(self, subject: str, expected: str, got: Term) -> PGSNTypeError:
        return PGSNTypeError(f"{self._reported_name()}: {subject} must be {expected}, "
                             f"got {type(_value(got)).__name__}",
                             cause=_why_stuck(got))

    # `got`, when it is one of `types`. Otherwise the builtin declines it, with
    # the message that `subject` must be `expected`.
    def _expect(self, got: Term, types, subject: str, expected: str):
        if not isinstance(got, types):
            raise self._type_error(subject, expected, got)
        return got


# The term a thunk the evaluator handed over stands for: its value.
def _value(t: Term) -> Term:
    return t._cell.value[0] if isinstance(t, Thunk) else t


# Why `t`, an argument the evaluator handed over, is stuck rather than a value,
# or None when it is a value. A stuck application already knows the first
# reason in the chain that led to it, so following the chain costs one look per
# term rather than a traversal. Only the head of the application is followed:
# an argument that is stuck where nothing needed it is no reason at all.
def _why_stuck(t: Term) -> str | None:
    while True:
        t = _value(t)
        if "cause" in t.meta_info:
            return t.meta_info["cause"]
        if "error" in t.meta_info:
            return t.meta_info["error"]
        if isinstance(t, App):
            t = t.t1
        elif isinstance(t, Variable):
            name = t.meta_info.get("name", t.name)
            return f"name {name!r} is not defined" if name is not None else "a name is not defined"
        else:
            return None


@frozen
class Unary(Builtin, ABC):
    arity = 1

    @abstractmethod
    def _apply_arg(self, arg: Term) -> Term:
        pass

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        return self._apply_arg(args[0])


@frozen
class ZeroAry(Builtin, ABC):
    arity = 0

    # A constant takes no argument.
    def _apply_args(self, _) -> Term:
        raise PGSNTypeError(f"{type(self).__name__}: a constant cannot be applied to an argument")


@frozen
class Constant(ConstMixin, ZeroAry):
    name = field(validator=helpers.not_none)


@frozen
class String(ConstMixin, ZeroAry):
    value: str = field(validator=helpers.not_none)


@frozen
class Integer(ConstMixin, ZeroAry):
    value: int = field(validator=helpers.not_none)


@frozen
class Boolean(ConstMixin, ZeroAry):
    value: bool = field(validator=helpers.not_none)


# A term that holds other terms in fields: a list, a record, a class or an
# object. Data is a value however its fields are, and applied to an argument
# it is a builtin that looks itself up. The fields are reached only through
# `fields` and `map_fields`, by the evaluator and by the operations on terms
# below, so a new kind of data defines those two and `_apply_arg`.
@frozen
class Data(Unary, ABC):
    # Whether every field is a thunk of the evaluator or a constant, so that
    # data applied again and again is not walked again and again.
    _closed: bool = field(default=False, init=False, eq=False, repr=False)

    # The fields, those of its classes included, in the order `map_fields`
    # visits them.
    @abstractmethod
    def fields(self):
        pass

    # The data with `f` applied to each of its fields, those of its classes
    # included, or the data itself when `f` changes none of them. `is_named`,
    # when given, is that of the result: data is named exactly when its fields
    # are, so removing the names changes both at once.
    @abstractmethod
    def map_fields(self, f, is_named: bool | None = None) -> Data:
        pass

    def _compute_free_bound(self) -> int:
        return max((c.free_bound() for c in self.fields()), default=0)

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        shifted = self.map_fields(lambda c: c.shift(num, cutoff))
        return None if shifted is self else shifted

    def _free_variables(self) -> set[str]:
        return set().union(*(c.free_variables() for c in self.fields()))

    def _remove_name_with_context(self, context: list[str]) -> Term:
        return self.map_fields(lambda c: c.remove_name_with_context(context), is_named=False)


# `d` with `f` applied to each value, or None when `f` changes none of them.
def _map_dict(d: dict, f) -> dict | None:
    mapped = {k: f(c) for k, c in d.items()}
    return None if all(mapped[k] is c for k, c in d.items()) else mapped


@frozen
class List(Data):
    terms: tuple[Term, ...] = field(validator=helpers.not_none)

    def __attrs_post_init__(self):
        assert all(isinstance(t, Term) for t in self.terms)
        assert all(t.is_named == self.is_named for t in self.terms)

    def fields(self):
        return self.terms

    def map_fields(self, f, is_named: bool | None = None) -> Data:
        is_named = helpers.default(is_named, self.is_named)
        terms = tuple(f(c) for c in self.terms)
        if is_named == self.is_named and all(a is b for a, b in zip(terms, self.terms)):
            return self
        return self.evolve(terms=terms, is_named=is_named)

    # A negative index counts from the end, as in Python and as `Index` does.
    def _apply_arg(self, term: Term) -> Term:
        self._expect(term, Integer, "the index", "an integer")
        if not -len(self.terms) <= term.value < len(self.terms):
            raise PGSNIndexError(f"List: index {term.value} is out of range "
                                 f"for a list of length {len(self.terms)}")
        return self.terms[term.value]


# The dicts and sets inside a term are plain, for ease of writing, and are
# never changed once the term is built: each is copied when the term is made,
# every accessor hands out a copy, and a changed term is a new one, made with
# evolve. That is what lets a term be compared and hashed by them. Equality
# and the hash read a dict through this key, so the order of the entries plays
# no part, as it plays none in `==`.
def _entries(d: dict) -> frozenset:
    return frozenset(d.items())


@frozen
class Record(Data):
    _attributes: dict[str, Term] = \
        field(converter=dict, eq=_entries, validator=helpers.not_none)

    def __attrs_post_init__(self):
        assert all(isinstance(k, str) for k in self.attributes().keys())
        assert all(isinstance(t, Term) for t in self.attributes().values())

    def fields(self):
        return self._attributes.values()

    def map_fields(self, f, is_named: bool | None = None) -> Data:
        is_named = helpers.default(is_named, self.is_named)
        attributes = _map_dict(self._attributes, f)
        if is_named == self.is_named and attributes is None:
            return self
        return self.evolve(is_named=is_named,
                           attributes=helpers.default(attributes, self._attributes))

    def attributes(self):
        return self._attributes.copy()

    def _apply_arg(self, term: Term) -> Term:
        self._expect(term, String, "the label", "a string")
        if term.value not in self._attributes:
            raise PGSNKeyError(f"Record: there is no label {term.value!r}")
        return self._attributes[term.value]


@frozen
class PGSNClass(Data):

    inherit: PGSNClass | None = field()
    name: str | None = field()
    _defaults: dict[str, Term] = field(default={}, converter=dict, eq=_entries,
                                       validator=helpers.not_none)
    _attributes: set[str, ...] = field(default=set(), converter=set, eq=frozenset,
                                       validator=helpers.not_none)
    _methods: dict[str, Term] = field(default={}, converter=dict, eq=_entries,
                                      validator=helpers.not_none)

    def __attrs_post_init__(self):
        assert all(k in self._attributes for k in self._defaults.keys())
        assert all(name not in self._attributes for name in self._methods.keys())
        assert not "name" in self._methods
        assert not "name" in self._attributes

    @classmethod
    def build(cls, is_named: bool, inherit: PGSNClass | None =None,
              name: str | None = None,
              defaults: dict[str, Term] | None =None, attributes: set[str] | None = None,
              methods: dict[str, Term] | None = None):
        defaults = helpers.default(defaults, {})
        attributes = helpers.default(attributes, set())
        methods = helpers.default(methods, {})
        if inherit is not None:
            defaults = inherit.defaults() | defaults
            attributes = set(inherit.attributes()) | set(attributes)
            methods = inherit.methods() | methods
        return super().build(is_named=is_named, name=name, inherit=inherit, defaults=defaults.copy(), attributes=set(attributes), methods=methods.copy())

    def defaults(self):
        return self._defaults.copy()

    def attributes(self):
        return self._attributes.copy()

    def methods(self):
        return self._methods.copy()

    def fields(self):
        inherited = self.inherit.fields() if self.inherit is not None else ()
        return [*inherited, *self._defaults.values(), *self._methods.values()]

    def map_fields(self, f, is_named: bool | None = None) -> Data:
        is_named = helpers.default(is_named, self.is_named)
        inherit = self.inherit.map_fields(f, is_named) if self.inherit is not None else None
        defaults = _map_dict(self._defaults, f)
        methods = _map_dict(self._methods, f)
        if (is_named == self.is_named and inherit is self.inherit
                and defaults is None and methods is None):
            return self
        return self.evolve(is_named=is_named, inherit=inherit,
                           defaults=helpers.default(defaults, self._defaults),
                           methods=helpers.default(methods, self._methods))

    # The object of this class with the attributes the record gives, and the
    # defaults for the rest.
    def _apply_arg(self, arg: Term) -> Term:
        arg = self._expect(arg, Record, "the argument", "a record")
        given = arg.attributes()
        if not self._defaults.keys() | given.keys() == self._attributes:
            raise PGSNValueError(f"PGSNClass: the attributes given, together with the defaults, "
                                 f"must be exactly the attributes of class {self.name}")
        missing = {k: d for k, d in self._defaults.items() if k not in given}
        return PGSNObject.nameless(instance=self, attributes=given | missing,
                                   methods=self._methods)


_CLASS_PARAMETERS = ("inherit", "name", "defaults", "attributes", "methods")


# A class is defined in steps, because the parameters are fields of a record
# and have to be evaluated first. DefineClass applies `_ClassDefinition` to
# each parameter, and that, when attributes are listed, applies itself once
# more to the parameters and to the name of each attribute.
@frozen
class DefineClass(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        self._expect(arg, Record, "the argument", "a record")
        params = arg.attributes()
        if not "inherit" in params:
            raise PGSNKeyError("DefineClass: inherit is missing")
        unknown = set(params.keys()) - set(_CLASS_PARAMETERS)
        if unknown:
            raise PGSNKeyError(f"DefineClass: unknown parameters {sorted(unknown)}")
        labels = tuple(k for k in _CLASS_PARAMETERS if k in params)
        definition = _ClassDefinition.nameless(labels=labels)
        return _spine(definition, [params[k] for k in labels])


@frozen
class _ClassDefinition(ConstMixin, Builtin):
    # The parameters given, in the order of _CLASS_PARAMETERS.
    labels: tuple[str, ...] = field(validator=helpers.not_none)
    # How many names of attributes follow the parameters; None until the list
    # of attributes has been evaluated.
    attribute_count: int | None = field(default=None)

    @property
    def arity(self) -> int:
        return len(self.labels) + (self.attribute_count or 0)

    def _reported_name(self) -> str:
        return "DefineClass"

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        params = dict(zip(self.labels, args))
        self._expect(params["inherit"], PGSNClass, "inherit", "a class")
        if "name" in params:
            self._expect(params["name"], String, "name", "a string")
        if "defaults" in params:
            self._expect(params["defaults"], Record, "defaults", "a record")
        if "attributes" in params:
            self._expect(params["attributes"], List, "attributes", "a list")
        if "attributes" in params and self.attribute_count is None:
            attributes = params["attributes"].terms
            if attributes:
                definition = _ClassDefinition.nameless(
                    labels=self.labels, attribute_count=len(attributes))
                return _spine(definition, [*args, *attributes])
        names = args[len(self.labels):]
        for k in names:
            self._expect(k, String, "each attribute", "a string")
        if "name" in (t.value for t in names):
            raise PGSNValueError("DefineClass: 'name' is reserved and cannot be an attribute")
        if "methods" in params:
            self._expect(params["methods"], Record, "methods", "a record")
            if "name" in (t for t in params["methods"].attributes().keys()):
                raise PGSNValueError("DefineClass: 'name' is reserved and cannot be a method")
        inherit: PGSNClass = params["inherit"]
        added_defaults = params["defaults"].attributes() if "defaults" in params else {}
        added_attributes = {a.value for a in names}
        added_methods = params["methods"].attributes() if "methods" in params else {}
        # The invariants of PGSNClass: every default names an attribute, and no name
        # is both an attribute and a method. The parent holds them by induction over
        # the construction paths, so only what this definition adds is examined.
        if not set(added_defaults.keys()) <= set(inherit.attributes()) | added_attributes:
            raise PGSNValueError("DefineClass: a default is given for a name that is not an attribute")
        if not added_attributes.isdisjoint(inherit.methods().keys()):
            raise PGSNValueError("DefineClass: an attribute is already inherited as a method")
        if not added_attributes.isdisjoint(added_methods.keys()):
            raise PGSNValueError("DefineClass: a name is both an attribute and a method")
        if not set(added_methods.keys()).isdisjoint(inherit.attributes()):
            raise PGSNValueError("DefineClass: a method is already inherited as an attribute")
        if "name" in params:
            name = params["name"].value
        else:
            name = None
        return PGSNClass.nameless(inherit=inherit, name=name,
                                  defaults=inherit.defaults() | added_defaults,
                                  attributes=set(inherit.attributes()) | added_attributes,
                                  methods=inherit.methods() | added_methods)


def _inherit_chain(cls: PGSNClass):
    if cls.inherit is None:
        return [cls]
    else:
        return [cls] + _inherit_chain(cls.inherit)


@frozen
class IsSubtype(ConstMixin, Builtin):
    """Structural subtyping: one type is a subtype of another when it declares
    at least the same attribute and method names.

    Only the labels are compared. A default value is never looked at, so the
    answer does not depend on how far either class has been reduced — which is
    what the inheritance-walking predicate this replaces could not promise.
    `inherit` is not consulted either: a class is a subtype of every class
    whose labels it covers, related to it or not.
    """
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        sub, sup = (self._expect(arg, PGSNClass, "both arguments", "classes") for arg in args)
        covered = (sup._attributes <= sub._attributes
                   and sup._methods.keys() <= sub._methods.keys())
        return Boolean.nameless(value=covered)


@frozen
class PGSNObject(Data):
    instance: PGSNClass = field(validator=helpers.not_none)
    _attributes: dict[str, Term] = field(converter=dict, eq=_entries, validator=helpers.not_none)
    _methods: dict[str, Term] = field(converter=dict, eq=_entries)

    def attributes(self):
        return self._attributes.copy()

    def methods(self):
        return self._methods.copy()

    def fields(self):
        return [*self.instance.fields(), *self._attributes.values(), *self._methods.values()]

    def map_fields(self, f, is_named: bool | None = None) -> Data:
        is_named = helpers.default(is_named, self.is_named)
        instance = self.instance.map_fields(f, is_named)
        attributes = _map_dict(self._attributes, f)
        methods = _map_dict(self._methods, f)
        if (is_named == self.is_named and instance is self.instance
                and attributes is None and methods is None):
            return self
        return self.evolve(is_named=is_named, instance=instance,
                           attributes=helpers.default(attributes, self._attributes),
                           methods=helpers.default(methods, self._methods))

    # An attribute is its value; a method is applied to the object.
    def _apply_arg(self, arg: Term) -> Term:
        arg = self._expect(arg, String, "the name of an attribute or a method", "a string")
        k = arg.value
        if k in self._attributes:
            return self._attributes[k]
        if k in self._methods:
            return App.nameless(t1=self._methods[k], t2=self)
        raise PGSNKeyError(f"PGSNObject: there is no attribute or method {k!r}")


@frozen
class Instance(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        return self._expect(arg, PGSNObject, "the argument", "an object").instance


## Builtin Functions

# List functions

@frozen
class Cons(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        tail = self._expect(args[1], List, "the second argument", "a list")
        return evolve(tail, terms=(args[0],) + tail.terms)

@frozen
class Head(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        self._expect(arg, List, "the argument", "a list")
        if len(arg.terms) == 0:
            raise PGSNIndexError("Head: the list is empty")
        return arg.terms[0]

@frozen
class Tail(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        self._expect(arg, List, "the argument", "a list")
        if len(arg.terms) == 0:
            raise PGSNIndexError("Tail: the list is empty")
        return List.nameless(terms=arg.terms[1:])


# Emptiness is a question about the list itself, not about its elements, so it
# is asked directly rather than by comparing the list with `empty`: equality
# looks at the elements and declines a list that holds anything but data.
@frozen
class IsEmpty(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        self._expect(arg, List, "the argument", "a list")
        return Boolean.nameless(value=len(arg.terms) == 0)


@frozen
class Index(ConstMixin, Builtin):
    arity = 2

    # A negative index counts from the end, as in Python.
    def _apply_args(self, args: tuple[Term,...]) -> Term:
        self._expect(args[0], List, "the first argument", "a list")
        self._expect(args[1], Integer, "the index", "an integer")
        terms = args[0].terms
        if not -len(terms) <= args[1].value < len(terms):
            raise PGSNIndexError(f"Index: index {args[1].value} is out of range "
                                 f"for a list of length {len(terms)}")
        return terms[args[1].value]


@frozen
class Map(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term,...]) -> Term:
        fun = args[0]
        items = self._expect(args[1], List, "the second argument", "a list")
        return List.nameless(terms=tuple(App.nameless(t1=fun, t2=t) for t in items.terms))


# Integer functions

# The values of the two arguments of `builtin`, which must be integers.
def _two_integers(builtin: Builtin, args: tuple[Term, ...]) -> tuple[int, int]:
    i1, i2 = (builtin._expect(arg, Integer, "both arguments", "integers") for arg in args)
    return i1.value, i2.value


@frozen
class Plus(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 + i2)


@frozen
class Minus(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 - i2)


@frozen
class Times(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 * i2)


@frozen
class Div(ConstMixin, Builtin):
    arity = 2

    # A zero divisor leaves the application stuck.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        if i2 == 0:
            raise PGSNValueError("Div: division by zero")
        return Integer.nameless(value=i1 // i2)


@frozen
class Mod(ConstMixin, Builtin):
    arity = 2

    # A zero divisor leaves the application stuck.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        if i2 == 0:
            raise PGSNValueError("Mod: modulo by zero")
        return Integer.nameless(value=i1 % i2)


# Control flow
@frozen
class IfThenElse(ConstMixin, Builtin):
    arity = 3

    # An integer counts as true when it is positive.
    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        cond = self._expect(terms[0], (Boolean, Integer),
                            "the condition", "a boolean or an integer")
        holds = cond.value if isinstance(cond, Boolean) else cond.value > 0
        return terms[1] if holds else terms[2]


# guard b t only progresses b is true
@frozen
class Guard(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        self._expect(terms[0], Boolean, "the condition", "a boolean")
        if not terms[0].value:
            raise PGSNValueError("Guard: the condition is false")
        return terms[1]


# Ordering. Only integers are ordered; the other comparisons in the expression
# syntax are derived from this one and from Equal.
@frozen
class LessThan(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Boolean.nameless(value=i1 < i2)


# Comparison. Only data can be compared. A term is comparable when it is a base
# value, or a list or a record whose components are all comparable in turn; the
# leaves of a comparable term are therefore always base values. Anything else is
# declined, and the application stays stuck rather than being called unequal: a
# function has no structural equality to speak of, a term still to be reduced
# holds no value yet, and a class or an object is not data -- what makes two of
# them the same is an open question, and answering it here would decide it by
# accident. Refusing the question is not the same answer as `false`, and a
# document that asks it stops where it asked.
#
# Whether a term is data is known only once all of it has been evaluated. So
# every component of both arguments is evaluated and checked before anything
# is answered, even when the answer is already decided. A list of another
# length, a record with other labels or a pair of components that differ makes
# the answer `false`, but only once both arguments are known to be data. The
# answer therefore does not depend on the order the components are looked at.
_BASE_VALUES = (String, Integer, Boolean, Constant)


@frozen
class Equal(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, args: tuple[Term,...]) -> Term:
        for arg in args:
            self._expect(arg, (*_BASE_VALUES, List, Record), "both arguments", "data")
        match args:
            case (List(terms=xs), List(terms=ys)) if len(xs) == len(ys):
                return _components_equal(args[0], args[1])
            case (Record(_attributes=xs), Record(_attributes=ys)) if xs.keys() == ys.keys():
                return _components_equal(List.nameless(terms=tuple(xs.values())),
                                         List.nameless(terms=tuple(ys[k] for k in xs)))
            case (List() | Record(), _) | (_, List() | Record()):
                # The shapes differ. A term equals itself exactly when it is
                # data, so comparing each argument with itself checks both.
                both = List.nameless(terms=args)
                return _components_equal(both, both, so_far=False)
            case (a, b):
                return Boolean.nameless(value=a == b)


# Whether each component of `xs` from the `i`th on equals the component of
# `ys` in the same place, and `so_far`. Every component is compared, whatever
# the comparisons before it said. The lists are passed on whole with the
# place, so a step costs the same however long they are.
def _components_equal(xs: List, ys: List, i: int = 0, so_far: bool = True) -> Term:
    if i == len(xs.terms):
        return Boolean.nameless(value=so_far)
    equal = _spine(Equal.nameless(), [xs.terms[i], ys.terms[i]])
    return _spine(_ComponentsEqual.nameless(),
                  [equal, Boolean.nameless(value=so_far), xs, ys, Integer.nameless(value=i)])


# The step of Equal that takes whether the `i`th components are equal, whether
# those before them were, both lists of components and `i`.
@frozen
class _ComponentsEqual(ConstMixin, Builtin):
    arity = 5

    def _reported_name(self) -> str:
        return "Equal"

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        equal, so_far, xs, ys, i = args
        self._expect(equal, Boolean, "the components", "data")
        return _components_equal(xs, ys, i.value + 1, so_far.value and equal.value)


# The first two arguments of `builtin` must be a record and a label.
def _record_and_label(builtin: Builtin, args: tuple[Term, ...]) -> tuple[dict, str]:
    record = builtin._expect(args[0], Record, "the first argument", "a record")
    label = builtin._expect(args[1], String, "the label", "a string")
    return record.attributes(), label.value


@frozen
class HasLabel(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, terms: tuple[Term, ...]) -> Term:
        attrs, label = _record_and_label(self, terms)
        return Boolean.nameless(value=label in attrs)


@frozen
class AddAttribute(ConstMixin, Builtin):
    arity = 3

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        attrs, label = _record_and_label(self, terms)
        attrs[label] = terms[2]
        return Record.nameless(attributes=attrs)


@frozen
class RemoveAttribute(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        attrs, label = _record_and_label(self, terms)
        if label not in attrs:
            raise PGSNKeyError(f"RemoveAttribute: there is no label {label!r}")
        del attrs[label]
        return Record.nameless(attributes=attrs)


# The first record with the fields of the second added, a field of the second
# replacing a field of the first with the same label in its place.
@frozen
class OverwriteRecord(ConstMixin, Builtin):
    arity = 2

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        r1, r2 = (self._expect(t, Record, "both arguments", "records") for t in terms)
        return Record.nameless(attributes=r1.attributes() | r2.attributes())


# A format string is text with fields: `{label}` is replaced by the field of
# that label, and `{{` and `}}` stand for the braces themselves. Nothing else
# happens between the braces -- what is written there is a label, looked up as
# it stands -- so the format string is never handed to Python's own
# formatting, which would read attribute and index references, conversions
# and format specifications out of it.
_FORMAT_PIECE = re.compile(r"\{\{|\}\}|\{([^{}]*)\}|[{}]|[^{}]+")


@frozen
class Formatter(ConstMixin, Builtin):
    arity = 2

    # The text between the fields is found here; the fields are then evaluated
    # as the arguments of `_Format`, as many as the format string names.
    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        self._expect(terms[0], String, "the format string", "a string")
        fields = self._expect(terms[1], Record, "the fields", "a record").attributes()
        texts = [""]
        labels = []
        for m in _FORMAT_PIECE.finditer(terms[0].value):
            piece = m.group()
            if piece == "{{" or piece == "}}":
                texts[-1] += piece[0]
            elif m.group(1) is not None:
                if m.group(1) not in fields:
                    raise PGSNKeyError(f"Formatter: there is no field {m.group(1)!r}")
                labels.append(m.group(1))
                texts.append("")
            elif piece in "{}":
                raise PGSNValueError(f"Formatter: an unmatched {piece!r} in the format string")
            else:
                texts[-1] += piece
        if not labels:
            return String.nameless(value=texts[0])
        format_ = _Format.nameless(texts=tuple(texts), labels=tuple(labels))
        return _spine(format_, [fields[label] for label in labels])


# The step of Formatter that takes the fields: the text before each field,
# and after the last one, and the label of each field.
@frozen
class _Format(ConstMixin, Builtin):
    texts: tuple[str, ...] = field(validator=helpers.not_none)
    labels: tuple[str, ...] = field(validator=helpers.not_none)

    @property
    def arity(self) -> int:
        return len(self.labels)

    def _reported_name(self) -> str:
        return "Formatter"

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        pieces = [self.texts[0]]
        for label, value, text in zip(self.labels, args, self.texts[1:]):
            pieces.append(self._show(label, value))
            pieces.append(text)
        return String.nameless(value="".join(pieces))

    # Only a string, an integer or a boolean is shown, and a boolean as PGSN
    # writes it.
    def _show(self, label: str, value: Term) -> str:
        if isinstance(value, Boolean):
            return "true" if value.value else "false"
        self._expect(value, (String, Integer), f"the field {label!r}",
                     "a string, an integer or a boolean")
        return str(value.value)


# Call-by-need evaluation: a lazy Krivine machine
#
# The machine evaluates a term under an environment instead of substituting:
# an argument is pushed unevaluated, an abstraction takes it off the stack
# into its environment, and a variable is looked up there. What the
# environment holds is a thunk, a cell that is evaluated the first time it is
# needed and then overwritten with its value, so an argument used many times
# is evaluated once.
#
# The machine stops at a weak head normal form. A builtin applied to as many
# arguments as it takes is strict in all of them: a frame on the stack holds
# it while the arguments are evaluated, one after the other, each to a weak
# head normal form, and the builtin is then applied once (see
# `Builtin._apply_args`). Data applied to an argument is a builtin too, but
# the data is not one of its arguments, so a record is projected without its
# fields being evaluated. Nothing is evaluated by calling the machine again
# from inside it, so the depth of the Python stack does not grow with the
# term.
#
# `fully_eval` goes on to the weak normal form: `normalize` evaluates in turn
# every thunk the value holds outside an abstraction, the fields of data and
# the arguments of an application that cannot proceed. The body of an
# abstraction is never evaluated.
#
# The result is read back with a thunk replaced by its value, or by what it
# was made from with its environment substituted if it was never forced.

_PENDING, _RUNNING, _DONE = range(3)


# A cell is compared and hashed by identity, as the sharing it stands for
# requires, and has no generated repr, which would walk its environment.
@define(eq=False, repr=False)
class _Cell:
    code: Term
    env: Any
    state: int
    # The value is a pair of a term and an environment. The environment is
    # that of a function and None for anything else, whose free indices are
    # those of the term evaluated at the top.
    value: Any
    readback: Term | None = None


def _new_thunk(code: Term, env) -> Thunk:
    return Thunk(is_named=False, cell=_Cell(code, env, _PENDING, None))


def _value_thunk(term: Term, env) -> Thunk:
    return Thunk(is_named=False, cell=_Cell(term, env, _DONE, (term, env)))


# An environment is a linked list of pairs (thunk, rest), None when empty. The
# thunk at a de Bruijn index, or, for an index the environment does not reach,
# the index of the same variable at the top.
def _lookup(env, i: int) -> Thunk | int:
    while env is not None:
        if i == 0:
            return env[0]
        env = env[1]
        i -= 1
    return i


def _delay(t: Term, env) -> Thunk:
    match t:
        case Thunk():
            return t
        case Variable():
            found = _lookup(env, t.num)
            if isinstance(found, Thunk):
                return found
            return _value_thunk(t if found == t.num else t.evolve(num=found), None)
        case ConstMixin():
            return _value_thunk(t, None)
        case Abs():
            return _value_thunk(t, env)
        case _:
            return _new_thunk(t, env)


# Data reached under an environment, with each field made a thunk.
def _close(t: Term, env) -> Term:
    if not isinstance(t, Data) or t._closed:
        return t
    closed = t.map_fields(lambda c: c if isinstance(c, ConstMixin) else _delay(c, env))
    object.__setattr__(closed, "_closed", True)
    return closed


def _spine(head: Term, args) -> Term:
    t = head
    for arg in args:
        t = App.nameless(t1=t, t2=arg)
    return t


# The frames on the machine's stack. Like a cell, a frame is compared by
# identity and has no generated repr.

# An argument, waiting for the function it is applied to.
@define(eq=False, repr=False)
class _Arg:
    thunk: Thunk


# A thunk being evaluated, to be overwritten with its value.
@define(eq=False, repr=False)
class _Update:
    thunk: Thunk


# A builtin waiting for its arguments to be evaluated. `next` is the first of
# them not evaluated yet.
@define(eq=False, repr=False)
class _Strict:
    builtin: Builtin
    args: tuple
    next: int = 0


# The arguments on top of the stack, the first one first.
def _pending_args(stack: list) -> tuple[Thunk, ...]:
    i = len(stack)
    while i > 0 and isinstance(stack[i - 1], _Arg):
        i -= 1
    return tuple(frame.thunk for frame in reversed(stack[i:]))


# A builtin applied to fewer arguments than it takes.
def _is_partial(t: Term) -> bool:
    n = 0
    while isinstance(t, App):
        n += 1
        t = t.t1
    return isinstance(t, Builtin) and n < t.arity


# What a builtin is handed for an argument that has been evaluated.
def _handed(thunk: Thunk) -> Term:
    t, _ = thunk._cell.value
    return t if isinstance(t, (Data, ConstMixin)) else thunk


class _Machine:

    def __init__(self, steps: int):
        self.steps = steps

    def _step(self, term: Term):
        if self.steps <= 0:
            raise LambdaInterpreterError('Reduction did not terminate', term)
        self.steps -= 1

    def force(self, thunk: Thunk):
        if thunk._cell.state != _DONE:
            self.whnf(thunk, None)
        return thunk._cell.value

    # `head` applied to every argument on top of the stack, which it takes off.
    def _stuck(self, head: Term, stack: list, error: PGSNRuntimeError | None) -> Term:
        args = _pending_args(stack)
        if not args:
            return head
        del stack[len(stack) - len(args):]
        t = _spine(head, args)
        if error is not None:
            t.mark_stuck(error)
        return t

    def whnf(self, term: Term, env) -> tuple[Term, object]:
        stack = []
        while True:
            # Evaluate `term` under `env` until it is a value.
            match term:
                case Thunk():
                    cell = term._cell
                    if cell.state == _RUNNING:
                        # Its value is needed to compute its value.
                        raise LambdaInterpreterError('Reduction did not terminate', term)
                    if cell.state == _PENDING:
                        cell.state = _RUNNING
                        stack.append(_Update(term))
                        term, env = cell.code, cell.env
                        continue
                    value = cell.value
                case Variable():
                    found = _lookup(env, term.num)
                    if isinstance(found, Thunk):
                        term, env = found, None
                        continue
                    free = term if found == term.num else term.evolve(num=found)
                    value = (self._stuck(free, stack, None), None)
                case App():
                    stack.append(_Arg(_delay(term.t2, env)))
                    term = term.t1
                    continue
                case Abs():
                    if stack and isinstance(stack[-1], _Arg):
                        self._step(term)
                        env = (stack.pop().thunk, env)
                        term = term.t
                        continue
                    value = (term, env)
                case Builtin():
                    term = _close(term, env)
                    args = _pending_args(stack)
                    n = term.arity
                    if not args or len(args) < n:
                        value = (self._stuck(term, stack, None), None)
                    else:
                        del stack[len(stack) - n:]
                        stack.append(_Strict(term, args[:n]))
                        value = None
                case _:
                    raise TypeError(f"not a term the machine evaluates: {type(term).__name__}")

            # Hand the value to what is on top of the stack, until something
            # is left to evaluate.
            while True:
                while stack and isinstance(stack[-1], _Update):
                    cell = stack.pop().thunk._cell
                    cell.state = _DONE
                    cell.value = value
                if not stack:
                    return value
                frame = stack[-1]
                if isinstance(frame, _Strict):
                    if frame.next < len(frame.args):
                        term, env = frame.args[frame.next], None
                        frame.next += 1
                        break
                    stack.pop()
                    try:
                        reduced = frame.builtin.apply_args(tuple(_handed(a) for a in frame.args))
                    except PGSNRuntimeError as e:
                        stack.extend(_Arg(a) for a in reversed(frame.args))
                        value = (self._stuck(frame.builtin, stack, e), None)
                        continue
                    self._step(frame.builtin)
                    term, env = reduced, None
                    break
                # The value is applied to more arguments.
                t, e = value
                if isinstance(t, (Abs, Builtin)):
                    term, env = t, e
                    break
                if _is_partial(t):
                    while isinstance(t, App):
                        stack.append(_Arg(t.t2))
                        t = t.t1
                    term, env = t, None
                    break
                # A stuck application is held in a thunk under the new one,
                # so that the term of a value does not deepen as it is applied.
                head = _value_thunk(t, None) if isinstance(t, App) else t
                value = (self._stuck(head, stack, None), None)

    # Evaluates every thunk the value of `thunk` holds outside an abstraction.
    def normalize(self, thunk: Thunk):
        todo = [thunk]
        seen = set()
        while todo:
            th = todo.pop()
            if id(th) in seen:
                continue
            seen.add(id(th))
            t, _ = self.force(th)
            while isinstance(t, App):
                todo.append(t.t2)
                t = t.t1
            if isinstance(t, Data):
                todo.extend(c for c in t.fields() if isinstance(c, Thunk))
            elif isinstance(t, Thunk):
                todo.append(t)

    # The term a thunk stands for, with no thunk left in it. A thunk is read
    # back after the thunks its term reaches, so that reading it back does not
    # recurse into theirs: the Python stack grows with the structure of one
    # term, not with the data. The free bound of each term read back is found
    # at once, for the same reason, before a term that holds it asks for it.
    def readback(self, thunk: Thunk) -> Term:
        todo = [thunk]
        expanded = set()

        def unread(th: Thunk, _) -> Thunk:
            if th._cell.readback is None:
                todo.append(th)
            return th

        while todo:
            th = todo[-1]
            cell = th._cell
            if cell.readback is not None:
                todo.pop()
                continue
            t, env = cell.value if cell.state == _DONE else (cell.code, cell.env)
            if id(th) not in expanded:
                expanded.add(id(th))
                waiting = len(todo)
                self._substitute(t, 0, env, unread)
                if len(todo) > waiting:
                    continue
            todo.pop()
            cell.readback = self._substitute(t, 0, env, self._read_under)
            cell.readback.free_bound()
        return thunk._cell.readback

    # The thunk has been read back already, before the term that reaches it.
    def _read_under(self, thunk: Thunk, depth: int) -> Term:
        r = thunk._cell.readback
        return r if depth == 0 else r.shift(depth, 0)

    # `t` under `depth` binders, with each thunk it reaches -- one written in
    # it, or one the environment holds for an index that reaches past the
    # binders -- replaced by `at_thunk(thunk, depth)`.
    def _substitute(self, t: Term, depth: int, env, at_thunk) -> Term:
        match t:
            case Variable():
                if t.num < depth:
                    return t
                found = _lookup(env, t.num - depth)
                if isinstance(found, Thunk):
                    return at_thunk(found, depth)
                num = found + depth
                return t if num == t.num else t.evolve(num=num)
            case Thunk():
                return at_thunk(t, depth)
            case Abs():
                return t.evolve(t=self._substitute(t.t, depth + 1, env, at_thunk))
            case App():
                return t.evolve(t1=self._substitute(t.t1, depth, env, at_thunk),
                                t2=self._substitute(t.t2, depth, env, at_thunk))
            case Data():
                return t.map_fields(lambda c: self._substitute(c, depth, env, at_thunk))
            case _:
                return t


def value_of(term: Term, steps=DEFAULT_STEPS, with_inherit_chain=False) -> Any:
    return to_python(term.fully_eval(steps), with_inherit_chain=with_inherit_chain)


def to_python(t: Term, with_inherit_chain=False, _path: str = "<root>") -> Any:
    """Convert a fully-evaluated PGSN term to a plain Python value.

    Args:
        t: The term to convert.  Must be in normal form (no App nodes).
        with_inherit_chain: When True, PGSNObject dicts include __parent_classes__.
        _path: Internal breadcrumb string that tracks the nested key/index path
               so that error messages can pinpoint exactly where conversion failed.
    """
    match t:
        case String():
            return t.value
        case Integer():
            return t.value
        case Boolean():
            return t.value
        case List():
            terms = t.terms
            result = []
            for i, t1 in enumerate(terms):
                child_path = f"{_path}[{i}]"
                # propagate both flags through list elements
                result.append(to_python(t1,
                                        with_inherit_chain=with_inherit_chain,
                                        _path=child_path))
            return result
        case Record():
            attr = t.attributes()
            out = {}
            for k, t1 in attr.items():
                child_path = f"{_path}.{k}"
                out[k] = to_python(t1,
                                   with_inherit_chain=with_inherit_chain,
                                   _path=child_path)
            return out
        case PGSNObject():
            attr = t.attributes()
            cls_name = t.instance.name
            if cls_name is None:
                raise ValueError(
                    f"PGSN term cannot be converted to a Python value at path "
                    f"'{_path}': an object is reported under the name of its "
                    f"class, and this object's class has no name. Give the "
                    f"class a name where it is defined."
                )
            attrs = {}
            for k, t1 in attr.items():
                child_path = f"{_path}.{k}"
                attrs[k] = to_python(t1,
                                     with_inherit_chain=with_inherit_chain,
                                     _path=child_path)
            attrs["__" + cls_name + "__"] = True
            if with_inherit_chain:
                attrs["__parent_classes__"] = [cls.name for cls in _inherit_chain(t.instance)]
            return attrs
        case _:
            # Include the path breadcrumb and a repr snippet to help locate the
            # stuck node without having to inspect the entire term tree manually.
            raise ValueError(
                f"PGSN term cannot be converted to a Python value at path '{_path}': "
                f"{_why_not_a_value(t)}. "
                f"Term (first 200 chars): {repr(t)[:200]}"
            )


# What readback tells the user about a term it met in place of a value.
def _why_not_a_value(t: Term) -> str:
    if "error" in t.meta_info:
        reason = f"evaluation stopped here: {t.meta_info['error']}"
        if "cause" in t.meta_info:
            reason += f", which was stuck on {t.meta_info['cause']}"
        return reason
    head = t
    while isinstance(head, App):
        head = head.t1
    if isinstance(head, Variable):
        name = head.meta_info.get("name")
        return f"name {name!r} is not defined" if name is not None else "a name is not defined"
    if isinstance(t, Abs):
        return "a function is not a value; an argument may be missing"
    return f"unexpected term type {type(t).__name__}"


json_term_converter = cattrs.preconf.json.make_converter()
union_strategy = functools.partial(configure_tagged_union, tag_name="type_name")
include_subclasses(Term, json_term_converter, union_strategy=union_strategy)


# The thunk of the call-by-need machine. It is defined after the JSON
# converter has collected the subclasses of Term, because a thunk exists only
# while the machine runs and is never written out.
@frozen
class Thunk(ConstMixin, Term):
    _cell: _Cell = field(validator=helpers.not_none)