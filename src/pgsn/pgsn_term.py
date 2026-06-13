from __future__ import annotations

import functools
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

    def _free_variables(self) -> set[str]:
        return set()

    def _remove_name_with_context(self, context: list[str]) -> Term:
        return self.evolve(is_named=False)


@frozen(kw_only=True, cache_hash=True)
class Term(ABC):
    # meta_info is always not empty
    meta_info: dict = field(default={}, eq=False)
    is_named: bool = field(validator=helpers.not_none)

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return cls(is_named=is_named, **kwarg)

    @classmethod
    def nameless(cls, **kwarg) -> Term:
        return cls.build(is_named=False, **kwarg)

    @classmethod
    def named(cls, **kwarg) -> Term:
        return cls.build(is_named=True, **kwarg)

    def add_metainfo(self, k:str, v:str):
        self.meta_info[k] = v

    def def_metainfo(self, k):
        del(self.meta_info[k])

    def evolve(self, **kwarg):
        evolved = self._evolve(**kwarg)
        return evolve(evolved)

    def _evolve(self, **kwarg):
        return evolve(self, **kwarg)

    # Only application becomes closure, otherwise None
    @abstractmethod
    def _eval_or_none(self):
        pass

    # If None is returned, the reduction is terminated.
    def eval_or_none(self):
        if self.is_named:
            t = self.remove_name()
        else:
            t = self
        evaluated = t._eval_or_none()
        assert (evaluated is None) or (not evaluated.is_named)
        assert (evaluated is None) or (evaluated != t)  # should progress
        return evaluated

    def eval(self) -> Term:
        t = self if not self.is_named else self.remove_name()
        evaluated = helpers.default(t.eval_or_none(), t)
        assert(not evaluated.is_named)
        return evaluated

    # FIXME: Use contexts in intermediate steps, not terms
    def fully_eval(self, steps=100000) -> Term:
        t = self if not self.is_named else self.remove_name()
        for _ in range(steps):
            t_reduced = t.eval_or_none()
            assert t_reduced is None or t_reduced != t  # should progress
            if t_reduced is None:
                return t
            t = t_reduced
        raise LambdaInterpreterError('Reduction did not terminate', t)

    @abstractmethod
    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        pass

    def shift_or_none(self, num: int, cutoff: int) -> Term | None:
        assert not self.is_named
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

    def __attr_post_init__(self):
        assert self.v.is_named == self.t.is_named

    def _evolve(self, t: Term, v: Variable | None = None):
        if v is None and not t.is_named:
            return evolve(self, v=v, t=t, is_named=False)
        elif v is not None and v.is_named and t.is_named:
            return evolve(self, v=v, t=t, is_named=True)
        else:
            assert False

    def _eval_or_none(self) -> Term | None:
        t_evaluated = self.t.eval_or_none()
        return None if t_evaluated is None else self.evolve(t=t_evaluated)

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
    def _shit_or_none(self, num: int, cutoff: int) -> Term | None:
        pass

    t1: Term = field(validator=helpers.not_none)
    t2: Term = field(validator=helpers.not_none)

    @t1.validator
    def _check_t1(self, _, v):
        assert v.is_named == self.is_named

    @t1.validator
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

    def __attr_post_init__(self):
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
        c_reduced = c.reduce_or_none()
        if c_reduced is None:
            return None
        else:
            return c_reduced.to_term()

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

    @abstractmethod
    def _applicable_args(self, args: tuple[Term, ...]) -> bool:
        pass

    def applicable_args(self, args: tuple[Term, ...]) -> bool:
        assert (not self.is_named and all(not arg.is_named for arg in args))
        return len(args) >= self.arity and self._applicable_args(args)

    @abstractmethod
    def _apply_args(self, args: tuple[Term, ...]) -> Term:
        pass

    def apply_args(self, args: tuple[Term, ...]) -> tuple[Term, tuple[Term, ...]]:
        assert self.applicable_args(args)
        reduced = self._apply_args(args)
        assert not reduced.is_named
        return reduced, args[self.arity:]


@frozen
class Unary(Builtin, ABC):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=1, is_named=is_named, **kwarg)

    @abstractmethod
    def _applicable(self, arg: Term):
        pass

    @abstractmethod
    def _apply_arg(self, arg: Term):
        pass

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 1 and self._applicable(args[0])

    def _apply_args(self, args: tuple[Term, ...]):
        return self._apply_arg(args[0])


