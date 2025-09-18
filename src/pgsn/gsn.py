import uuid
from treelib import Tree
import treelib
import graphviz

import pgsn.dsl
import pgsn.pgsn_term

gsn_class = pgsn.dsl.define_class(inherit=pgsn.dsl.base_class,
                                     name='GSN_Node',
                                     attributes=["description"])

support_class = pgsn.dsl.define_class(inherit=gsn_class, name='Support')
undeveloped_class = pgsn.dsl.define_class(inherit=support_class,
                                          name='Undeveloped',
                                          defaults={"description": ""})
undeveloped = undeveloped_class()
evidence_class = pgsn.dsl.define_class(inherit=support_class, name='Evidence')
strategy_class = pgsn.dsl.define_class(inherit=support_class, name='Strategy',
                                          attributes=["sub_goals"])

goal_class = pgsn.dsl.define_class(inherit=gsn_class,
                                      name='Goal',
                                      attributes=["assumptions", "contexts", "support"],
                                      defaults={"assumptions":[], "contexts": [], "support": undeveloped}
                                      )
assumption_class = pgsn.dsl.define_class(inherit=gsn_class, name='Assumption')
context_class = pgsn.dsl.define_class(inherit=gsn_class, name='Context')

_d = pgsn.dsl.variable('x')
_support = pgsn.dsl.variable('support')
_assumptions = pgsn.dsl.variable('assumptions')
_contexts = pgsn.dsl.variable('contexts')
_sub_goals = pgsn.dsl.variable('sub_goals')

evidence = pgsn.dsl.lambda_abs_keywords(arguments={'description': _d},
                                           body=evidence_class(description=_d))
strategy = pgsn.dsl.lambda_abs_keywords(arguments={'description': _d, 'sub_goals': _sub_goals},
                                           body=strategy_class
                               (description=_d, sub_goals=_sub_goals))
goal = pgsn.dsl.lambda_abs_keywords(arguments={'description': _d,
                                      'assumptions': _assumptions,
                                      'contexts': _contexts,
                                      'support': _support},
                                       defaults=pgsn.dsl.record({
                               'assumptions': pgsn.dsl.empty,
                               'contexts': pgsn.dsl.empty}),
                                       body=goal_class(description=_d,
                                                       contexts=_contexts,
                                                       assumptions=_assumptions,
                                                       support=_support))
assumption = pgsn.dsl.lambda_abs_keywords(arguments={'description': _d},
                                             body=assumption_class(description=_d))
context = pgsn.dsl.lambda_abs_keywords(arguments={'description': _d},
                                          body=context_class(description=_d))

_goals = pgsn.dsl.variable('goals')
immediate = pgsn.dsl.lambda_abs(_goals, strategy(description="immediate", sub_goals=_goals))

_evd = pgsn.dsl.variable('evidence')
evidence_as_goal = pgsn.dsl.lambda_abs(_evd, goal(description=_evd('description'), support=_evd))

# Keys for lists that should be hidden if empty
GSN_KEYS_TO_HIDE_IF_EMPTY = {"contexts", "assumptions"}

# Keys for lists whose children should be attached directly to the parent
GSN_KEYS_TO_FLATTEN = {"support", "sub_goals", "contexts", "assumptions"}
GSN_TYPES = {"Goal", "Strategy", "Evidence", "Context", "Assumption", "Undeveloped"}


# Term and to_python are assumed to be in your module
# from your_module import Term, to_python

def gsn_tree(root_term: pgsn.pgsn_term.Term) -> Tree:
    tree = Tree()
    py_data = pgsn.dsl.python_value(root_term)

    def _add_nodes(data, parent_id=None, key_name="root"):

        # Hide specific GSN keys if their list is empty
        if key_name in GSN_KEYS_TO_HIDE_IF_EMPTY and isinstance(data, list) and not data:
            return

        node_id = str(uuid.uuid4())

        if isinstance(data, dict):
            # (Dictionary processing logic remains the same)
            has_meaningful_keys = any(not (k.startswith('__') and k.endswith('__')) for k in data)
            class_name_key = next((k for k in data if k.startswith('__') and k.endswith('__')), None)
            class_name = class_name_key.strip('_') if class_name_key is not None else None

            if not has_meaningful_keys:
                node_tag = f"{key_name}: {{}}"
            elif class_name_key:
                # special handling for GSN node
                if class_name in GSN_TYPES:
                    description = data["description"] if "description" in data else ""
                    node_tag = f"{class_name}: {description}"
                else:
                    node_tag = f"{key_name}: <{class_name}>"
            else:
                node_tag = f"{key_name}: <Record>"

            tree.create_node(tag=node_tag, identifier=node_id, parent=parent_id)

            for key, value in data.items():
                if class_name in GSN_TYPES and key=="description":
                    continue
                if not (key.startswith('__') and key.endswith('__')):
                    # Special handling to flatten key
                    if key in GSN_KEYS_TO_FLATTEN and isinstance(value, list):
                        for item in value:
                            # Attach each item directly to the parent (node_id)
                            _add_nodes(item, parent_id=node_id, key_name=key)
                    else:
                        _add_nodes(value, parent_id=node_id, key_name=key)

        elif isinstance(data, list):
            # (List handling logic remains the same)
            if not data:
                node_tag = f"{key_name}: [List] = []"
            else:
                node_tag = f"{key_name}: [List]"

            tree.create_node(tag=node_tag, identifier=node_id, parent=parent_id)

            for i, item in enumerate(data):
                _add_nodes(item, parent_id=node_id, key_name=f"[{i}]")

        else:
            node_tag = f"{key_name}: {data}"
            tree.create_node(tag=node_tag, identifier=node_id, parent=parent_id)

    _add_nodes(py_data)
    return tree


