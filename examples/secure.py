from pprint import pprint

from pgsn.gsn import *
from pgsn.dsl import python_value

g = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=evidence(description="Static analysis passed")),
            goal(description="Output sanitized",
                 support=evidence(description="Fuzzing test succeeded"))
        ]
    )
)

gsn_tree(g.fully_eval()).show(sorting=False)