@frozen
class ZeroAry(Builtin, ABC):

    @classmethod
    def build(cls, is_named: bool, **kwargs) -> Term:
        return super().build(arity=0, is_named=is_named, **kwargs)

    def _applicable_args(self, _):
        return False

    def _apply_args(self, _):
        assert False


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

    def __attr_post_init__(self):
        assert all(isinstance(t, Term) for t in self.terms)
        assert len(self.terms) == 0 or all((t == self.is_named for t in self.terms))

    def _eval_or_none(self):
        evaluated = [term.eval_or_none() for term in self.terms]
        if all(t is None for t in evaluated):
            return None
        else:
            evaluated_expanded = (x[0] if x[1] is None else x[1] for x in zip(self.terms, evaluated))
            return self.evolve(terms=tuple(evaluated_expanded))

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

    def _applicable(self, term: Term):
        return isinstance(term, Integer) and 0 <= term.value < len(self.terms)

    def _apply_arg(self, term: Integer):
        return self.terms[term.value]


@frozen
class Record(Unary):
    _attributes: dict[str, Term] = \
        field(validator=helpers.not_none)

    def __attr_post_init__(self):
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

    def _applicable(self, term: Term):
        return isinstance(term, String) and term.value in self.attributes()

    def _apply_arg(self, term: String):
        return self.attributes()[term.value]


@frozen
class PGSNClass(Unary):

    inherit: PGSNClass | None = field()
    name: str | None = field()
    _defaults: dict[str, Term] = field(default={}, validator=helpers.not_none)
    _attributes: set[str, ...] = field(default=set(), validator=helpers.not_none)
    _methods: dict[str, Term] = field(default={}, validator=helpers.not_none)

    def __attr_post_init__(self):
        assert all(k in self._attributes for k in self._defaults.keys())
        assert all(name not in self._attributes for name in self._methods.keys())
        assert not "name" in self._method
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
            attributes = set(inherit.defaults()) | set(attributes)
            methods = inherit.methods() | methods
        return super().build(is_named=is_named, name=name, inherit=inherit, defaults=defaults.copy(), attributes=attributes, methods=methods.copy())

    def defaults(self):
        return self._defaults.copy()

    def attributes(self):
        return self._attributes

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

    def _shift_or_none(self, num: int, cutoff: int) -> Term | None:
        return self._traverse(lambda t: t.shift_or_none(num, cutoff))

    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        return self._traverse(lambda t: t.subst_or_none(variable, term))

    def _free_variables(self) -> set[str]:
        vars_inherit = self.inherit.free_variables() if self.inherit is not None else set()
        vars_defaults = set(t.free_variables() for t in self.defaults().values())
        vars_methods = set(t.free_variables() for t in self.methods().values())
        return vars_inherit | vars_defaults | vars_methods

    def _applicable(self, arg: Term):
        if not isinstance(arg, Record):
            return False
        attr = arg.attributes()
        if set(self.defaults().keys()) | set(attr.keys()) ==  set(self.attributes()):
            return True
        else:
            return False

    def _apply_arg(self, arg: Record):
        attr = arg.attributes()
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

    def _applicable(self, arg: Term) -> bool:
        if not isinstance(arg, Record):
            return False
        params = arg.attributes()
        if not "inherit" in params:
            return False
        if not isinstance(params["inherit"], PGSNClass):
            return False
        if "name" in params and not isinstance(params["name"], String):
            return False
        if not set(params.keys()) <= {"inherit", "name", "defaults", "attributes", "methods"}:
            return False
        if "defaults" in params and not isinstance(params["defaults"], Record):
            return False
        if "attributes" in params and not isinstance(params["attributes"], List):
            return False
        if "attributes" in params:
            if not all(isinstance(k, String) for k in params["attributes"].terms):
                return False
            if "name" in (t.value for t in params["attributes"].terms):
                return False
        if "methods" in params:
            if not isinstance(params["methods"], Record):
                return False
            if "name" in (t for t in params["methods"].attributes().keys()):
                return False
        return True

    def _apply_arg(self, arg: Record) -> Term:
        inherit: PGSNClass = arg.attributes()["inherit"]
        if "name" in arg.attributes():
            name = arg.attributes()["name"].value
        else:
            name = None
        if "defaults" in arg.attributes():
            defaults = inherit.defaults()| arg.attributes()["defaults"].attributes()
        else:
            defaults = inherit.defaults()
        if "attributes" in arg.attributes():
            attributes = (set(inherit.attributes()) |
                          set((a.value for a in arg.attributes()["attributes"].terms)))
        else:
            attributes = inherit.attributes()
        if "methods" in arg.attributes():
            methods = inherit.methods() | arg.attributes()["methods"].attributes()
        else:
            methods= inherit.methods()
        return PGSNClass.nameless(inherit=inherit, name=name, defaults=defaults, attributes=set(attributes),
                                          methods=methods)


def _is_subclass(cls1: PGSNClass, cls2: PGSNClass):
    if cls1.inherit is None:
        return False
    if cls1 == cls2:
        return True
    return _is_subclass(cls1.inherit, cls2)


