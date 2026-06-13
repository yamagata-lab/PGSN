from __future__ import annotations

import json

from pgsn.pgsn_term import *

###########################
# DSL API
# Enough for everyday use
###########################


format_string = Formatter.named()


# Interface by lambda terms
# identifiers starting _ is reserved for internal uses.
def variable(name: str) -> Variable:
    return Variable.named(name=name)


_x = variable('x')
_y = variable('y')
_z = variable('z')
_w = variable('w')
_f = variable('f')
_label = variable('label')


def constant(name: str) -> Term:
    return Constant.named(name=name)


undefined = constant('undefined')


# let var = t1 in t2
def let(var: Variable, t1: Term, t2: Term):
    return (lambda_abs(var, t2))(t1)


# let v1 = t1, v2 = t2, ... in t
def let_vars(assigns: tuple[tuple[Variable, Term],...], t: Term):
    for v, t1 in reversed(assigns):
        t = let(v, t1, t)
    return t


# fixed point operator
# fixed point operator
def lambda_abs(v: Variable, t: Term) -> Term:
    return Abs.named(v=v, t=t)


fix = lambda_abs(_f,
                 lambda_abs(_x, _f(_x(_x)))(lambda_abs(_x, _f(_x(_x))))
                 )

# Boolean related
def boolean(b: bool) -> Boolean:
    return Boolean.named(value=b)


true = boolean(True)
false = boolean(False)
if_then_else = IfThenElse.named()
guard = Guard.named()


def lambda_abs_vars(vs: tuple[Variable,...], t) -> Term:
    t1 = t
    for v in reversed(vs):
        t1 = lambda_abs(v, t1)
    return t1


boolean_and = lambda_abs_vars(
    (_x, _y),
    if_then_else(_x)(_y)(false)
)
boolean_or = lambda_abs_vars(
    (_x, _y),
    if_then_else(_x)(true)(_y)
)
boolean_not = lambda_abs(_x, if_then_else(_x)(false)(true))

equal = Equal.named()


# Integer related
plus = Plus.named()
minus = Minus.named()
times = Times.named()
div = Div.named()
mod = Mod.named()

_repeat = variable("repeat")
_num = variable("num")
_acc = variable("accumulator")

_F = lambda_abs_vars((_repeat, _f, _acc, _num),
                     if_then_else(equal(_num)(0))
                     (_acc)
                     (_f(_repeat(_f, _acc, minus(_num, 1))))
                     )
repeat = fix(_F)

# List related
cons = Cons.named()
head = Head.named()
tail = Tail.named()
index = Index.named()
#fold = Fold.named()
map_term = Map.named()

_elem = variable('elem')
_list = variable('list')
_acc = variable('acc')
_foldr = variable('_foldr')
empty: List = List.named(terms=tuple())
_F = lambda_abs_vars((_foldr, _f, _acc, _list),
                     if_then_else(equal(_list)(empty))
                     (_acc)
                     (_f(head(_list))(_foldr(_f)(_acc)(tail(_list))) )
                     )
foldr = fix(_F)
fold = foldr

_list1 = variable('list1')
_list2 = variable('list2')
concat = lambda_abs_vars(
    (_list1, _list2),
    foldr(lambda_abs_vars((_elem, _acc), cons(_elem)(_acc)), _list2, _list1))

list_all = lambda_abs_vars(
    (_x, _y),
    let(
        _f,
        lambda_abs_vars((_z, _w), boolean_and(_x(_z))(_w)),
        fold(_f)(_y)(true)
    )
)


def integer(i: int) -> Integer:
    return Integer.named(value=i)


integer_sum = fold(plus)(integer(0))


# Record
def record(d: dict[str, Term]):
    return Record.named(attributes=d)


empty_record = record({})
has_label = HasLabel.named()
list_labels = ListLabels.named()
add_attribute = AddAttribute.named()
remove_attribute = RemoveAttribute.named()
overwrite_record = OverwriteRecord.named()


# keyword_args_function
def lambda_abs_keywords(arguments: dict[str,Variable],
                        body: Term,
                        defaults: Record = empty_record) -> Term:
    sorted_arguments = sorted(arguments.items(), key=lambda x: x[0])
    variables = tuple((v for _, v in sorted_arguments))
    t = lambda_abs_vars(variables, body)
    _args = variable('args')
    for k, _ in sorted_arguments:
        _k = string(k)
        t = t(_args(_k))
    return lambda_abs(_args, let(_args, overwrite_record(defaults)(_args), t))


def string(s: str) -> String:
    return String.named(value=s)


def list_term(terms: tuple[Term,...]) -> List:
    return List.named(terms=terms)


### internal variables
_obj = variable("_obj")
_class = variable("_class")
_attrs = variable("_attrs")

### OO programming
ClassTerm = PGSNClass
ObjectTerm = PGSNObject

## Class

# inheritance
base_class = PGSNClass.named(name="BaseClass")
define_class = DefineClass.named()

# subclass
is_subclass = IsSubclass.named()

## Objects
instance = Instance.named()
is_instance = lambda_abs_vars((_obj, _class), is_subclass(instance(_obj))(_class))
instantiate = lambda_abs_vars((_class, _attrs), _class(_attrs))


def python_value(obs: Term, with_inherit_chain=False):
    return to_python(obs, with_inherit_chain=with_inherit_chain)


def json_dumps(t: Term, **kwargs) -> str:

    d = json_term_converter.unstructure(t, unstructure_as=Term)
    return json.dumps(d, **kwargs)


def json_loads(s: str, **kwargs) -> Term:
    d = json.loads(s, **kwargs)
    return json_term_converter.structure(d, Term)