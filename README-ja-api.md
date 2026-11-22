# PGSN Python API

サポート対象の機能はすべてトップレベルのパッケージから参照できます。

```python
import pgsn
```

`pgsn.__all__` が公開 API のすべてです。そこに載っていないもの（サブモジュール `pgsn.dsl`・`pgsn.gsn`・`pgsn.pgsn_term`・`pgsn.pgsn_xml`・`pgsn.helpers`・`pgsn.config`・`pgsn.jail`・`pgsn.cli` を含む）は内部実装で、予告なく変更されることがあります。下の関数と項のほかに、`__version__` と `LABEL_WIDTH` も入っています。`LABEL_WIDTH` はノードのラベルを既定で折り返す桁数で、`gsn_dot` と `save_gsn` の `label_width` と、`pgsn render --label-width` の既定値です。

入り口は2つあります。XML ドキュメントを読み込む（`load_xml` がコンパイルと評価までします）か、Python で項を組み立てて `fully_eval()` で評価するかです。どちらでも評価済みの項が得られ、そこから先は[結果の読み出し](#結果の読み出し)の関数で扱います。パッケージがここに書いたのと違う動きをするところは、[known_issues-ja.md](known_issues-ja.md) に挙げてあります。この文書の英語版は [README-api.md](README-api.md) です。

目次：

1. [クイックスタート](#クイックスタート)
2. [項と評価](#項と評価)
3. [項の構築](#項の構築)
4. [組み込みの項](#組み込みの項)
5. [GSN のノード](#gsn-のノード)
6. [クラスとオブジェクト](#クラスとオブジェクト)
7. [結果の読み出し](#結果の読み出し)
8. [XML の読み込み](#xml-の読み込み)
9. [設定と jail](#設定と-jail)
10. [例外](#例外)

---

## クイックスタート

XML ドキュメントを読み込み、結果を読み出します。

```python
import pgsn

result = pgsn.load_xml("examples/gsn.xml")              # コンパイルと評価まで済む
print(pgsn.gsn_tree(result).show(stdout=False, sorting=False))
data = pgsn.python_value(result)                        # 素の dict と list
problems = pgsn.gsn_violations(result)                  # GSN v3 の規則への違反
```

同じ構造を Python で組み立て、1回だけ評価することもできます。

```python
g = pgsn.goal(
    description="System is secure",
    support=pgsn.strategy(
        description="Break into sub-goals",
        sub_goals=[
            pgsn.goal(description="Input validated",
                      support=pgsn.solution(description="Static analysis passed")),
            pgsn.goal(description="Output sanitized",
                      support=pgsn.solution(description="Fuzzing test succeeded")),
        ],
    ),
)
result = g.fully_eval()
print(pgsn.gsn_tree(result).show(stdout=False, sorting=False))
```

```
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded
```

---

## 項と評価

`Term` はすべての PGSN 値の型です。項は不変で、組み合わせて作ります。要求するまで何も計算されません。

### 適用

項を呼び出すと適用になります。位置引数は1つずつ適用され、キーワード引数はまとめて1つのレコードになって最後に適用されます。

```python
pgsn.plus(pgsn.integer(1))(pgsn.integer(2))   # 1つずつ
pgsn.plus(pgsn.integer(1), pgsn.integer(2))   # まとめて渡しても同じ
pgsn.goal(description=..., support=...)       # キーワードのレコード
```

レコードやオブジェクトは、ラベルに適用して読みます。`pgsn.record({"a": pgsn.integer(1)})("a")` は `1` に評価され、ゴールを `"description"` に適用するとその説明が得られます。

引数に渡した Python の値は項に変換されます。`str` は `string`、`int` は `integer`、`bool` は `boolean`、`list` と `tuple` は `list_term`、`dict` は `record` になり、中身も再帰的に変換されます。それ以外の値は `TypeError` になります。`list_term` と `record` 自身は項しか受け取りません（`pgsn.list_term((pgsn.string("a"),))`）。

### 評価

```python
term.fully_eval()            # 項全体を評価する。上限は既定の steps=1000000
term.fully_eval(steps=5000)  # 上限を自分で決める
```

項は全部組み立ててから、1回だけ評価します。評価が返すのは読み出すための結果で、`python_value` や `gsn_tree`、描画に渡します。結果を何かに適用したり、別の項を組み立てる引数として渡したりする使いかたはサポートしていません。

`steps` は安全のための上限です。評価器が関数か組み込みを引数に適用するたびに1ステップと数え、上限に達すると評価は[例外](#例外)で述べるエラーで止まります。普通のドキュメントなら既定の上限で足ります。大きなドキュメントが上限に達したときだけ増やしてください。ステップの数えかたは今後の版で変わることがあります。

### 評価が先へ進めないとき

項の中の誤り（レコードに無いラベル、種類の合わない引数、定義されていない名前）があっても、評価はエラーで止まりません。その部分はそのまま残り（*詰まった*状態）、エラーになるのは結果を読み出すときです。[`python_value`](#python_valueterm-with_inherit_chainfalse) が `ValueError` を送出し、評価が先へ進めなかった位置をパスで示します。誰も読まない部分が詰まっていても害はありません。理由は [PGSN-implementation.md](PGSN-implementation.md) にあります。

---

## 項の構築

### データ・変数・定数

| 関数 | 作るもの |
|------|------------|
| `string(s)` | 文字列 |
| `integer(i)` | 整数 |
| `boolean(b)` | 真偽値 |
| `list_term((t1, t2, ...))` | リスト。項の**タプル**から作る |
| `record({"k": t, ...})` | レコード。項の辞書から作る |
| `variable(name)` | 変数 |
| `constant(name)` | 不透明な定数 |

### 関数と束縛

| 関数 | 意味 |
|------|------|
| `lambda_abs(v, body)` | パラメーター1つの関数 |
| `lambda_abs_vars((v1, v2, ...), body)` | パラメーターが複数あり、1つずつ適用する関数 |
| `lambda_abs_keywords(arguments, body, defaults=空のレコード)` | キーワードパラメーターの関数。`arguments` は名前から変数への辞書、`defaults` はデフォルト値のレコード |
| `let(v, t, body)` | `body` の中で `v` を `t` に束縛 |
| `let_vars(((v1, t1), ...), body)` | 複数の束縛をまとめて |

再帰には組み込みの [`fix`](#組み込みの項) を使います。

```python
x = pgsn.variable("x")
double = pgsn.lambda_abs(x, pgsn.plus(x)(x))
pgsn.python_value(double(pgsn.integer(21)).fully_eval())   # 42

n = pgsn.variable("n")
inc = pgsn.lambda_abs_keywords({"n": n}, pgsn.plus(n)(1),
                               pgsn.record({"n": pgsn.integer(1)}))
pgsn.python_value(inc().fully_eval())      # 2: n はデフォルト値
pgsn.python_value(inc(n=5).fully_eval())   # 6

f = pgsn.variable("f")
fact = pgsn.fix(pgsn.lambda_abs_vars((f, n),
    pgsn.if_then_else(pgsn.equal(n)(0))(1)(pgsn.times(n)(f(pgsn.minus(n)(1))))))
pgsn.python_value(fact(5).fully_eval())    # 120
```

デフォルト値の無いキーワードパラメーターを呼び出しで省くと、そのパラメーターは値を持たず、適用は詰まります。

### テンプレート

GSN のテンプレートはノードを返す普通の関数なので、`map_term` でリストに展開できます。

```python
x = pgsn.variable("x")
template = pgsn.lambda_abs(
    x, pgsn.goal(description=x, support=pgsn.solution(description=x)))

goals = pgsn.map_term(template)(["R1", "R2"])
top = pgsn.goal(description="All requirements are met",
                support=pgsn.immediate(goals))
```

---

## 組み込みの項

これらは Python の関数ではなく項です。適用して使う値で、引数は1つずつ渡しても、まとめて渡してもかまいません。XML も同じ組み込みを同じ名前で束縛し、クラスの短い別名 `Goal`・`Strategy` などを加えています（[README-ja-xml.md](README-ja-xml.md#組み込み)）。

| 組み込み | 適用のしかた | 結果 |
|---|---|---|
| `cons` | `cons(x)(xs)` | `xs` の先頭に `x` を付けたリスト |
| `head`・`tail` | `head(xs)`・`tail(xs)` | 先頭の要素、残りのリスト |
| `index` | `index(xs)(i)` | `i` 番目の要素。0 から数え、負の `i` は Python と同じく末尾から数える |
| `is_empty` | `is_empty(xs)` | `xs` が空かどうか |
| `concat` | `concat(xs)(ys)` | `xs` の後に `ys` を続けたリスト |
| `map_term` | `map_term(f)(xs)` | 各要素に `f` を適用したリスト |
| `fold`・`foldr` | `fold(f)(z)(xs)` | 右畳み込み。`fold(f)(z)([x1, x2])` は `f(x1)(f(x2)(z))`。`fold` は `foldr` の別名 |
| `list_all` | `list_all(p)(xs)` | すべての要素で `p` が成り立つかどうか |
| `empty` | `empty` | 空リスト |
| `true`・`false` | | 真偽値 |
| `if_then_else` | `if_then_else(c)(a)(b)` | `c` が成り立てば `a`、そうでなければ `b`。選ばれた枝だけが評価される |
| `boolean_and`・`boolean_or`・`boolean_not` | `boolean_and(a)(b)`・`boolean_not(a)` | 論理演算 |
| `equal` | `equal(a)(b)` | 2つのデータが等しいかどうか。データ以外は詰まる |
| `less_than` | `less_than(a)(b)` | 整数で `a < b` かどうか |
| `guard` | `guard(c)(v)` | `c` が真なら `v`、そうでなければ詰まる |
| `plus`・`minus`・`times` | `plus(a)(b)` | 整数の算術 |
| `div`・`mod` | `div(a)(b)` | Python の `//` と `%`。`div(-7)(2)` は `-4`、`mod(-7)(2)` は `1`。0 での除算は詰まる |
| `integer_sum` | `integer_sum(xs)` | 整数のリストの和 |
| `repeat` | `repeat(f)(z)(n)` | `z` に `f` を `n` 回適用したもの |
| `has_label` | `has_label(r)(k)` | レコード `r` がラベル `k` を持つかどうか |
| `add_attribute` | `add_attribute(r)(k)(v)` | `r` のラベル `k` を `v` にしたレコード |
| `remove_attribute` | `remove_attribute(r)(k)` | `r` からラベル `k` を除いたレコード |
| `overwrite_record` | `overwrite_record(r)(s)` | `r` に `s` のラベルを加えたレコード。`s` のほうが優先 |
| `empty_record` | `empty_record` | ラベルの無いレコード |
| `format_string` | `format_string(t)(r)` | 文字列 `t` の `{label}` をレコード `r` の値で置き換えたもの。`format_string("{a}-{b}")({"a": "x", "b": 2})` は `"x-2"` |
| `define_class`・`instantiate`・`type_of`・`is_subtype`・`base_class` | | [クラスとオブジェクト](#クラスとオブジェクト)を参照 |
| `fix` | `fix(f)` | `f` の不動点。再帰に使う（[関数と束縛](#関数と束縛)の例を参照） |
| `undefined` | `undefined` | 名前の付いた定数 |

---

## GSN のノード

どのコンストラクタもキーワード引数を取り、項を返します。

| コンストラクタ | 引数 |
|--------------|------|
| `goal` | `description`・`support`・`contexts`（デフォルトは空）・`assumptions`（デフォルトは空）・`defeaters`（デフォルトは空） |
| `strategy` | `description`・`sub_goals`・`contexts`（デフォルトは空）・`assumptions`（デフォルトは空）・`defeaters`（デフォルトは空） |
| `solution` | `description`・`defeaters`（デフォルトは空） |
| `context` | `description` |
| `assumption` | `description` |
| `defeater` | `description`・`support`（デフォルトは undeveloped）・`defeaters`（デフォルトは空） |

`undeveloped` はコンストラクタではなく値で、まだ展開していない Goal の支持を表します。`support` にデフォルト値は無いので、支持の無い Goal は `support=pgsn.undeveloped` と書きます。

`contexts` と `assumptions` は Goal と Strategy が持ちます。GSN v3 がこの2つのノードに付けるからです。Solution はどちらも取りません。

`defeaters` は GSN v3 の弁証法的拡張（dialectic extension）です。Defeater は、それを持つノードへの支持ではなく疑いを記録します。Goal・Strategy・Solution・Defeater はどれも Defeater を持てるので、異議は入れ子にできます。根拠を示して異議を立てる Defeater は `support` を書き、異議を述べるだけなら省きます。Defeater ノードは PGSN 独自のものです。GSN v3 にはそのような要素は無く、そう選んだ理由は [PGSN-implementation.md](PGSN-implementation.md) にあります。

よく使う形のための補助が2つあります。

- `immediate(goals)` — サブゴールのリストをそのまま持つだけの Strategy。説明は文字列 `immediate` で、ほかの Strategy と同じく描かれ、検査されます。
- `solution_as_goal(s)` — 説明と支持の両方を Solution から取る Goal。

```python
import pgsn

g = pgsn.goal(
    description="System is secure",
    contexts=[pgsn.context(description="Deployment: cloud")],
    support=pgsn.strategy(
        description="Argue over properties",
        sub_goals=[
            pgsn.goal(description="Input is validated",
                      support=pgsn.solution(description="Static analysis report")),
            pgsn.goal(description="Output is sanitized",
                      support=pgsn.undeveloped),
        ],
    ),
)
evaluated = g.fully_eval()
print(pgsn.gsn_tree(evaluated).show(stdout=False, sorting=False))
```

```
Goal: System is secure
├── Context: Deployment: cloud
└── Strategy: Argue over properties
    ├── Goal: Input is validated
    │   └── Solution: Static analysis report
    └── Goal: Output is sanitized
        └── Undeveloped:
```

以下の例では、この `evaluated` を使います。

---

## クラスとオブジェクト

GSN のコンストラクタの背後にあるクラス値は `gsn_class`・`goal_class`・`strategy_class`・`solution_class`・`context_class`・`assumption_class`・`defeater_class`・`support_class`・`undeveloped_class` です。

`define_class(name=..., inherit=..., attributes=[...])` がクラスを作り、`instantiate(cls, **attributes)` がそのオブジェクトを作ります。`inherit` は必須です。ほかに親の無いクラスには `pgsn.base_class` を指定してください。`attributes` はクラスが加えるラベルのリストです。GSN のクラスから派生したクラスは、どの読み出しの関数でも使えます。

```python
owned_goal_class = pgsn.define_class(
    name="OwnedGoal", inherit=pgsn.goal_class, attributes=["owner"])
g = pgsn.instantiate(owned_goal_class, description="Logging enabled",
                     owner="alice", support=pgsn.undeveloped)
pgsn.python_value(g.fully_eval())["owner"]   # 'alice'
```

`name` はクラスの名前です。`python_value` はインスタンスをこの名前で報告します（マーカーキー `__OwnedGoal__`）。そのため、インスタンスを読み出すクラスには名前が要ります。名前の無いクラスのインスタンスには `python_value` が `ValueError` を送出します。名前は継承されず、名前どうしが比べられることもありません。

`type_of` はオブジェクトのクラスを返し、`is_subtype` は2つのクラスを比べます。値を型と照合するときはこう書きます。

```python
pgsn.python_value(pgsn.is_subtype(pgsn.type_of(g))(pgsn.goal_class).fully_eval())   # True
```

型付けは構造的です。`is_subtype` が比べるのは2つのクラスが宣言する属性名とメソッド名だけで、`inherit` は関与しません。`description` と `defeaters` を持つ自作のクラスは `solution_class` を満たしますし、Goal もそれらを含めて宣言しているので満たします。「どのクラスに属するか」を尋ねる述語はありません。クラスの出自を知りたいときは、オブジェクトから継承チェーンを読み出してください。チェーンはオブジェクト自身のクラスから始まります。

```python
pgsn.python_value(g.fully_eval(), with_inherit_chain=True)["__parent_classes__"]
# ['OwnedGoal', 'Goal', 'GSN_Node', 'BaseClass']
```

---

## 結果の読み出し

先に評価してください。以下の関数はどれも評価済みの項を前提にしています。評価していない項や詰まった項には `ValueError` を送出し、評価が止まった位置をパスで示します。

### `python_value(term, with_inherit_chain=False)`

項を素の Python のデータ（`dict`・`list`・`str`・`int`・`bool`）に変換します。オブジェクトは属性の `dict` になり、値が `True` のマーカーキー `__ClassName__` が付きます。たとえば未展開の Goal は次のようになります。

```python
{'description': 'G', 'contexts': [], 'assumptions': [], 'defeaters': [],
 'support': {'defeaters': [], 'description': '', '__Undeveloped__': True},
 '__Goal__': True}
```

`with_inherit_chain=True` を渡すと、入れ子のものも含めてすべてのオブジェクトに `__parent_classes__` が付きます。

`ValueError` のメッセージには、問題のノードまでのパス（`<root>.support` や `<root>.contexts[0]` など）が入るので、詰まった部分を特定する最短の手段になります。クラスに名前の無いオブジェクトでも送出します。付けるマーカーキーが無いからです。関数・クラス・定数でも送出します。対応する Python の値が無いからです。

### `gsn_tree(term)`

[treelib](https://treelib.readthedocs.io/) の `Tree` を返します。

```python
tree = pgsn.gsn_tree(evaluated)
print(tree.show(stdout=False, sorting=False))   # テキスト表示
tree.to_json(sort=False)                        # treelib の JSON 形式
```

treelib は指定しないと兄弟をタグ順に並べ替えるので、`show` には `sorting=False`、`to_json` には `sort=False` を渡してください。リストの順序はドキュメントが述べていることの一部で、`python_value` はその順序で報告します。`pgsn doc` も同じオプションを渡しています。

### `gsn_dot(term, layout_attrs=None, label_width=40)`

GSN のノード形状を適用した `graphviz.Digraph` を返します。`layout_attrs` で既定値（`rankdir`・`splines`・`nodesep`・`ranksep`）を上書きできます。ラベルは `label_width` 桁で折り返し、`0` なら1行のままにします。グラフを作るだけなら Graphviz は要りませんが、画像にするには要ります。

```python
dot = pgsn.gsn_dot(evaluated, {"rankdir": "LR"})
dot.render("out", format="svg", cleanup=True)
```

### `save_gsn(term, filename, image_format="png", view=False, cleanup=True, label_width=40)`

そのままファイルに書き出し、`None` を返します。`filename` には拡張子を付けません。`save_gsn(t, "saved")` は `saved.png` を書きます。`view=True` で画像をビューアで開き、`cleanup=True` で途中の DOT ファイルを消します。`label_width` は `gsn_dot` と同じです。Graphviz のプログラムが要ります。

### `gsn_violations(term)`

評価した構造が GSN v3 の規則を破っている箇所を、`GSNViolation`（`path`・`identifier`・`message`）のリストで返します。空のリストなら違反はありません。`path` は `python_value` のエラーメッセージと同じ書き方で、`identifier` は図がその要素に付けるラベル（`G1`・`S1`）です。規則は [GSN v3 に照らした検査](README-ja-xml.md#gsn-v3-に照らした検査)にあります。

```python
for v in pgsn.gsn_violations(evaluated):
    print(v)   # S1 at <root>.support: a strategy relates a goal to ...
```

---

## XML の読み込み

ドキュメントの構文は [README-ja-xml.md](README-ja-xml.md) にあります。ルート要素は `<PGSN>` でなければなりません。

### `load_xml(path, *, config=None, steps=None)`

```python
term = pgsn.load_xml("main.xml")
```

### `load_xml_string(xml, *, config=None, jail=None, steps=None)`

```python
term = pgsn.load_xml_string(source)
```

文字列として持っているドキュメントには自分のディレクトリが無いので、どの jail に属すると見なすかを指定しない限り、相対 import は拒否されます（[設定と jail](#設定と-jail) を参照）。

```python
pgsn.load_xml_string(source, config=cfg, jail="lib")
```

jail パス（`/lib/...`）はどちらの場合も使えます。

### どちらも返すもの

どちらもコンパイルと評価まで行うので、返ってくるのは[評価](#評価)で述べた結果です。読み出すのに使い、組み立ての材料にはしません。

どちらも `steps` を取ります。意味も既定値も `fully_eval` と同じで、`pgsn` コマンドの既定値とも同じです。それでは足りない大きなドキュメントでは、上限を上げます。

```python
term = pgsn.load_xml("big.xml", steps=5_000_000)
```

---

## 設定と jail

ドキュメントは他のドキュメントを import できますが、どこまで届くかは *jail の表*で制御されます。jail は名前の付いたディレクトリルートで、ドキュメント側は絶対パス風のパスの先頭要素としてそれを指定します。

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

```python
cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})   # 共有モジュールを置いた実在のディレクトリ
term = pgsn.load_xml("main.xml", config=cfg)
```

ドキュメントの*封じ込めルート*は、それを含む登録済みの jail です。どの jail にも含まれなければ、そのドキュメント自身のディレクトリです。

- 相対 import は、封じ込めルートの内側に留まる限り `..` を使えます。
- シンボリックリンクは、その検証の前に展開されます。
- jail 経由でたどったモジュールは、その jail の外に出られません。

規則の全体は [README-ja-xml.md](README-ja-xml.md#import-パスと-jail) にあります。

### `Jails(roots=None)`

名前からパスへの辞書から作る不変の表です。ルートは構築時に一度だけ検証・解決されます。相対パスのルートはその時点のカレントディレクトリを基準に解決され、ディレクトリが存在しなければ import 時ではなくその場で `JailError` になります。名前に使えるのは ASCII の英数字と `_`、`-` です。

```python
jails = pgsn.Jails({"lib": "/opt/pgsn-lib", "proj": "./modules"})
jails.names            # ('lib', 'proj')
"lib" in jails         # True
jails.root_of("lib")   # PosixPath('/opt/pgsn-lib')
```

表に無い名前を `root_of` に渡すと `JailError` になります。`len()` と繰り返しは使えますが、添字（`jails["lib"]`）は使えません。

### `Config(jails=None)`

不変の設定オブジェクトです。`Jails` でも素の辞書でも受け取ります。`config.jails` で読み出し、`config.replace(jails=...)` で一部を変えた複製を作れます。

### `configure(config=None, *, jails=None)` と `get_config(config=None)`

`configure` は、`config` を省略した呼び出しで使われる既定の設定を登録し、それを返します。何度でも呼べて、引数なしの `configure()` は空の既定に戻します。`Config` と個別の設定を両方渡すことはできません。`get_config` は現在の既定を返すか、渡された設定を検証して返します。

```python
pgsn.configure(jails={"lib": "/opt/pgsn-lib"})
pgsn.load_xml("main.xml")                      # 既定を使う
pgsn.load_xml("other.xml", config=other_cfg)   # この呼び出しだけ上書き
```

既定の設定は利便のためのもので、セキュリティの境界ではありません。ドキュメントを封じ込めるのは、その呼び出しで実際に使われた設定が持つ `Jails` の表です。PGSN にとって信用できない入力は XML で、XML からこれらの関数には手が届きません。

---

## 例外

| 例外 | 送出するもの | 場合 |
|---|---|---|
| `PGSNError` | `load_xml`・`load_xml_string` | 整形式のドキュメントをコンパイラが拒むとき。値が期待される位置の知らない要素、不正な名前や予約された名前、循環 import、拒否された import や見つからない import、`<PGSN>` 以外のルート要素 |
| `JailError` | `Jails`・`Config`・`configure`・`Jails.root_of` | 不正な jail 名、存在しないかディレクトリでないルート、表に無い jail 名。コンパイル中に起きた場合は `PGSNError` に変換される |
| `xml.etree.ElementTree.ParseError` | `load_xml`・`load_xml_string` | ドキュメントが整形式の XML でない |
| `FileNotFoundError` | `load_xml` | ドキュメントのファイルそのものが無い |
| `LambdaInterpreterError` | `fully_eval`・`load_xml`・`load_xml_string` | `steps` の上限に達した。`e.args[0]` は `'Reduction did not terminate'` |
| `TypeError` | 項の構築、`Config`・`configure`・`get_config`・`load_xml` | 項に対応しない Python の値（`float`・`None`）、または種類の違う設定 |
| `ValueError` | `python_value`・`gsn_tree`・`gsn_dot`・`save_gsn`・`gsn_violations` | 結果が値を持たない。メッセージは評価が止まった位置をパスで示す |

```python
try:
    term = pgsn.load_xml(path, config=cfg)
except pgsn.PGSNError as e:
    print(f"{path} を読み込めませんでした: {e}")
```