def _inherit_chain(cls: PGSNClass):
    if cls.inherit is None:
        return [cls]
    else:
        return [cls] + _inherit_chain(cls.inherit)


@frozen
class IsSubclass(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]) -> bool:
        if not len(args) == 2:
            return False
        if isinstance(args[0], PGSNClass) and isinstance(args[1], PGSNClass):
            return True
        else:
            return False

    def _apply_args(self, args: tuple[PGSNClass, PGSNClass]) -> Term:
        cls1 = args[0]
        cls2 = args[1]

        return Boolean.nameless(value=_is_subclass(cls1, cls2))


@frozen
class PGSNObject(Unary):
    instance: PGSNClass = field(validator=helpers.not_none)
    _attributes: dict[str, Term] = field(validator=helpers.not_none)
    _methods: dict[str, Term] = field()

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

    def _shift(self, num: int, cutoff: int) -> Term:
        return self._traverse(lambda t: helpers.default(t.shift(num, cutoff), t))

    def _subst_or_none(self, variable: int, term: Term) -> Term | None:
        return self._traverse(lambda t: t.subst_or_none(variable, term))

    def _free_variables(self) -> set[str]:
        vars_instance = self.instance.free_variables()
        vars_attributes = set(t.free_variables() for t in self.attributes().values())
        vars_methods = set(t.free_variables() for t in self.methods().values())
        return vars_instance | vars_attributes | vars_methods

    def _applicable(self, arg: Term):
        if not isinstance(arg, String):
            return False
        k = arg.value
        if k in self.attributes().keys() or self.methods().keys():
            return True
        else:
            return False

    def _apply_arg(self, arg: String):
        k = arg.value
        if k in self.attributes().keys():
            return self.attributes()[k]
        elif k in self.methods().keys():
            return (self.methods()[k])(self)
        assert False

    def _remove_name_with_context(self, context: list[str]) -> Term:
        reduced = self._traverse(lambda t: t.remove_name_with_context(context=context))
        if reduced is None:
            return self.evolve(is_named=False)
        return reduced.evolve(is_named=False)


@frozen
class Instance(ConstMixin, Unary):

    def _applicable(self, arg: Term) -> bool:
        if isinstance(arg, PGSNObject):
            return True
        else:
            return False

    def _apply_arg(self, arg: PGSNObject) -> Term:
        return arg.instance


## Builtin Functions

# List functions

@frozen
class Cons(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term,...]):
        return isinstance(args[1], List)

    def _apply_args(self, args: tuple[Term, List]):
        return evolve(args[1], terms=(args[0],) + args[1].terms)

@frozen
class Head(ConstMixin, Unary):

    def _applicable(self, arg: Term):
        return isinstance(arg, List) and len(arg.terms) >= 1

    def _apply_arg(self, arg: List) -> Term:
        return arg.terms[0]

@frozen
class Tail(ConstMixin, Unary):

    def _applicable(self, arg: Term):
        return isinstance(arg, List) and len(arg.terms) >= 1

    def _apply_arg(self, arg: List) -> Term:
        return List.build(terms=arg.terms[1:], is_named=self.is_named)


@frozen
class Index(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term,...]):
        return isinstance(args[0], List) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term,...]) -> Term:
        return args[0].terms[args[1].value]


@frozen
class Fold(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=3, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term,...]):
        if not len(args) >= 3:
            return False
        if not isinstance(args[2], List):
            return False
        return True
    def _apply_args(self, args: tuple[Term,...]) -> Term:
        fun = args[0]
        init = args[1]
        arg_list = args[2].terms
        if len(arg_list) == 0:
            return init
        list_head = arg_list[0]
        list_rest = arg_list[1:]
        rest = List(terms=list_rest, is_named=self.is_named)
        return fun(list_head)(self(fun)(init)(rest))


@frozen
class Map(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term,...]):
        if not isinstance(args[1], List):
            return False
        return True

    def _apply_args(self, args: tuple[Term,...]) -> Term:
        fun = args[0]
        arg = args[1]
        arg_list = arg.terms
        map_list = tuple((fun(t) for t in arg_list))
        map_result = List.build(terms=map_list, is_named=self.is_named)
        return map_result


# Integer functions
@frozen
class Plus(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 2 and isinstance(args[0], Integer) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term, ...]):
        i1 = args[0].value
        i2 = args[1].value
        return Integer.nameless(value=i1 + i2)


@frozen
class Minus(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 2 and isinstance(args[0], Integer) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term, ...]):
        i1 = args[0].value
        i2 = args[1].value
        return Integer.nameless(value=i1 - i2)


@frozen
class Times(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 2 and isinstance(args[0], Integer) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term, ...]):
        i1 = args[0].value
        i2 = args[1].value
        return Integer.nameless(value=i1 * i2)


