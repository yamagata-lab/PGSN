from pgsn import *

requirements = ["Firewall enabled", "Encrypted communication", "Access control active"]


goal_template = lambda_abs(variable("desc"),
    goal(description=variable("desc"),
         support=solution(description=variable("desc")))
)

goals = map_term(goal_template, requirements)

main = goal(
    description="Security requirements fulfilled",
    support=immediate(goals)
)
