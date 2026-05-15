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


import uuid

# Tree と pgsn は君のモジュールでインポートされている前提だね

def gsn_tree(root_term: pgsn.pgsn_term.Term) -> Tree:
    tree = Tree()
    # 継承チェーンを含めてPythonの辞書に変換
    py_data = pgsn.dsl.python_value(root_term, with_inherit_chain=True)

    def _add_nodes(data, parent_id=None, key_name="root"):
        node_id = str(uuid.uuid4())

        if isinstance(data, dict):
            # 血脈（親クラスのリスト）を取り出す
            parent_classes = data.get("__parent_classes__", [])

            # その血脈の中に、GSN_TYPES に該当する起源があるかを探す
            gsn_type = next((cls for cls in parent_classes if cls in GSN_TYPES), None)

            # 実際のクラス名（派生クラス名。GSN以外のオブジェクト表示用として残す）
            class_name_key = next(
                (k for k in data if k.startswith('__') and k.endswith('__') and k != '__parent_classes__'), None)
            class_name = class_name_key.strip('_') if class_name_key is not None else None

            has_meaningful_keys = any(not (k.startswith('__') and k.endswith('__')) for k in data)

            # --- ノードのタグ（表示名）の決定 ---
            if gsn_type:
                description = data.get("description", "")
                # 【変更点】class_name（派生クラス）ではなく、gsn_type（祖先クラス）を表示する
                node_tag = f"{gsn_type}: {description}"
            elif class_name_key:
                # GSNの血脈は持たない純粋なPGSNObjectの場合
                node_tag = f"{key_name}: <{class_name}>"
            elif not has_meaningful_keys:
                node_tag = f"{key_name}: {{}}"
            else:
                node_tag = f"{key_name}: <Record>"

            tree.create_node(tag=node_tag, identifier=node_id, parent=parent_id)

            for key, value in data.items():
                if key.startswith('__') and key.endswith('__'):
                    continue

                if gsn_type and key == "description":
                    continue

                if key in GSN_KEYS_TO_FLATTEN and isinstance(value, list):
                    for item in value:
                        _add_nodes(item, parent_id=node_id, key_name=key)
                else:
                    _add_nodes(value, parent_id=node_id, key_name=key)

        elif isinstance(data, list):
            if not data:
                node_tag = f"{key_name}: [List] =[]"
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
        'Strategy': 'polygon',
        'Evidence': 'ellipse',  # Evidenceは円で表現することが多い
        'Solution': 'ellipse',  # Solutionも円で
        'Context': 'box',  # 本来は角丸だけど、まずは四角で
        'Assumption': 'ellipse',
        'Undeveloped': 'diamond'
    }


def gsn_dot(gsn: pgsn.pgsn_term.Term, layout_attrs: dict[str] = None) -> graphviz.Digraph:
    """
    treelib.Treeオブジェクトを受け取り、GSNのルールに基づいて
    ノードの形をカスタマイズしたdotファイルを生成する。
    """
    tree = gsn_tree(gsn)

    default_layout = {
        "rankdir": "TB",
        "splines": "line",
        "nodesep": "0.6",
        "ranksep": "1.2"
    }
    if layout_attrs:
        default_layout.update(layout_attrs)

    dot = graphviz.Digraph('GSN', comment='Goal Structuring Notation')
    dot.attr(**default_layout)

    horizontal_pairs = []
    skipped_nodes = set()  # 親の箱に吸収された属性ノードのIDを記録

    for node in tree.expand_tree(mode=treelib.Tree.DEPTH):
        # すでに親の箱に吸収されたノードは、独立した箱として描かない
        if node in skipped_nodes:
            continue

        node_obj = tree.get_node(node)
        tag = node_obj.tag

        node_type = None  # 'Default'という仮の名前は捨てる
        node_label = tag

        if ': ' in tag:
            parts = tag.split(': ', 1)
            # parts[0]がGSN_TYPESに含まれているかチェック
            if parts[0] in GSN_TYPES:
                node_type = parts[0]
                node_label = parts[1]

        # --- 子ノードを覗き込んで、単なる属性なら親の箱の中に吸収する ---
        children = tree.children(node)
        attr_lines = []
        for child in children:
            child_tag = child.tag
            child_parts = child_tag.split(': ', 1)
            is_gsn = len(child_parts) > 1 and child_parts[0] in GSN_TYPES

            # GSNノードではなく、かつ子を持たない「葉っぱ」のノード（数値やBooleanも含む）の場合
            if not is_gsn and child.is_leaf():
                attr_lines.append(child_tag)
                skipped_nodes.add(child.identifier)

        # 吸収した属性があれば、ラベルの文字列に改行(\n)で合体させる
        if attr_lines:
            node_label += "\n" + "\n".join(attr_lines)
        # -------------------------------------------------------------------------

        # GSNタイプに基づいて形を決定する（GSN以外は単なる四角形）
        shape = GSN_SHAPES.get(node_type, 'box') if node_type else 'box'
        style = ''
        node_attrs = {}

        if node_type == 'Context':
            style = 'rounded'
        elif node_type == 'Strategy':
            node_attrs['sides'] = '4'
            node_attrs['skew'] = '0.3'
            node_attrs['margin'] = '0'

        # ラベルの最終決定（GSNならタイプ名を見出しにし、それ以外はタグをそのまま使う）
        final_label = f"{node_type}\n{node_label}" if node_type else node_label

        dot.node(
            name=node_obj.identifier,
            label=final_label,
            shape=shape,
            style=style,
            **node_attrs
        )

        edge_attrs = {}
        if not node_obj.is_root():
            parent_id = node_obj.predecessor(tree.identifier)
            parent_node_obj = tree.get_node(parent_id)
            parent_tag_parts = parent_node_obj.tag.split(': ', 1)
            parent_node_type = parent_tag_parts[0] if len(parent_tag_parts) > 1 else 'Default'

            if node_type in ('Assumption', 'Context'):
                edge_attrs['dir'] = 'back'
                horizontal_pairs.append((parent_id, node_obj.identifier))

            if parent_node_type == 'Goal' and node_type == 'Evidence':
                edge_attrs['tailport'] = 's'
                edge_attrs['headport'] = 'n'
                edge_attrs['weight'] = '10'

            dot.edge(parent_id, node_obj.identifier, **edge_attrs)

    # まとめて水平配置の魔法をかける
    for parent, child in horizontal_pairs:
        dot.body.append(f'{{ rank=same; "{parent}"; "{child}" }}')

    return dot

def save_gsn(gsn: pgsn.pgsn_term.Term,
             filename: str,
             image_format: str = "png",
             view=False,
             cleanup=True):

    dot = gsn_dot(gsn)
    dot.render(filename, view=view, format=image_format, cleanup=cleanup)

