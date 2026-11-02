from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from typing import Any
from typing import TypeAlias
from typing import TypeVar

import cattrs.preconf.json
from attrs import field, frozen, evolve
from cattrs.strategies import include_subclasses, configure_tagged_union

from pgsn import helpers

Term: TypeAlias = "Term"


def is_named(instance, attribute, value):
    assert value.is_named


def is_nameless(instance, attribute, value):
    assert not value.is_named


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


class PGSNTypeError(PGSNRuntimeError):
    pass


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


Castable: TypeAlias = "Term | int | str | bool | list | dict"


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
        case list():
            y = [cast(z, is_named=is_named) for z in x]
            return List.build(is_named=is_named, terms=y)
        case dict():
            y = {k: cast(z, is_named=is_named) for k, z in x.items()}
            return Record.build(is_named=is_named, attributes=y)
        case _:
            assert False


class ConstMixin(ABC):

    def _eval_or_none(self) -> Term | None:
        return None

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        return None

    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        return None

    def _compute_free_bound(self) -> int:
        return 0

    def _free_variables(self) -> set[str]:
        return set()

    def _remove_name_with_context(self, context: list[str]) -> Term:
        return self.evolve(is_named=False)


@frozen(kw_only=True, cache_hash=True)
class Term(ABC):
    # meta_info is always not empty
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

    def def_metainfo(self, k):
        meta_info = dict(self.meta_info)
        del meta_info[k]
        object.__setattr__(self, "meta_info", meta_info)

    # Keeps the reason evaluation stopped at this term, under "error". Being
    # stuck is not progress, so the term is annotated in place rather than
    # evolved.
    def mark_stuck(self, e: PGSNRuntimeError):
        self.add_metainfo("error", f"{type(e).__name__}: {e}")

    def evolve(self, **kwarg):
        evolved = self._evolve(**kwarg)
        return evolve(evolved)

    def _evolve(self, **kwarg):
        return evolve(self, **kwarg)

    # Only application becomes closure, otherwise None
    @abstractmethod
    def _eval_or_none(self):
        pass

    # If None is returned, the reduction is terminated. A term returned is a
    # reduction, even when it equals the term reduced: (λx. x x)(λx. x x)
    # reduces to itself.
    def eval_or_none(self):
        if self.is_named:
            t = self.remove_name()
        else:
            t = self
        evaluated = t._eval_or_none()
        assert (evaluated is None) or (not evaluated.is_named)
        return evaluated

    def eval(self) -> Term:
        t = self if not self.is_named else self.remove_name()
        evaluated = helpers.default(t.eval_or_none(), t)
        assert(not evaluated.is_named)
        return evaluated

    # FIXME: Use contexts in intermediate steps, not terms
    def fully_eval(self, steps=DEFAULT_STEPS) -> Term:
        t = self if not self.is_named else self.remove_name()
        # `steps` steps that reduce, and one more that finds nothing to reduce.
        for _ in range(steps + 1):
            t_reduced = t.eval_or_none()
            if t_reduced is None:
                return t
            t = t_reduced
        raise LambdaInterpreterError('Reduction did not terminate', t)

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
    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        pass

    def subst_or_none(self, variable: int, term: Term) -> Term | None:
        assert not self.is_named
        assert not term.is_named
        # The variable does not occur free here.
        if self.free_bound() <= variable:
            return None
        substituted = self._subst_or_none(variable, term)
        assert substituted is None or not substituted.is_named
        return substituted

    def subst(self, variable:int, term: Term) -> Term:
        substituted_or_none = self.subst_or_none(variable, term)
        substituted = helpers.default(substituted_or_none, self)
        return substituted

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

    def pretty(self):
        return self.__str__()

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

    @classmethod
    def from_name(cls, name:str):
        return cls.named(name=name)

    def _evolve(self, num: int | None = None, name: str | None = None):
        if num is None and name is not None:
            return evolve(self, num=None, name=name, is_named=True)
        if num is not None and name is None:
            return evolve(self, num=num, name=None, is_named=False)
        else:
            assert False

    def _free_variables(self) -> set[str]:
        return {self.name}

    def _eval_or_none(self):
        return None

    def _compute_free_bound(self) -> int:
        return self.num + 1

    def _shift_or_none(self, d, cutoff):
        if self.num < cutoff:
            return None
        else:
            return self.evolve(num=self.num+d)

    def _subst_or_none(self, num, term) -> Term | None:
        if self.num == num:
            return term
        else:
            return None

    def _remove_name_with_context(self, context: list[str]) -> Term:
        num = context.index(self.name)
        return self.evolve(num=num)


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

    # Evaluation stops at an abstraction and leaves its body as written, so a
    # term evaluates to a weak normal form. Every term the evaluator reduces is
    # then closed, which keeps builtin reductions stable under substitution,
    # and recursion through `fix` cannot unfold under a binder.
    def _eval_or_none(self) -> Term | None:
        return None

    def _compute_free_bound(self) -> int:
        # Index 0 in the body is bound by this abstraction.
        return max(self.t.free_bound() - 1, 0)

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        t_shifted = self.t.shift_or_none(num, cutoff + 1)
        if t_shifted is None:
            return None
        return self.evolve(t=t_shifted)

    def _subst_or_none(self, var: int, term: Term) -> Term | None:
        term_shifted_or_none = term.shift_or_none(1, 0)
        term_shifted = helpers.default(term_shifted_or_none, term)
        substituted = self.t.subst_or_none(var + 1, term_shifted)
        if substituted is None:
            return None
        else:
            return self.evolve(t=substituted)

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

    @classmethod
    def term(cls, t1: Term, t2: Term):
        if t1.is_named and t2.is_named:
            return cls.named(t1=t1, t2=t2)
        elif not t1.is_named and not t2.is_named:
            return cls.nameless(t1=t1, t2=t2)
        else:
            assert False

    def __attrs_post_init__(self):
        assert self.t1.is_named == self.t2.is_named

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

    def to_context(self) -> Context:
        if isinstance(self.t1, App):
            return self.t1.to_context().stack(self.t2)
        else:
            return Context.build(head=self.t1, args=(self.t2,))

    def _eval_or_none(self):
        if isinstance(self.t1, App):
            c = self.t1.to_context().stack(self.t2)
        else:
            c = Context.build(head=self.t1, args=(self.t2,))
        c_reduced = c.reduce_or_declined()
        if isinstance(c_reduced, PGSNRuntimeError):
            self.mark_stuck(c_reduced)
            return None
        if c_reduced is None:
            return None
        else:
            return c_reduced.to_term()

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

    def _subst_or_none(self, var: int, term: Term) -> Term | None:
        t1_subst_or_none = self.t1.subst_or_none(var, term)
        t2_subst_or_none = self.t2.subst_or_none(var, term)
        if t1_subst_or_none is None and t2_subst_or_none is None:
            return None
        t1_subst = helpers.default(t1_subst_or_none, self.t1)
        t2_subst = helpers.default(t2_subst_or_none, self.t2)
        return self.evolve(t1=t1_subst, t2=t2_subst)

    def _free_variables(self) -> set[str]:
        return self.t1.free_variables() | self.t2.free_variables()

    def _remove_name_with_context(self, context: list[str]) -> Term:
        nameless_t1 = self.t1.remove_name_with_context(context)
        nameless_t2 = self.t2.remove_name_with_context(context)
        return self.evolve(t1=nameless_t1, t2=nameless_t2)


