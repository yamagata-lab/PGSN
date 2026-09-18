from pprint import pprint

from pgsn.dsl import *
from pgsn.gsn import *

# Define a custom subclass of Goal
CustomGoal = define_class(inherit=goal_class, name="GoalWithProject", attributes=["project"])

g = instantiate(CustomGoal, description="Secure connection established",
                project='Alpha',
                support=evidence(description="Verified by audit"))

gsn_tree(g.fully_eval()).show(sorting=False)