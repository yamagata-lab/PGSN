import pprint

from typeguard import install_import_hook

import pgsn.dsl
import pgsn.gsn

install_import_hook('robot')

install_import_hook('gsn')
install_import_hook('gsn')
install_import_hook('helpers')
install_import_hook('dsl')
install_import_hook('stdlib')

robot = pgsn.gsn.goal(description="There is no known vulnerability in the robot",
                           support=pgsn.gsn.strategy(description="Argument over each vulnerability",
                                                          sub_goals=[
                                  pgsn.gsn.goal(description="Vulnerability A is not exploited",
                                                     support=pgsn.gsn.evidence(description="Test results")),
                                  pgsn.gsn.goal(description="Vulnerability B is not exploited",
                                                     support=pgsn.gsn.evidence(description="Test results"))
                              ]
                                                          )
                           )


s = pgsn.gsn.strategy(description="Argument over each vulnerability",
                                                          sub_goals=[
                                  pgsn.gsn.goal(description="Vulnerability A is not exploited",
                                                     support=pgsn.gsn.evidence(description="Test results")),
                                  pgsn.gsn.goal(description="Vulnerability B is not exploited",
                                                     support=pgsn.gsn.evidence(description="Test results"))
                              ]
                                                          )

pprint.pprint(pgsn.dsl.python_value(pgsn.gsn.evidence(description="Test results").fully_eval()), indent=2)

e1 = pgsn.gsn.evidence(description="Test results")
pprint.pprint(pgsn.dsl.to_python(e1.fully_eval()), indent=2)

g1 = pgsn.gsn.goal(description="Vulnerability A is not exploited",
                                                     support=pgsn.gsn.evidence(description="Test results"))
pprint.pprint(pgsn.dsl.to_python(g1.fully_eval()), indent=2)

pprint.pprint(pgsn.dsl.to_python(s.fully_eval()), indent=2)
pprint.pprint(pgsn.dsl.to_python(robot.fully_eval()), indent=2)


pprint.pprint(pgsn.dsl.to_python(robot.fully_eval()), indent=2)

web_server = pgsn.gsn.goal(description="The server can deal with DoS attacks on the server",
                                support=pgsn.gsn.evidence(description="Access restriction"))

system = pgsn.gsn.goal(description="The robot does not make unintended movements",
                            support=pgsn.gsn.strategy(description="Argument over the robot and the server",
                                                           sub_goals=[
                                   pgsn.gsn.goal(description="The robot behaves according to commands",
                                                      support=pgsn.gsn.strategy(description="Argument over each threat",
                                                                                     sub_goals=[robot]
                                                                                     )),
                                   pgsn.gsn.goal(description="The server gives correct commands to the robot",
                                                      support=pgsn.gsn.strategy(description="Argument over each threat",
                                                                                     sub_goals=[web_server])
                                                      )
                               ]
                                                           )
                            )

if __name__ == '__main__':
    system_evaluated = system.fully_eval()
    pgsn.gsn.gsn_tree(system_evaluated).show(sorting=False)
    # n = gsn.pgsn_to_gsn(system_evaluated, steps=1)
    # js = json.dumps(gsn.python_val(n), sort_keys=True, indent=4)
    # print(js)