@frozen
class Builtin(Term, ABC):

    # hack.  the default is an invalid value
    arity: int = field(validator=[helpers.not_none, helpers.non_negative])

    # The result of applying the builtin. When the arguments do not meet its
    # preconditions it raises a PGSNRuntimeError, which leaves the application
    # stuck. An argument that is not reduced yet fails the preconditions too;
    # the evaluator then reduces it and applies the builtin again. `args` holds
    # every pending argument, so it may be longer than the arity, but never
    # shorter.
    @abstractmethod
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        pass

    # None when there are fewer arguments than the arity: a partial application
    # is a value, not a failure.
    def apply_args_or_none(self, args: tuple[Term, ...]) -> tuple[Term, tuple[Term, ...]] | None:
        assert (not self.is_named and all(not arg.is_named for arg in args))
        # The arity is checked before anything else is: it costs nothing.
        if len(args) < self.arity:
            return None
        reduced = self._apply_args(args)
        assert not reduced.is_named
        return reduced, args[self.arity:]

    # Only type names go into the message: it is built every time an argument
    # is not reduced yet, and printing the argument would cost a traversal.
    def _type_error(self, subject: str, expected: str, got: Term) -> PGSNTypeError:
        return PGSNTypeError(f"{type(self).__name__}: {subject} must be {expected}, "
                             f"got {type(got).__name__}")


