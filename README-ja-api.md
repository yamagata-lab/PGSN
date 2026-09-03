# PGSN Python API

サポート対象の機能はすべてトップレベルのパッケージから参照できます。

```python
import pgsn
```

`pgsn.__all__` が公開 API のすべてです。そこに載っていないもの — サブモジュール `pgsn.dsl`、`pgsn.gsn`、`pgsn.pgsn_term`、`pgsn.pgsn_xml`、`pgsn.dcom`、`pgsn.helpers`、`pgsn.cli` を含む — は内部実装であり、予告なく変更されることがあります。

入り口は 2 つあります。Python で項を組み立てるか、XML ドキュメントから読み込むか。どちらも `Term` を返し、そこから先は共通です。

- [項と評価](#項と評価)
- [定数と項の構築](#定数と項の構築)
- [組み込みの項](#組み込みの項)
- [GSN コンストラクタ](#gsn-コンストラクタ)
- [結果の読み出し](#結果の読み出し)
- [XML の読み込み](#xml-の読み込み)
- [例外](#例外)

---

## 項と評価

`Term` はすべての PGSN 値の型です。項は不変で、合成によって組み立てられます。要求するまで何も計算されません。

### 適用

項を呼び出すと適用になります。位置引数は 1 つずつ適用され、キーワード引数はまとめて 1 つのレコードになって最後に適用されます。

```python
pgsn.plus(pgsn.integer(1))(pgsn.integer(2))   # カリー化
pgsn.plus(pgsn.integer(1), pgsn.integer(2))   # 同じ意味
pgsn.goal(description=..., support=...)       # キーワードのレコード
```

項が期待される位置では Python の値が自動的にキャストされるので、引数としては `pgsn.string("a")` と `"a"` は同じように使えます。

### 評価

```python
term.eval()                  # 1 ステップだけ簡約
term.fully_eval()            # 正規形まで簡約、既定は steps=100000
term.fully_eval(steps=5000)  # 上限を明示
```

すでに正規形なら `fully_eval` はそのまま返します。`steps` は簡約回数の上限であって時間の上限ではありません。簡約するたびに項が膨らむ形だと、上限に達する前にこちらの忍耐が尽きます。自由変数が残った項や、型の合わない引数に適用された項はエラーにならず、単に「詰まった」状態のまま返ってきます。

---

## 定数と項の構築

### リテラル

| 関数 | 生成するもの |
|------|------------|
| `string(s)` | 文字列 |
| `integer(i)` | 整数 |
| `boolean(b)` | 真偽値 |
| `list_term((t1, t2, ...))` | リスト。項の**タプル**から作る |
| `record({"k": t, ...})` | レコード |
| `variable(name)` | 変数 |
| `constant(name)` | 不透明な定数 |

### 抽象と束縛

| 関数 | 意味 |
|------|------|
| `lambda_abs(v, body)` | 引数 1 個の関数 |
| `lambda_abs_vars((v1, v2, ...), body)` | カリー化された多引数関数 |
| `lambda_abs_keywords(arguments, body, defaults)` | キーワード引数の関数。`arguments` は名前から変数への辞書、`defaults` はレコード |
| `let(v, t, body)` | `body` の中で `v` を `t` に束縛 |
| `let_vars(((v1, t1), ...), body)` | 複数の束縛をまとめて |
| `fix(f)` | 不動点。再帰に使う |

```python
x = pgsn.variable("x")
double = pgsn.lambda_abs(x, pgsn.plus(x)(x))
pgsn.python_value(double(pgsn.integer(21)).fully_eval())   # 42
```

---

## 組み込みの項

これらは Python の関数ではなく項です。適用して使う値です。XML 側もまったく同じ名前を公開しています（[README-ja-xml.md](README-ja-xml.md)）。

**リスト** — `cons`・`head`・`tail`・`index`・`concat`・`map_term`・`fold`・`foldr`・`list_all`・`empty`

**真偽値** — `true`・`false`・`if_then_else`・`boolean_and`・`boolean_or`・`boolean_not`・`equal`・`guard`

**整数** — `plus`・`minus`・`times`・`div`・`mod`・`integer_sum`・`repeat`

**レコード** — `has_label`・`list_labels`・`add_attribute`・`remove_attribute`・`overwrite_record`・`empty_record`

**文字列** — `format_string`

**クラスとオブジェクト** — `define_class`・`instantiate`・`instance`・`is_instance`・`is_subclass`・`base_class`

**その他** — `fix`・`undefined`

`fold` の引数の順は `fold(f)(accumulator)(list)` です。`repeat(f, accumulator, n)` は accumulator に `f` を `n` 回適用します。

---

## GSN コンストラクタ

いずれもキーワード引数を取り、項を返します。

| コンストラクタ | 引数 |
|--------------|------|
| `goal` | `description`・`support`・`contexts`（既定は空）・`assumptions`（既定は空） |
| `strategy` | `description`・`sub_goals` |
| `evidence` | `description` |
| `context` | `description`・`value`（既定は `""`） |
| `assumption` | `description`・`value`（既定は `""`） |

`support` に既定値はありません。支持のないゴールは `support=pgsn.undeveloped` と明示的に書きます。

よく使う形のための補助が 2 つあります。

- `immediate(goals)` — サブゴールのリストをそのまま持つだけの戦略
- `evidence_as_goal(ev)` — description と support の両方をエビデンスから取るゴール

```python
import pgsn

g = pgsn.goal(
    description="System is secure",
    contexts=pgsn.list_term((pgsn.context(description="Deployment: cloud"),)),
    support=pgsn.strategy(
        description="Argue over properties",
        sub_goals=pgsn.list_term((
            pgsn.goal(description="Input is validated",
                      support=pgsn.evidence(description="Static analysis report")),
            pgsn.goal(description="Output is sanitised",
                      support=pgsn.undeveloped),
        )),
    ),
)
print(pgsn.gsn_tree(g.fully_eval()).show(stdout=False))
```

```
Goal: System is secure
├── Context: Deployment: cloud
│   └── value:
└── Strategy: Argue over properties
    ├── Goal: Input is validated
    │   └── Evidence: Static analysis report
    └── Goal: Output is sanitised
        └── Undeveloped:
```

### クラス

コンストラクタの背後にあるクラス値は `gsn_class`・`goal_class`・`strategy_class`・`evidence_class`・`context_class`・`assumption_class`・`support_class`・`undeveloped_class` です。`define_class` と組み合わせて独自のノード型を派生させたり、`is_instance` で判定したりできます。

```python
my_goal_class = pgsn.define_class(
    inherit=pgsn.goal_class,
    attributes=pgsn.list_term((pgsn.string("owner"),)),
)
```

### テンプレート

GSN のテンプレートはノードを返す普通の関数なので、`map_term` でリストに展開できます。

```python
x = pgsn.variable("x")
template = pgsn.lambda_abs(
    x, pgsn.goal(description=x, support=pgsn.evidence(description=x)))

requirements = pgsn.list_term((pgsn.string("R1"), pgsn.string("R2")))
goals = pgsn.map_term(template)(requirements)
```

---

## 結果の読み出し

先に評価してください。以下はいずれも正規形の項を前提にしています。

### `python_value(term, with_inherit_chain=False)`

項を素の Python のデータ（`dict`・`list`・`str`・`int`・`bool`）に変換します。オブジェクトノードには `__ClassName__` というマーカーキーが付くので、評価済みのゴールは `description`・`support`・`contexts`・`assumptions`・`__Goal__` というキーを持つ辞書になります。`with_inherit_chain=True` を渡すと `__parent_classes__` も付きます。

項が評価しきれていない場合は `ValueError` を送出します。メッセージに問題のノードまでのパスが入るので、詰まった部分項を特定する最短の手段になります。

### `gsn_tree(term)`

[treelib](https://treelib.readthedocs.io/) の `Tree` を返します。

```python
tree = pgsn.gsn_tree(evaluated)
print(tree.show(stdout=False))   # テキスト表示
tree.to_json()                   # JSON
```

### `gsn_dot(term, layout_attrs=None)`

GSN のノード形状を適用した `graphviz.Digraph` を返します。`layout_attrs` で既定値（`rankdir`・`splines`・`nodesep`・`ranksep`）を上書きできます。

```python
dot = pgsn.gsn_dot(evaluated, {"rankdir": "LR"})
dot.render("out", format="svg", cleanup=True)
```

### `save_gsn(term, filename, image_format="png", view=False, cleanup=True)`

そのままファイルに書き出します。

---

## XML の読み込み

```python
term = pgsn.load_xml("main.xml")
term = pgsn.load_xml_string(source)
```

どちらもコンパイルと完全評価まで行い、正規形を返します。ドキュメントの構文は [README-ja-xml.md](README-ja-xml.md) を参照してください。

### jail

ドキュメントは他のドキュメントを import できますが、どこまで届くかは *jail テーブル*で制御されます。jail は名前の付いたディレクトリルートで、ドキュメント側は絶対パス風のパスの先頭要素としてそれを指定します。

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

```python
cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

パス指定で開いたドキュメントが登録済みの jail のどれにも属さない場合、そのドキュメント自身のディレクトリが封じ込め範囲になります。相対 import は封じ込めルートの内側に留まる限り `..` を使えます。シンボリックリンクは検証前に展開され、jail 経由で辿ったモジュールはその jail の外に出られません。

#### `Jails(roots)`

名前からパスへの辞書から作る不変のテーブルです。ルートは構築時に一度だけ検証・解決されるので、ディレクトリが存在しなければ import 時ではなくその場で `JailError` になります。名前に使えるのは英数字と `_`、`-` です。

```python
jails = pgsn.Jails({"lib": "/opt/pgsn-lib", "proj": "./modules"})
jails.names            # ('lib', 'proj')
"lib" in jails         # True
jails.root_of("lib")   # PosixPath('/opt/pgsn-lib')
```

#### `Config(jails=None)`

不変の設定オブジェクトです。`Jails` でも素の辞書でも受け取ります。`config.jails` で読み出し、`config.replace(jails=...)` で派生を作れます。

#### `configure(config=None, *, jails=None)` と `get_config(config=None)`

`configure` は `config` を省略した呼び出しで使われる既定設定を設定します。何度でも呼べます。`get_config` は現在の既定を返すか、渡された設定を検証して返します。

```python
pgsn.configure(jails={"lib": "/opt/pgsn-lib"})
pgsn.load_xml("main.xml")                      # 既定を使う
pgsn.load_xml("other.xml", config=other_cfg)   # 一時的に上書き
```

既定設定は利便のためのもので、セキュリティ境界ではありません。ドキュメントを封じ込めるのは、その呼び出しで実際に使われた設定が持つ `Jails` テーブルです。PGSN にとって信用できない入力は XML であり、XML からこれらの関数には手が届きません。

#### `load_xml_string(xml, *, config=None, jail=None)`

文字列として持っているドキュメントには自分のディレクトリがないので、どの jail に属すると見なすかを指定しない限り相対 import は拒否されます。

```python
pgsn.load_xml_string(source, config=cfg, jail="lib")
```

jail パス（`/lib/...`）はどちらの場合も使えます。

---

## 例外

`PGSNError` はドキュメントのコンパイル中に起きるすべてを表します。構文の誤り、未知の要素、循環 import、そして拒否されたすべての import パスです。`JailError` は jail 定義そのものの不正を表し、`Jails` の構築時に送出されます。コンパイル中に起きた場合は `PGSNError` に変換されるので、読み込みの周りは `PGSNError` を捕まえれば足ります。

```python
try:
    term = pgsn.load_xml(path, config=cfg)
except pgsn.PGSNError as e:
    print(f"{path} を読み込めませんでした: {e}")
```
