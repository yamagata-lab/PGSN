from pprint import pprint

from pgsn.gsn import *
from pgsn.gsn import gsn_tree
import pgsn.dsl

if __name__ == '__main__':
    # サンプルとなる複雑なTermオブジェクトを組み立てる
    g = goal(
        description="System is secure",
        assumptions=[assumption(description="if properly updated")],
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

    gsn = g.fully_eval()
    # 変換関数を呼び出す
    my_tree = gsn_tree(gsn)

    # 結果を表示
    my_tree.show(sorting=False)


    dot = save_gsn(gsn, "gsn_tree", view=True)