@frozen
class Unary(Builtin, ABC):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=1, is_named=is_named, **kwarg)

    @abstractmethod
    def _apply_arg(self, arg: Term) -> Term:
        pass

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        return self._apply_arg(args[0])


@frozen
class ZeroAry(Builtin, ABC):

    @classmethod
    def build(cls, is_named: bool, **kwargs) -> Term:
        return super().build(arity=0, is_named=is_named, **kwargs)

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


@frozen
class List(Unary):
    terms: tuple[Term, ...] = field(validator=helpers.not_none)

    def __attrs_post_init__(self):
        assert all(isinstance(t, Term) for t in self.terms)
        assert all(t.is_named == self.is_named for t in self.terms)

    def _eval_or_none(self):
        evaluated = [term.eval_or_none() for term in self.terms]
        if all(t is None for t in evaluated):
            return None
        else:
            evaluated_expanded = (x[0] if x[1] is None else x[1] for x in zip(self.terms, evaluated))
            return self.evolve(terms=tuple(evaluated_expanded))

    def _compute_free_bound(self) -> int:
        return max((t.free_bound() for t in self.terms), default=0)

    def _shift_or_none(self, d, c):
        shifted_or_none = [t.shift_or_none(d, c) for t in self.terms]
        if all(s is None for s in shifted_or_none):
            return None
        shifted = (helpers.default(shifted_or_none[i], self.terms[i]) for i in range(len(self.terms)))
        return self.evolve(terms=tuple(shifted))

    def _subst_or_none(self, num, term):
        subst = [t.subst_or_none(num, term) for t in self.terms]
        if all(t is None for t in subst):
            return None
        else:
            subst_expanded = (x[0] if x[1] is None else x[1] for x in zip(self.terms, subst))
            return self.evolve(terms=tuple(subst_expanded))

    def _free_variables(self):
        return set().union(*[t.free_variables() for t in self.terms])

    def _remove_name_with_context(self, context):
        return List.nameless(meta_info=self.meta_info,
                             terms=tuple(t.remove_name_with_context(context) for t in self.terms))

    # A negative index counts from the end, as in Python and as `Index` does.
    def _apply_arg(self, term: Term) -> Term:
        if not isinstance(term, Integer):
            raise self._type_error("the index", "an integer", term)
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
class Record(Unary):
    _attributes: dict[str, Term] = \
        field(converter=dict, eq=_entries, validator=helpers.not_none)

    def __attrs_post_init__(self):
        assert all(isinstance(k, str) for k in self.attributes().keys())
        assert all(isinstance(t, Term) for t in self.attributes().values())

    def _evolve(self, is_named: bool | None = None, attributes: dict[str, Term] | None =None):
        if attributes is None:
            attributes = self._attributes
        if is_named is None:
            is_named = self.is_named
        return evolve(self, is_named=is_named, attributes=attributes.copy())

    def attributes(self):
        return self._attributes.copy()

    def _eval_or_none(self):
        evaluated = {label: t.eval_or_none() for label, t in self.attributes().items()}
        if all(t is None for _, t in evaluated.items()):
            return None
        else:
            evaluated_expand = dict(evaluated)
            for k in evaluated.keys():
                if evaluated_expand[k] is None:
                    evaluated_expand[k] = self.attributes()[k]
            return self.evolve(attributes=evaluated_expand)

    def _compute_free_bound(self) -> int:
        return max((t.free_bound() for t in self._attributes.values()), default=0)

    def _shift_or_none(self, d, c):
        shifted = dict((label, t.shift_or_none(d, c)) for label, t in self.attributes().items())
        if all(s is None for s in shifted.values()):
            return None
        for k in shifted.keys():
            if shifted[k] is None:
                shifted[k] = self._attributes[k]
        return self.evolve(attributes=shifted)

    def _subst_or_none(self, num, term):
        subst = dict((label, t.subst_or_none(num, term)) for label, t in self.attributes().items())
        if all(t is None for _, t in subst.items()):
            return None
        else:
            for k in subst.keys():
                if subst[k] is None:
                    subst[k] = self._attributes[k]
            return self.evolve(attributes=subst)

    def _free_variables(self):
        return set().union(*(t.free_variables() for _, t in self.attributes().items()))

    def _remove_name_with_context(self, context):
        return self.evolve(
            attributes=dict((label, t.remove_name_with_context(context)) for label, t
                            in self.attributes().items()),
            is_named=False)

    def _apply_arg(self, term: Term) -> Term:
        if not isinstance(term, String):
            raise self._type_error("the label", "a string", term)
        if term.value not in self._attributes:
            raise PGSNKeyError(f"Record: there is no label {term.value!r}")
        return self._attributes[term.value]