@frozen
class Div(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 2 and isinstance(args[0], Integer) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term, ...]):
        i1 = args[0].value
        i2 = args[1].value
        return Integer.nameless(value=i1 // i2)


@frozen
class Mod(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term, ...]):
        return len(args) >= 2 and isinstance(args[0], Integer) and isinstance(args[1], Integer)

    def _apply_args(self, args: tuple[Term, ...]):
        i1 = args[0].value
        i2 = args[1].value
        return Integer.nameless(value=i1 % i2)


# Control flow
@frozen
class IfThenElse(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=3, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Boolean) or isinstance(terms[0], Integer)

    def _apply_args(self, terms: tuple[Term,...]):
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

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Boolean) and terms[0].value

    def _apply_args(self, terms: tuple[Term,...]):
        return terms[1]


# Comparison. does not compare App and Abs
@frozen
class Equal(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, args: tuple[Term,...]):
        return all((not isinstance(arg, App) and not isinstance(arg, Abs) for arg in args))

    def _apply_args(self, args: tuple[Term,...]):
        return Boolean.build(is_named=self.is_named, value=args[0] == args[1])


@frozen
class HasLabel(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Record) and isinstance(terms[1], String)

    def _apply_args(self, terms: tuple[Record, String]):
        k = terms[1].value
        b = k in terms[0].attributes()
        return Boolean.build(is_named=self.is_named, value=b)


@frozen
class AddAttribute(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=3, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Record) and isinstance(terms[1], String)

    def _apply_args(self, terms: tuple[Term,...]):
        attrs = terms[0].attributes()
        attrs[terms[1].value] = terms[2]
        return Record.build(is_named=self.is_named, attributes=attrs)


@frozen
class RemoveAttribute(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Record) and isinstance(terms[1], String)

    def _apply_args(self, terms: tuple[Term,...]):
        attrs = terms[0].attributes()
        del attrs[terms[1].value]
        return Record.build(is_named=self.is_named, attributes=attrs)


@frozen
class ListLabels(ConstMixin, Unary):

    def _applicable(self, term: Term):
        return isinstance(term, Record)

    def _apply_arg(self, term: Term):
        labels = map(lambda l: String.build(is_named=self.is_named, value=l), term.attributes())
        return List.build(is_named=self.is_named, terms=tuple(labels))


@frozen
class OverwriteRecord(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        return isinstance(terms[0], Record) and isinstance(terms[1], Record)

    def _apply_args(self, terms: tuple[Term,...]):
        r1 = terms[0].attributes()
        r2 = terms[1].attributes()
        r = r1
        for k, t in r2.items():
            r[k] = t
        return Record.build(is_named=self.is_named, attributes=r)


@frozen
class Formatter(ConstMixin, Builtin):

    @classmethod
    def build(cls, is_named: bool, **kwarg) -> Term:
        return super().build(arity=2, is_named=is_named, **kwarg)

    def _applicable_args(self, terms: tuple[Term,...]):
        if not len(terms) == 2:
            return False
        if not isinstance(terms[0], String):
            return False
        if not isinstance(terms[1], Record):
            return False
        try:
            python_vals = to_python(terms[1])
            _ = terms[0].value.format(**python_vals)
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def _apply_args(self, terms: tuple[Term,...]):
        python_vals = to_python(terms[1])
        return String.build(is_named=self.is_named, value=terms[0].value.format(**python_vals))



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


def value_of(term: Term, steps=1000, with_inherit_chain=False) -> Any:
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

    # If None is returned, the reduction is terminated
    # outermost leftmost reduction.
    def reduce_or_none(self) -> Context | None:
        if isinstance(self.head, Abs) and len(self.args) > 0:
            head_substituted = (self.head.t.subst(0, self.args[0].shift(1, 0))
                                .shift(-1, 0))
            return self.evolve(head=head_substituted, args=self.args[1:])
        if isinstance(self.head, Builtin) and self.head.applicable_args(self.args):
            reduced, rest = self.head.apply_args(self.args)
            return self.evolve(head=reduced, args=rest)
        head_reduced = self.head.eval_or_none()
        if head_reduced is not None:
            return self.evolve(head=head_reduced)
        for i in range(len(self.args)):
            arg_reduced = self.args[i].eval_or_none()
            if arg_reduced is not None:
                new_args = self.args[0:i] + (arg_reduced,) + self.args[i + 1:]
                return self.evolve(args=new_args)
        else:
            return None


json_term_converter = cattrs.preconf.json.make_converter()
union_strategy = functools.partial(configure_tagged_union, tag_name="type_name")
include_subclasses(Term, json_term_converter, union_strategy=union_strategy)