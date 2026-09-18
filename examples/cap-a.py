import pprint

from pgsn.gsn import *
from pgsn.dsl import *

y = variable('y')
xs = variable('xs')
c = variable('c')

test_docs = variable('test_docs')
test_resources = variable('test_resources')
evidences = variable('evidences')

goals = variable('goals')

xs = variable('xs')

gd3 = lambda_abs(xs, let_vars((
    (test_docs, map_term(
        lambda_abs(c, evidence_as_goal(evidence(description=format_string("Test doc for {c}", c=c)))), xs)),
    (test_resources, map_term(
        lambda_abs(c, evidence_as_goal(evidence(description=format_string("Test resources for {c}", c=c)))), xs)),
    (evidences, cons(evidence_as_goal(evidence(description="E3.1...")), concat(test_docs, test_resources)))),
    goal(description="GD3: Security test is ...", context="N.D. devel. info. ...", support=immediate(evidences))))

cap_a_term = gd3(["C1", "C2", "C3"])

# (λxs.goal(dsc:“GD3: Security test is ...”,
# ctx:“N.D. devel. info. ...”,
# supp: [ev(“E3.1:...”)] + +
# map(λy.ev(“Test doc on Component {y}”), xs) + +
# map(λy.ev(“Test resource on Component {y}”), xs)))
# [C1, C2, . . . , Cn]

if __name__ == '__main__':
    cap_a_fully_eval = cap_a_term.fully_eval(steps=1000000)
    (gsn_tree(cap_a_fully_eval)).show(sorting=False)
    # n = gsn.pgsn_to_gsn(cap_a_fully_eval, steps=100000)
    # print(json.dumps(gsn.python_val(n), sort_keys=True, indent=4))