@frozen
class PGSNClass(Unary):

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

    def _evolve(self,
                is_named: bool | None = None,
                name: str | None = None,
                inherit: PGSNClass | None = None,
                defaults: dict[str, Term] | None = None,
                attributes: set[str,...] | None = None,
                methods: dict[str, Term] | None = None):
        if is_named is None:
            is_named = self.is_named
        if name is None:
            name = self.name
        if inherit is None:
            inherit = self.inherit
        if defaults is None:
            defaults = self.defaults()
        if attributes is None:
            attributes = self.attributes()
        if methods is None:
            methods = self.methods()
        return evolve(self,
                      is_named=is_named,
                      name=name,
                      inherit=inherit,
                      defaults=defaults.copy(),
                      attributes=attributes,
                      methods=methods.copy())

    def _traverse(self, visit):
        if self.inherit is not None:
            inherit1 = visit(self.inherit)
        else:
            inherit1 = None
        defaults1 = {label: visit(t) for label, t in self.defaults().items()}
        methods1 = {label: visit(t) for label, t in self.methods().items()}
        if all(v is None for v in defaults1.values()):
            if all(v is None for v in methods1.values()):
                if inherit1 is None:
                    return None
        inherit2 = helpers.default(inherit1, self.inherit)
        defaults2 = {k: helpers.default(defaults1[k], self.defaults()[k]) for k in defaults1.keys()}
        methods2 = {k: helpers.default(methods1[k], self.methods()[k]) for k in self.methods().keys()}
        return self.evolve(inherit=inherit2, defaults=defaults2, methods=methods2)

    def _eval_or_none(self):
        return self._traverse(lambda t: t.eval_or_none())

    def _compute_free_bound(self) -> int:
        children = [*self._defaults.values(), *self._methods.values()]
        if self.inherit is not None:
            children.append(self.inherit)
        return max((t.free_bound() for t in children), default=0)

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        return self._traverse(lambda t: t.shift_or_none(num, cutoff))

    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        return self._traverse(lambda t: t.subst_or_none(variable, term))

    def _free_variables(self) -> set[str]:
        vars_inherit = self.inherit.free_variables() if self.inherit is not None else set()
        vars_defaults = set().union(*(t.free_variables() for t in self.defaults().values()))
        vars_methods = set().union(*(t.free_variables() for t in self.methods().values()))
        return vars_inherit | vars_defaults | vars_methods

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, Record):
            raise self._type_error("the argument", "a record", arg)
        attr = arg.attributes()
        if not set(self.defaults().keys()) | set(attr.keys()) ==  set(self.attributes()):
            raise PGSNValueError(f"PGSNClass: the attributes given, together with the defaults, "
                                 f"must be exactly the attributes of class {self.name}")
        for k in self._defaults:
            if not k in attr.keys():
                attr[k] = self.defaults()[k]
        return PGSNObject.nameless(instance=self, attributes=attr, methods=self.methods())

    def _remove_name_with_context(self, context: list[str]) -> Term:
        reduced = self._traverse(lambda t: t.remove_name_with_context(context))
        if reduced is None:
            return self.evolve(is_named=False)
        return reduced.evolve(is_named=False)


