from pgsn import *

# Define a custom subclass of Goal
CustomGoal = define_class(inherit=goal_class, name="GoalWithProject", attributes=["project"])

main = instantiate(CustomGoal, description="Secure connection established",
                   project='Alpha',
                   support=solution(description="Verified by audit"))