GSN_SHAPES = {
        'Goal': 'box',
        'Strategy': 'parallelogram',
        'Evidence': 'ellipse',  # Evidenceは円で表現することが多い
        'Solution': 'ellipse',  # Solutionも円で
        'Context': 'box',  # 本来は角丸だけど、まずは四角で
        'Assumption': 'ellipse',
        'Undeveloped': 'diamond'
    }



def gsn_dot(gsn: pgsn.pgsn_term.Term, layout_attrs: dict[str]=None) -> graphviz.Digraph:
    """
    treelib.Treeオブジェクトを受け取り、GSNのルールに基づいて
    ノードの形をカスタマイズしたdotファイルを生成する。
    """
    tree = gsn_tree(gsn)

    # GSNのタイプとgraphvizのshapeを対応付ける辞書
    default_layout = {
        "rankdir": "TB",
        "splines": "spline",
        "nodesep": "0.6",
        "ranksep": "1.2"
    }
    if layout_attrs:
        default_layout.update(layout_attrs)

    dot = graphviz.Digraph('GSN', comment='Goal Structuring Notation')
    # 見た目を整えるための設定
    dot.attr(**default_layout)

    # tree内のすべてのノードをたどる
    # 水平に並べたいノードのペアを記録しておくリスト
    horizontal_pairs = []
    for node in tree.expand_tree(mode=treelib.Tree.DEPTH):
        node_obj = tree.get_node(node)
        tag = node_obj.tag

        # tagからGSNタイプとラベルを抽出する
        node_type = 'Default'
        node_label = tag

        if ': ' in tag:
            parts = tag.split(': ', 1)
            # parts[0]がGSN_TYPESに含まれているかチェック
            if parts[0] in GSN_TYPES:
                node_type = parts[0]
                node_label = parts[1]

        # GSNタイプに基づいて形を決定する
        shape = GSN_SHAPES.get(node_type, 'box')  # GSNタイプでなければデフォルトで四角
        style = ''
        if node_type == 'Context':
            # Contextのときだけ、styleを'rounded'に設定する
            style = 'rounded'

        # ノードをdotオブジェクトに追加するときに、styleも渡してあげる
        dot.node(
            name=node_obj.identifier,
            label=f"{node_type}\n{node_label}",
            shape=shape,
            style=style  # styleを追加
        )


        if not node_obj.is_root():
            parent_id = node_obj.predecessor(tree.identifier)

            if node_type in ('Assumption', 'Context'):
                # 矢印の向きを逆にする魔法だけをかける
                dot.edge(parent_id, node_obj.identifier, dir='back')

                # 水平にしたいペアとして、親と自分を記録しておく
                horizontal_pairs.append((parent_id, node_obj.identifier))
            else:
                dot.edge(parent_id, node_obj.identifier)

    # --- ここからが、新しい言霊を紡ぐ部分 ---
    # ループが終わった後で、記録しておいたペアに、まとめて魔法をかける
    for parent, child in horizontal_pairs:
        # dot.bodyに、{ rank=same; "親ID"; "子ID" } という文字列を直接追加する
        dot.body.append(f'{{ rank=same; "{parent}"; "{child}" }}')

    return dot


def save_gsn(gsn: pgsn.pgsn_term.Term,
             filename: str,
             image_format: str = "png",
             view=False,
             cleanup=True):

    dot = gsn_dot(gsn)
    dot.render(filename, view=view, format=image_format, cleanup=cleanup)