@frozen
class DefineClass(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, Record):
            raise self._type_error("the argument", "a record", arg)
        params = arg.attributes()
        if not "inherit" in params:
            raise PGSNKeyError("DefineClass: inherit is missing")
        if not isinstance(params["inherit"], PGSNClass):
            raise self._type_error("inherit", "a class", params["inherit"])
        if "name" in params and not isinstance(params["name"], String):
            raise self._type_error("name", "a string", params["name"])
        unknown = set(params.keys()) - {"inherit", "name", "defaults", "attributes", "methods"}
        if unknown:
            raise PGSNKeyError(f"DefineClass: unknown parameters {sorted(unknown)}")
        if "defaults" in params and not isinstance(params["defaults"], Record):
            raise self._type_error("defaults", "a record", params["defaults"])
        if "attributes" in params and not isinstance(params["attributes"], List):
            raise self._type_error("attributes", "a list", params["attributes"])
        if "attributes" in params:
            for k in params["attributes"].terms:
                if not isinstance(k, String):
                    raise self._type_error("each attribute", "a string", k)
            if "name" in (t.value for t in params["attributes"].terms):
                raise PGSNValueError("DefineClass: 'name' is reserved and cannot be an attribute")
        if "methods" in params:
            if not isinstance(params["methods"], Record):
                raise self._type_error("methods", "a record", params["methods"])
            if "name" in (t for t in params["methods"].attributes().keys()):
                raise PGSNValueError("DefineClass: 'name' is reserved and cannot be a method")
        inherit: PGSNClass = params["inherit"]
        added_defaults = params["defaults"].attributes() if "defaults" in params else {}
        added_attributes = ({a.value for a in params["attributes"].terms}
                            if "attributes" in params else set())
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

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # `apply_args_or_none` hands over every pending argument, not just the ones
    # this builtin consumes, so the tuple is variadic.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        for arg in args[:2]:
            if not isinstance(arg, PGSNClass):
                raise self._type_error("both arguments", "classes", arg)
        sub = args[0]
        sup = args[1]
        covered = (set(sup.attributes()) <= set(sub.attributes())
                   and set(sup.methods()) <= set(sub.methods()))

        return Boolean.nameless(value=covered)


@frozen
class PGSNObject(Unary):
    instance: PGSNClass = field(validator=helpers.not_none)
    _attributes: dict[str, Term] = field(converter=dict, eq=_entries, validator=helpers.not_none)
    _methods: dict[str, Term] = field(converter=dict, eq=_entries)

    def attributes(self):
        return self._attributes.copy()

    def methods(self):
        return self._methods.copy()

    def _evolve(self,
                is_named: bool | None = None,
                instance: PGSNClass | None = None,
                attributes: dict[str, ...] | None = None,
                methods: dict[str, Term] | None = None):
        if is_named is None:
            is_named = self.is_named
        if instance is None:
            instance = self.instance
        if attributes is None:
            attributes = self._attributes.copy()
        if methods is None:
            methods = self.methods()
        return evolve(self,
                      is_named=is_named,
                      instance=instance,
                      attributes=attributes,
                      methods=methods)

    def _traverse(self, visit):
        instance1 = visit(self.instance)
        attributes1 = {label: visit(t) for label, t in self.attributes().items()}
        methods1 = {label: visit(t) for label, t in self.methods().items()}
        if all(v is None for v in attributes1.values()):
            if all(v is None for v in methods1.values()):
                if instance1 is None:
                    return None
        instance2 = helpers.default(instance1, self.instance)
        attributes2 = {k: helpers.default(attributes1[k], self.attributes()[k]) for k in attributes1.keys()}
        methods2 = {k: helpers.default(methods1[k], self.methods()[k]) for k in self.methods().keys()}
        return self.evolve(instance=instance2, attributes=attributes2, methods=methods2)

    def _eval_or_none(self):
        return self._traverse(lambda t: t.eval_or_none())

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        return self._traverse(lambda t: t.shift_or_none(num, cutoff))

    def _compute_free_bound(self) -> int:
        children = [self.instance, *self._attributes.values(), *self._methods.values()]
        return max(t.free_bound() for t in children)

    def _shift(self, num: int, cutoff: int) -> Term:
        return self._traverse(lambda t: helpers.default(t.shift(num, cutoff), t))

    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        return self._traverse(lambda t: t.subst_or_none(variable, term))

    def _free_variables(self) -> set[str]:
        vars_instance = self.instance.free_variables()
        vars_attributes = set().union(*(t.free_variables() for t in self.attributes().values()))
        vars_methods = set().union(*(t.free_variables() for t in self.methods().values()))
        return vars_instance | vars_attributes | vars_methods

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, String):
            raise self._type_error("the name of an attribute or a method", "a string", arg)
        k = arg.value
        if not (k in self.attributes().keys() or k in self.methods().keys()):
            raise PGSNKeyError(f"PGSNObject: there is no attribute or method {k!r}")
        if k in self.attributes().keys():
            return self.attributes()[k]
        else:
            return (self.methods()[k])(self)

    def _remove_name_with_context(self, context: list[str]) -> Term:
        reduced = self._traverse(lambda t: t.remove_name_with_context(context=context))
        if reduced is None:
            return self.evolve(is_named=False)
        return reduced.evolve(is_named=False)


