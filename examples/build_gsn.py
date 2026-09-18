import json
from pprint import pprint
from typing import Dict, List, Optional, Tuple

from pgsn.dsl import *
from pgsn.gsn import goal, evidence, context, strategy, assumption, undeveloped
import pgsn

SUPPORT_PRIORITY = ["Strategy", "Evidence", "Goal", "Assumption", "Undeveloped"]


def build_gsn_from_json(json_path: str) -> Tuple[list[object], dict[str, object]]:

    with open(json_path, mode = "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes: Dict[str, dict] = {n["id"]: n for n in data["nodes"]}
    edges: List[dict] = data["edges"]

    children: Dict[str, List[str]] = {}
    for e in edges:
        children.setdefault(e["from"], []).append(e["to"])

    parents: Dict[str, List[str]] = {}
    for e in edges:
        parents.setdefault(e["to"], []).append(e["from"])

    node_objs: Dict[str, object] = {}

    def get_desc(n: dict) -> str:
        return (n.get("description") or "").replace('"', '¥¥')
    
    def emit(nid: str):

        if nid in node_objs:
            return node_objs[nid]
        
        node = nodes[nid]
        typ = node["gsn_type"]

        if typ == "Context":
            obj = context(description = get_desc(node))

        elif typ == "Evidence":
            obj = evidence(description = get_desc(node))

        elif typ == "Assumption":
            obj = assumption(description = get_desc(node))
        
        elif typ == "Undeveloped":
            obj = undeveloped()

        elif typ == "Strategy":
            sub_goal_ids = [
                cid for cid in children.get(nid, []) if nodes[cid]["gsn_type"] == "Goal"
            ]
            sub_goals = [emit(cid) for cid in sub_goal_ids]
            obj = strategy(description=get_desc(node), sub_goals=sub_goals)

        elif typ == "Goal":
            sub_cids = children.get(nid, [])
            sub_pids = parents.get(nid, [])


            ctx_id: Optional[str] = next(
                (pid for pid in sub_pids if nodes[pid]["gsn_type"] == "Context"),
                None
            )
    

            ctx_obj = emit(ctx_id) if ctx_id else None

           


            support_id: Optional[str] = None
            for t in SUPPORT_PRIORITY:
                cid = next((cid for cid in sub_cids if nodes[cid]["gsn_type"] == t), None)
                if cid is not None:
                    support_id = cid
                    break
            support_obj = emit(support_id) if support_id else None

            kwargs = {"description": get_desc(node)}
            if ctx_obj is not None:
                kwargs["contexts"] = [ctx_obj]
            if support_obj is not None:
                kwargs["support"] = support_obj
            #
            # print(kwargs)

            obj = goal(**kwargs)

            obj2 = goal(description = "2", contexts = ["2は2である"], support = evidence(description="2は正しい"))
            # pprint(python_value(obj.fully_eval()))
            # pprint(python_value(obj2.fully_eval()))



        else :
            raise ValueError(f"Unsupported node type: {typ} (id: {nid})")
        
        node_objs[nid] = obj
        return obj
    
    def is_top_goal(nid: str) -> bool:
        if nodes[nid]["gsn_type"] != "Goal":
            return False
        non_ctx_parents = [
            pid for pid in parents.get(nid, [])
            if nodes[pid]["gsn_type"] != "Context"
        ]
        return len(non_ctx_parents) == 0
    
    top_goal_ids = [nid for nid in nodes if is_top_goal(nid)]

    tops = [emit(tid) for tid in top_goal_ids]
    return tops, node_objs


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="GSN構造のJSONからオブジェクトを生成し、評価結果を表示します"
    )
    parser.add_argument("json_path", help = "入力GSN JSONファイルパス")
    args = parser.parse_args()

    tops, _nodes_objs = build_gsn_from_json(args.json_path)

    if not tops:
        print("No top-level Goal found.")
        return
    
    for i, top in enumerate(tops, 1):
        if len(tops) > 1:
            print(f"¥n=== Top-level Goal #{i} ===")
        (pgsn.gsn.gsn_tree(top.fully_eval())).show(sorting=False)

if __name__ == "__main__":
    main()




    
