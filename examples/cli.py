from pgsn.gsn import *

main = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=solution(description="Static analysis passed")),
            goal(description="Output sanitized",
                 support=solution(description="Fuzzing test succeeded"))
        ]
    )
)