@frozen
class Instance(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, PGSNObject):
            raise self._type_error("the argument", "an object", arg)
        return arg.instance


## Builtin Functions

# List functions

@frozen
class Cons(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # Variadic for the same reason as IsSubtype._apply_args above.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        if not isinstance(args[1], List):
            raise self._type_error("the second argument", "a list", args[1])
        return evolve(args[1], terms=(args[0],) + args[1].terms)

@frozen
class Head(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, List):
            raise self._type_error("the argument", "a list", arg)
        if len(arg.terms) == 0:
            raise PGSNIndexError("Head: the list is empty")
        return arg.terms[0]

@frozen
class Tail(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, List):
            raise self._type_error("the argument", "a list", arg)
        if len(arg.terms) == 0:
            raise PGSNIndexError("Tail: the list is empty")
        return List.build(terms=arg.terms[1:], is_named=self.is_named)


# Emptiness is a question about the list itself, not about its elements, so it
# is asked directly rather than by comparing the list with `empty`: equality
# looks at the elements and declines a list that holds anything but data.
@frozen
class IsEmpty(ConstMixin, Unary):

    def _apply_arg(self, arg: Term) -> Term:
        if not isinstance(arg, List):
            raise self._type_error("the argument", "a list", arg)
        return Boolean.build(is_named=self.is_named, value=len(arg.terms) == 0)


@frozen
class Index(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # A negative index counts from the end, as in Python.
    def _apply_args(self, args: tuple[Term,...]) -> Term:
        if not isinstance(args[0], List):
            raise self._type_error("the first argument", "a list", args[0])
        if not isinstance(args[1], Integer):
            raise self._type_error("the index", "an integer", args[1])
        terms = args[0].terms
        if not -len(terms) <= args[1].value < len(terms):
            raise PGSNIndexError(f"Index: index {args[1].value} is out of range "
                                 f"for a list of length {len(terms)}")
        return terms[args[1].value]


@frozen
class Map(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, args: tuple[Term,...]) -> Term:
        if not isinstance(args[1], List):
            raise self._type_error("the second argument", "a list", args[1])
        fun = args[0]
        arg = args[1]
        arg_list = arg.terms
        map_list = tuple((fun(t) for t in arg_list))
        map_result = List.build(terms=map_list, is_named=self.is_named)
        return map_result


# Integer functions

# The values of the first two arguments of `builtin`, which must be integers.
def _two_integers(builtin: Builtin, args: tuple[Term, ...]) -> tuple[int, int]:
    for arg in args[:2]:
        if not isinstance(arg, Integer):
            raise builtin._type_error("both arguments", "integers", arg)
    return args[0].value, args[1].value


@frozen
class Plus(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 + i2)


@frozen
class Minus(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 - i2)


@frozen
class Times(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Integer.nameless(value=i1 * i2)


@frozen
class Div(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # A zero divisor leaves the application stuck.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        if i2 == 0:
            raise PGSNValueError("Div: division by zero")
        return Integer.nameless(value=i1 // i2)


@frozen
class Mod(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # A zero divisor leaves the application stuck.
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        if i2 == 0:
            raise PGSNValueError("Mod: modulo by zero")
        return Integer.nameless(value=i1 % i2)


# Control flow
@frozen
class IfThenElse(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=3, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        if not (isinstance(terms[0], Boolean) or isinstance(terms[0], Integer)):
            raise self._type_error("the condition", "a boolean or an integer", terms[0])
        b = terms[0].value
        if isinstance(b, bool):
            return terms[1] if b else terms[2]
        if isinstance(b, int):
            return terms[1] if b > 0 else terms[2]


# guard b t only progresses b is true
@frozen
class Guard(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        if not isinstance(terms[0], Boolean):
            raise self._type_error("the condition", "a boolean", terms[0])
        if not terms[0].value:
            raise PGSNValueError("Guard: the condition is false")
        return terms[1]


# Ordering. Only integers are ordered; the other comparisons in the expression
# syntax are derived from this one and from Equal.
@frozen
class LessThan(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        i1, i2 = _two_integers(self, args)
        return Boolean.build(is_named=self.is_named, value=i1 < i2)


# Comparison. Only data can be compared. A term is comparable when it is a base
# value, or a list or a record whose components are all comparable in turn; the
# leaves of a comparable term are therefore always base values. Anything else is
# declined, and the application stays stuck rather than being called unequal: a
# function has no structural equality to speak of, a term still to be reduced
# holds no value yet, and a class or an object is not data -- what makes two of
# them the same is an open question, and answering it here would decide it by
# accident. Refusing the question is not the same answer as `false`, and a
# document that asks it stops where it asked.
def _comparable(term: Term) -> bool:
    if isinstance(term, (String, Integer, Boolean, Constant)):
        return True
    if isinstance(term, List):
        return all(_comparable(t) for t in term.terms)
    if isinstance(term, Record):
        return all(_comparable(t) for t in term._attributes.values())
    return False


@frozen
class Equal(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # Only the two arguments being compared are inspected; anything further
    # along the spine is passed on by `apply_args_or_none` and is none of our
    # business.
    def _apply_args(self, args: tuple[Term,...]) -> Term:
        for arg in args[:2]:
            if not _comparable(arg):
                raise self._type_error("both arguments", "data", arg)
        return Boolean.build(is_named=self.is_named, value=args[0] == args[1])


# The first two arguments of `builtin` must be a record and a label.
def _record_and_label(builtin: Builtin, args: tuple[Term, ...]) -> None:
    if not isinstance(args[0], Record):
        raise builtin._type_error("the first argument", "a record", args[0])
    if not isinstance(args[1], String):
        raise builtin._type_error("the label", "a string", args[1])


@frozen
class HasLabel(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    # Variadic: see IsSubtype._apply_args.
    def _apply_args(self, terms: tuple[Term, ...]) -> Term:
        _record_and_label(self, terms)
        k = terms[1].value
        b = k in terms[0].attributes()
        return Boolean.build(is_named=self.is_named, value=b)


@frozen
class AddAttribute(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=3, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        _record_and_label(self, terms)
        attrs = terms[0].attributes()
        attrs[terms[1].value] = terms[2]
        return Record.build(is_named=self.is_named, attributes=attrs)


@frozen
class RemoveAttribute(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        _record_and_label(self, terms)
        attrs = terms[0].attributes()
        if terms[1].value not in attrs:
            raise PGSNKeyError(f"RemoveAttribute: there is no label {terms[1].value!r}")
        del attrs[terms[1].value]
        return Record.build(is_named=self.is_named, attributes=attrs)


@frozen
class OverwriteRecord(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        for term in terms[:2]:
            if not isinstance(term, Record):
                raise self._type_error("both arguments", "records", term)
        r1 = terms[0].attributes()
        r2 = terms[1].attributes()
        r = r1
        for k, t in r2.items():
            r[k] = t
        return Record.build(is_named=self.is_named, attributes=r)


# A format string is text with fields: `{label}` is replaced by the field of
# that label, and `{{` and `}}` stand for the braces themselves. Nothing else
# happens between the braces -- what is written there is a label, looked up as
# it stands -- so the format string is never handed to Python's own
# formatting, which would read attribute and index references, conversions
# and format specifications out of it.
_FORMAT_PIECE = re.compile(r"\{\{|\}\}|\{([^{}]*)\}|[{}]|[^{}]+")


@frozen
class Formatter(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _apply_args(self, terms: tuple[Term,...]) -> Term:
        if not isinstance(terms[0], String):
            raise self._type_error("the format string", "a string", terms[0])
        if not isinstance(terms[1], Record):
            raise self._type_error("the fields", "a record", terms[1])
        fields = terms[1].attributes()
        pieces = []
        for m in _FORMAT_PIECE.finditer(terms[0].value):
            piece = m.group()
            if piece == "{{" or piece == "}}":
                pieces.append(piece[0])
            elif m.group(1) is not None:
                pieces.append(self._show(m.group(1), fields))
            elif piece in "{}":
                raise PGSNValueError(f"Formatter: an unmatched {piece!r} in the format string")
            else:
                pieces.append(piece)
        return String.build(is_named=self.is_named, value="".join(pieces))

    # Only a string, an integer or a boolean is shown, and a boolean as PGSN
    # writes it.
    def _show(self, label: str, fields: dict[str, Term]) -> str:
        if label not in fields:
            raise PGSNKeyError(f"Formatter: there is no field {label!r}")
        value = fields[label]
        if isinstance(value, Boolean):
            return "true" if value.value else "false"
        if not isinstance(value, (String, Integer)):
            raise self._type_error(f"the field {label!r}",
                                   "a string, an integer or a boolean", value)
        return str(value.value)



def _find_open_variables(t: Term) -> list[int]:
    """Return de Bruijn indices of free (unbound) Variables remaining in a nameless term.

    A nameless Variable with num >= 0 that survived full_eval is an open term —
    it was never substituted, which means some lambda abstraction is still unapplied.
    """
    match t:
        case Variable():
            return [t.num]
        case App():
            return _find_open_variables(t.t1) + _find_open_variables(t.t2)
        case Abs():
            # Variables with num == 0 are bound by this Abs; shift index for callers.
            return [i - 1 for i in _find_open_variables(t.t) if i > 0]
        case List():
            result = []
            for item in t.terms:
                result.extend(_find_open_variables(item))
            return result
        case Record():
            result = []
            for _, v in t.attributes().items():
                result.extend(_find_open_variables(v))
            return result
        case PGSNObject():
            result = []
            for _, v in t.attributes().items():
                result.extend(_find_open_variables(v))
            return result
        case _:
            return []


def value_of(term: Term, steps=DEFAULT_STEPS, with_inherit_chain=False) -> Any:
    t = term.fully_eval(steps)

    # Detect open terms (unapplied lambdas / unsubstituted variables) before
    # attempting conversion, so we can emit a meaningful diagnostic instead of
    # a cryptic "does not normalizes" error later.
    open_indices = _find_open_variables(t)
    if open_indices:
        raise ValueError(
            f"PGSN term did not fully evaluate: open (unbound) de Bruijn "
            f"indices {sorted(set(open_indices))} remain in the normalised term. "
            f"This usually means a lambda is still waiting for an argument. "
            f"Partial term (first 300 chars): {repr(t)[:300]}"
        )

    return to_python(t, with_inherit_chain=with_inherit_chain)


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
                f"unexpected term type {type(t).__name__}. "
                f"Term (first 200 chars): {repr(t)[:200]}"
            )


# Evaluation Context
# leftmost, outermost reduction
@frozen
class Context:
    head: Term = field(validator=helpers.not_none)
    args: tuple[Term, ...] = field(default=(), validator=helpers.not_none)

    @classmethod
    def build(cls, head, args):
        if isinstance(head, App):
            return cls.build(head=head.t1, args=(head.t2,) + args)
        else:
            return cls(head=head, args=args)

    def evolve(self, head=None, args=None):
        if head is None:
            head = self.head
        if args is None:
            args = self.args
        return type(self).build(head=head, args=args)

    def to_term(self) -> Term:
        term = self.head
        for arg in self.args:
            term = term(arg)
        return term

    def stack(self, arg: Term):
        return self.evolve(args=self.args + (arg,))

    # Outermost leftmost reduction. The reduced context, or, when nothing
    # reduces, the error of the builtin that declined its arguments if there is
    # one, and None otherwise.
    def reduce_or_declined(self) -> Context | PGSNRuntimeError | None:
        declined = None
        if isinstance(self.head, Abs) and len(self.args) > 0:
            head_substituted = (self.head.t.subst(0, self.args[0].shift(1, 0))
                                .shift(-1, 0))
            return self.evolve(head=head_substituted, args=self.args[1:])
        if isinstance(self.head, Builtin):
            # A builtin declines arguments that are not reduced yet as well,
            # so this is not the end: they are reduced below and the builtin
            # is applied again on the next step.
            try:
                applied = self.head.apply_args_or_none(self.args)
            except PGSNRuntimeError as e:
                applied = None
                declined = e
            if applied is not None:
                reduced, rest = applied
                return self.evolve(head=reduced, args=rest)
        head_reduced = self.head.eval_or_none()
        if head_reduced is not None:
            return self.evolve(head=head_reduced)
        for i in range(len(self.args)):
            arg_reduced = self.args[i].eval_or_none()
            if arg_reduced is not None:
                new_args = self.args[0:i] + (arg_reduced,) + self.args[i + 1:]
                return self.evolve(args=new_args)
        return declined


json_term_converter = cattrs.preconf.json.make_converter()
union_strategy = functools.partial(configure_tagged_union, tag_name="type_name")
include_subclasses(Term, json_term_converter, union_strategy=union_strategy)