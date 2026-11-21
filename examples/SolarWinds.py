import sys

sys.path.append("..")
import pprint
from pgsn.gsn import *

solarwinds = goal(description="Binary Repositoryが安全である",
                  support=strategy(description="Pushが安全であるためには?",
                                   #Root tree(Artifact)
                              sub_goals=[goal(description="Artifact Consumes Push が安全である",
                                               support=goal(description="各ArtifactによるConsumesが安全である",
                                                    support=strategy(description="artifactについて分解",
                                                         #Validation Data Query tree
                                                           sub_goals=[goal(description="Validation Build Reportが安全である",
                                                           support=strategy(description="Vulunarbility data Queryが安全であるためには?",
                                                                            #Carries Out Vulnarability Data Query Tree
                                                                sub_goals=[goal(description="Carries Out Vulunarbility data Queryが安全",
                                                                               support=strategy(description="resourceについて分解",
                                                                                               sub_goals=[goal(description="Tektlon Security CI/CD pipeline が安全",
                                                                                                               support=strategy(description="Uses Tektlon Security CI/CD pipeline が安全であるためには？",
                                                                                                                              sub_goals=[goal(description="Uses Resourceが安全",
                                                                                                                                              support=strategy(description="CI/CD Controller Usesが安全であるためには？",
                                                                                                                                                              sub_goals=[goal(description="P1",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="P2",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="P3",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="P4",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="P5",
                                                                                                                                                                               support=evidence(description = "none"))]
                                                                                                                                                              )
                                                                                                                                            ),
                                                                                                                                        goal(description="S1",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="S2",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="S3",
                                                                                                                                             support=evidence(description = "none"))]
                                                                                                                                     )
                                                                                                              ),
                                                                                                          goal(description="Jfrog Xray が安全",
                                                                                                               support=strategy(description="Uses Jfrog Xray が安全であるためには？",
                                                                                                                                sub_goals=[goal(description="R1",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="R2",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="R3",
                                                                                                                                             support=evidence(description = "none"))]
                                                                                                                                )
                                                                                                              )]
                                                                                               )
                                                                               ),
                                                                                #Consumes Vulunarability Data Query tree
                                                                                goal(description="Consumes Vulunarbility data Queryが安全",
                                                                                     support=strategy(description="Sourcecode Consumes が安全であるためには？",
                                                                                                sub_goals=[goal(description="Produce Sourcecodeが安全",
                                                                                                      support=strategy(description="Fetch Produce が安全であるためには？",
                                                                                                                       sub_goals=[goal(description="Consumes Fetchが安全",
                                                                                                                                              support=strategy(description="Repository Consumesが安全であるためには？",
                                                                                                                                                              sub_goals=[goal(description="A1",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="A2",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="A3",
                                                                                                                                                                               support=evidence(description = "none"))]
                                                                                                                                                              )
                                                                                                                                       ),
                                                                                                                                        goal(description="Carries Out Fetchが安全",
                                                                                                                                              support=strategy(description="GitHub Carries Outが安全であるためには？",
                                                                                                                                                              sub_goals=[goal(description="Uses Resourceが安全",
                                                                                                                                                                              support=strategy(description="Ballistaが安全であるためには？",
                                                                                                                                                                                                sub_goals=[goal(description="P1",
                                                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                                                          goal(description="P2",
                                                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                                                          goal(description="P3",
                                                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                                                          goal(description="P4",
                                                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                                                          goal(description="P5",
                                                                                                                                                                                                               support=evidence(description = "none"))]
                                                                                                                                                                                              )
                                                                                                                                                                             ),
                                                                                                                                                                          goal(description="R1",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="R2",
                                                                                                                                                                               support=evidence(description = "none")),
                                                                                                                                                                          goal(description="R3",
                                                                                                                                                                               support=evidence(description = "none"))]
                                                                                                                                                              )
                                                                                                                                            ),
                                                                                                                                       goal(description="A1",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="A2",
                                                                                                                                             support=evidence(description = "none")),
                                                                                                                                        goal(description="A3",
                                                                                                                                             support=evidence(description = "none"))]
                                                                                                                      )
                                                                                                     )]
                                                                                    )
                                                                                    ),
                                                                                goal(description="S1",
                                                                                     support=evidence(description = "none")),
                                                                                goal(description="S2",
                                                                                     support=evidence(description = "none")),
                                                                                goal(description="S3",
                                                                                     support=evidence(description = "none"))]
                                                              )
                                                              ),
                                                          #Built Binary tree
                                                         goal(description="Build Binary が安全である",
                                                              support=strategy(description="Produce Built Binaryの安全に必要なものは？",
                                                                               sub_goals=[goal(description="Vulnarability Data Query Produce Artifactが安全",
                                                                                                support=strategy(description="Vulnarability Data Queryが安全であるためには？",
                                                                                                                 #Source Code COnsumes Build tree
                                                                                                                 sub_goals=[goal(description="Source Code Consumes Buildが安全",
                                                                                                                                   support=strategy(description="Source Code Dependancy Consumesが安全であるためには？",
                                                                                                                                                    sub_goals=[goal(description="Produce Dependencyが安全",
                                                                                                                                                                        support=strategy(description="Fetch Produceが安全であるためには？",
                                                                                                                                                                                         sub_goals=[goal(description="Carries Out Fetchが安全",
                                                                                                                                                                                                          support=strategy(description="Jfrog Artifactory Carries Outが安全であるためには？",
                                                                                                                                                                                                                         sub_goals=[goal(description="Uses Jfrog Artifactoryが安全",
                                                                                                                                                                                                                                          support=strategy(description="Developer Usesが安全であるためには？",
                                                                                                                                                                                                                                                         sub_goals=[goal(description="P1",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P2",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P3",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P4",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P5",
                                                                                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                                                                                          )
                                                                                                                                                                                                                                         ),
                                                                                                                                                                                                                                    goal(description="R1",
                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                      goal(description="R2",
                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                      goal(description="R3",
                                                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                                                           )
                                                                                                                                                                                                         ),
                                                                                                                                                                                                     goal(description="S1",
                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                      goal(description="S2",
                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                      goal(description="S3",
                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                         )
                                                                                                                                                                    ),
                                                                                                                                                                goal(description="R1",
                                                                                                                                                                    support=evidence(description = "none")),
                                                                                                                                                                goal(description="R2",
                                                                                                                                                                   support=evidence(description = "none")),
                                                                                                                                                              goal(description="R3",
                                                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                                                    )
                                                                                                                                 ),
                                                                                                                             #Carries Out Build tree
                                                                                                                             goal(description="Carries Out Buildが安全",
                                                                                                                                   support=strategy(description="Uses Tektlon standard CI/CD pipelineが安全であるためには？",
                                                                                                                                                    sub_goals=[goal(description="Uses Resourceが安全",
                                                                                                                                                                        support=strategy(description="CI/CD Controller Usesが安全であるためには？",
                                                                                                                                                                                         sub_goals=[goal(description="P1",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P2",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P3",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P4",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P5",
                                                                                                                                                                                                          support=evidence(description = "none"))]
                                                                                                                                                                                         )
                                                                                                                                                                    ),
                                                                                                                                                                goal(description="R1",
                                                                                                                                                                    support=evidence(description = "none")),
                                                                                                                                                                goal(description="R2",
                                                                                                                                                                   support=evidence(description = "none")),
                                                                                                                                                                goal(description="R3",
                                                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                                                    )
                                                                                                                                  ),
                                                                                                                             goal(description="S1",
                                                                                                                                   support=evidence(description = "none")),
                                                                                                                             goal(description="S2",
                                                                                                                                   support=evidence(description = "none")),
                                                                                                                             goal(description="S3",
                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                 )
                                                                                               ),
                                                                                            goal(description="A1",
                                                                                                 support=evidence(description = "none")),
                                                                                            goal(description="A2",
                                                                                                 support=evidence(description = "none")),
                                                                                            goal(description="A3",
                                                                                                 support=evidence(description = "none"))]
                                                                              )
                                                             ),
                                                          #Build Container Image tree
                                                          goal(description="Build Container Image が安全である",
                                                              support=strategy(description="Produce Built Container imagesの安全に必要なものは？",
                                                                                sub_goals=[goal(description="Vulnarability Data Query Produce Artifactが安全",
                                                                                                support=strategy(description="Vulnarability Data Queryが安全であるためには？",
                                                                                                                 #Source Code COnsumes Build tree
                                                                                                                 sub_goals=[goal(description="Source Code Consumes Buildが安全",
                                                                                                                                   support=strategy(description="Source Code Dependancy Consumesが安全であるためには？",
                                                                                                                                                    sub_goals=[goal(description="Produce Dependencyが安全",
                                                                                                                                                                        support=strategy(description="Fetch Produceが安全であるためには？",
                                                                                                                                                                                         sub_goals=[goal(description="Carries Out Fetchが安全",
                                                                                                                                                                                                          support=strategy(description="Jfrog Artifactory Carries Outが安全であるためには？",
                                                                                                                                                                                                                         sub_goals=[goal(description="Uses Jfrog Artifactoryが安全",
                                                                                                                                                                                                                                          support=strategy(description="Developer Usesが安全であるためには？",
                                                                                                                                                                                                                                                         sub_goals=[goal(description="P1",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P2",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P3",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P4",
                                                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                                                      goal(description="P5",
                                                                                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                                                                                          )
                                                                                                                                                                                                                                         ),
                                                                                                                                                                                                                                    goal(description="R1",
                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                      goal(description="R2",
                                                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                                                      goal(description="R3",
                                                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                                                           )
                                                                                                                                                                                                         ),
                                                                                                                                                                                                     goal(description="S1",
                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                      goal(description="S2",
                                                                                                                                                                                                           support=evidence(description = "none")),
                                                                                                                                                                                                      goal(description="S3",
                                                                                                                                                                                                           support=evidence(description = "none"))]
                                                                                                                                                                                         )
                                                                                                                                                                    ),
                                                                                                                                                                goal(description="R1",
                                                                                                                                                                    support=evidence(description = "none")),
                                                                                                                                                                goal(description="R2",
                                                                                                                                                                   support=evidence(description = "none")),
                                                                                                                                                              goal(description="R3",
                                                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                                                    )
                                                                                                                                 ),
                                                                                                                             #Carries Out Build tree
                                                                                                                             goal(description="Carries Out Buildが安全",
                                                                                                                                   support=strategy(description="Uses Tektlon standard CI/CD pipelineが安全であるためには？",
                                                                                                                                                    sub_goals=[goal(description="Uses Resourceが安全",
                                                                                                                                                                        support=strategy(description="CI/CD Controller Usesが安全であるためには？",
                                                                                                                                                                                         sub_goals=[goal(description="P1",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P2",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P3",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P4",
                                                                                                                                                                                                          support=evidence(description = "none")),
                                                                                                                                                                                                     goal(description="P5",
                                                                                                                                                                                                          support=evidence(description = "none"))]
                                                                                                                                                                                         )
                                                                                                                                                                    ),
                                                                                                                                                                goal(description="R1",
                                                                                                                                                                    support=evidence(description = "none")),
                                                                                                                                                                goal(description="R2",
                                                                                                                                                                   support=evidence(description = "none")),
                                                                                                                                                                goal(description="R3",
                                                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                                                    )
                                                                                                                                  ),
                                                                                                                             goal(description="S1",
                                                                                                                                   support=evidence(description = "none")),
                                                                                                                             goal(description="S2",
                                                                                                                                   support=evidence(description = "none")),
                                                                                                                             goal(description="S3",
                                                                                                                                   support=evidence(description = "none"))]
                                                                                                                 )
                                                                                               ),
                                                                                            goal(description="A1",
                                                                                                 support=evidence(description = "none")),
                                                                                            goal(description="A2",
                                                                                                 support=evidence(description = "none")),
                                                                                            goal(description="A3",
                                                                                                 support=evidence(description = "none"))]
                                                                              )
                                                                      )]
                                                                    )
                                                   )
                                             ),
                                         #Resource Carries Out tree
                                         goal(description="Resources Carries Out Pushが安全である",                                                    
                                              support=strategy(description="Resourceについて分解",
                                                               #AmazonECR tree
                                                               sub_goals=[goal(description="AmazonECR が安全である",
                                                                               support=strategy(description="Uses AmazonECRが安全であるためには?",
                                                                                                sub_goals=[goal(description="Uses Resources が安全である",
                                                                                                                support=strategy(description="CI/CD Controller Usesが安全であるためには?",
                                                                                                                                 sub_goals=[goal(description="P1",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P2",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P3",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P4",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P5",
                                                                                                                                                support=evidence(description = "none"))]
                                                                                                                                 )
                                                                                                                 ),
                                                                                                            goal(description="R1",
                                                                                                                support=evidence(description = "none")),
                                                                                                            goal(description="R2",
                                                                                                                support=evidence(description = "none")),
                                                                                                            goal(description="R3",
                                                                                                                support=evidence(description = "none"))]
                                                                                               )
                                                                               ),
                                                                           #AmazonS3 tree
                                                                           goal(description="AmazonS3 が安全である",
                                                                               support=strategy(description="Uses AmazonS3が安全であるためには?",
                                                                                                sub_goals=[goal(description="Uses Resources が安全である",
                                                                                                                support=strategy(description="CI/CD Controller Usesが安全であるためには?",
                                                                                                                                 sub_goals=[goal(description="P1",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P2",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P3",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P4",
                                                                                                                                                support=evidence(description = "none")),
                                                                                                                                             goal(description="P5",
                                                                                                                                                support=evidence(description = "none"))]
                                                                                                                                 )
                                                                                                                 ),
                                                                                                            goal(description="R1",
                                                                                                                support=evidence(description = "none")),
                                                                                                            goal(description="R2",
                                                                                                                support=evidence(description = "none")),
                                                                                                            goal(description="R3",
                                                                                                                support=evidence(description = "none"))]
                                                                                               )
                                                                               )]
                                                              )
                                             ),
                                         goal(description="S1",
                                              support=evidence(description = "none")),
                                         goal(description="S2",
                                              support=evidence(description = "none")),
                                         goal(description="S3",
                                              support=evidence(description = "none"))]
                                  )
                 )
if __name__ == '__main__':
    # n = gsn.pgsn_to_gsn(evidence_class, steps=10000)
    # print(json.dumps(gsn.python_val(n), sort_keys=True, indent=4))
    #print(s('sub_goals').fully_eval())
    SolarWinds = solarwinds.fully_eval()
    pprint.pprint(pgsn.dsl.python_value(SolarWinds))
    # n = gsn.pgsn_to_gsn(SolarWinds, steps=10000)
    # js = json.dumps(gsn.python_val(n), sort_keys=True, indent=4)
    # print(js)
    #