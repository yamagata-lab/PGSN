from pgsn.gsn import *

g = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=undeveloped),
            goal(description="Output sanitized",
                 support=evidence(description="Fuzzing test succeeded"))
        ]
    )
)

gsn_tree(g.fully_eval()).show()
dot = save_gsn(g.fully_eval(), "gsn_tree", view=True)