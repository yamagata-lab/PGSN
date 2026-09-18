# PGSN — Programmable Goal Structuring Notation

PGSN は XML ベースの言語で、GSN（Goal Structuring Notation）をプログラマブルに拡張したものです。
GSN ノード（Goal・Strategy・Evidence）を値として扱い、変数・テンプレート・クラスといったプログラミング構造と組み合わせることができます。

---

## 設計の原則

言語のどこでも成り立つ性質が5つあります。以降の節は構文を説明しますが、ここで述べるのは、その構文が何のための構文なのかです。

**すべてが値です。** Goal も Strategy も Evidence も、クラスもテンプレートも、文字列やリストと同じ値です。名前に束縛でき、リストに入れられ、テンプレートに渡せて、テンプレートから返せます。名前を書くための特別なスロットも、クラス名を表す文字列もありません。content を取る要素は、どこでも式を取ります。[値（val）](#値val)を参照してください。

**純粋関数型です。** 書き換えも実行もありません。`<def>` はそれ以降のスコープで名前を束縛するだけで、前の束縛が意味していたものを変えることはありません。同じ名前をもう一度束縛するのは、代入ではなくシャドーイングです。したがってドキュメントはひとつの値を表し、何度評価しても同じ値を表します。[定義（def）](#定義def)を参照してください。

**評価は失敗せず、止まります。** 束縛されていない変数、持っていないラベルで引かれたレコード、値が満たさない `typeOf` 検査——どれもエラーではありません。その適用を簡約する規則が無いので、項はそのまま残り、それを含む項は正規形に到達しません。関数のところでも簡約は止まります。関数は値なので、適用されるまで本体には入りません。ここでは何も raise されません。raise するのは、そのあとに値を求めるもの——`pgsn doc` や `python_value`——です。正規形でない項からは値を作れないので、簡約が止まった位置をパスで示します。コンパイルは別の話で、構文の誤りや拒否された import はエラーであり、エラーとして raise されます。

**外へ出る道は `import` だけで、それも閉じ込められています。** ドキュメントはファイルを読まず、ネットワークに触れず、時計も見ません。自分の外にあるものへの唯一の接続は `<from>` で、そこに書けるのは、ドキュメントが閉じ込められたディレクトリツリーの中にあるファイルか、PGSN を実行した人が登録した jail の中にあるファイルだけです。[import パスと jail](#import-パスと-jail)を参照してください。

**同一性はデータだけのものです。** 等価性が比べるのは基本値——文字列・整数・真偽値・`undefined`——と、それらで組まれたリストとレコードです。関数どうし、クラスどうし、GSN ノードどうしを比べても値は出ません。物理的な同一性もありません。値はアドレスも時刻も持たないので、コピーと元を見分けることはできず、同じ description で書かれた2つのノードを見分けることもできません。[式（expr）](#式expr)を参照してください。

---

## ドキュメントの種類

PGSN には2種類のルート要素があります。

### `<PGSN>` — 値を生成するドキュメント

単一の値を返します。`<param>` は**使えません**。

```xml
<PGSN>
    <from file="..."/>         <!-- import（0個以上） -->
    <def name="x">...</def>    <!-- 定義（0個以上） -->
    ...                        <!-- 値（1つ） -->
</PGSN>
```

### `<PGSNModule>` — 再利用可能なモジュール

呼び出し元からパラメーターを受け取ります。`<param>` は先頭にだけ書けます。

```xml
<PGSNModule>
    <param name="p"/>          <!-- パラメーター（0個以上、先頭に書く） -->
    <from file="..."/>         <!-- import（0個以上） -->
    <def name="x">...</def>    <!-- 定義（0個以上） -->
</PGSNModule>
```

`<from>` と `<def>` は両形式とも混在して書くことができます。

---

## 値（val）

PGSN では**すべてが値**です。コンテンツを受け取る要素は必ず**式**（評価されて値になるもの）を期待します。言語に「クラス名」や「特別な名前スロット」という概念はありません。

> **重要な原則：ベタ書きのテキストは String リテラルになります。**
> 要素の中にテキストを直接書くと、それは `String` 値として解釈されます。
> `<inherit>Goal</inherit>` は Goal クラスを参照しません——文字列 `"Goal"` を生成するだけで、クラスではありません。変数を参照するには `<var>` または `var=` 属性を使います。

```xml
<!-- NG: テキストは文字列 "Goal" になり、クラスとして扱われない -->
<inherit>Goal</inherit>

<!-- OK: var= は変数参照の省略形 -->
<inherit var="Goal"/>

<!-- OK: 完全形 -->
<inherit><var name="Goal"/></inherit>

<!-- OK: クラスに評価される式ならなんでも書ける -->
<inherit><apply template="makeBaseClass"><arg>...</arg></apply></inherit>
```

### リテラル

裸のテキストは文字列になるので、それ以外のリテラルは明示的に書きます。

| 要素 | 値 |
|------|-----|
| 裸のテキスト | `String`。前後の空白は除去され、`{name}` は補間されます（[テキスト中の書式文字列](#テキスト中の書式文字列)を参照） |
| `<num>3</num>` | `Integer`。PGSN に浮動小数点数はありません |
| `<str> a {b} </str>` | `String`。書いたとおりに解釈され、空白は保たれ `{...}` は補間されません |

`<num>` が必要なのは、数字に見えても裸のテキストは文字列のままだからです。おかげでゴールに「2024年度の監査に合格」と書いても年が整数になりません。逆に算術の組み込みは整数しか受け取らないので、`<arg>3</arg>` は文字列を渡すことになり、和は計算されません。`<arg><num>3</num></arg>` と書いてください。

組み込みは最も外側のスコープにある普通の束縛です。したがって `<var name="plus"/>` は、より内側で `plus` を束縛するものがなければ組み込みに解決されます。

### 式（expr）

算術を `<apply>` で書くのは重いので、`<expr>` では通常の中置記法が使えます。

```xml
<def name="next"><expr>i + 1</expr></def>
<def name="label"><expr>f"コンポーネント {i}（全 {total}）"</expr></def>
```

`<expr>` は略記であって、それ以上のものではありません。コンパイルが始まる前に、対応する組み込みの適用へ展開されます。式を通してしか到達できない機能は存在しません。

**式の中に書けるもの**

| | |
|---|---|
| リテラル | `3`、`"text"`、`True`、`False` |
| 変数 | `i` — `<var name="i"/>` になります |
| 算術 | `+`、`-`、`*`、`//`、`%`、単項の `-` |
| 比較 | `==`、`!=`、`<`、`<=`、`>`、`>=` |
| 論理 | `and`、`or`、`not` |
| f-string | `f"コンポーネント {i} / {total}"`。`{i:>3}` のような書式指定も使えます |

これ以外は、何が見つかったかを示すエラーで拒否されます。関数呼び出し・属性アクセス・添字はありません。`<apply>`・`<get>`・リスト要素を使ってください。そちらのほうが何をしているか明確です。

**注意点が3つ**

XML では `<` をエスケープする必要があります。`i &lt; n` と書くか、`CDATA` で囲みます。

```xml
<expr>i &lt; n</expr>
<expr><![CDATA[i < n]]></expr>
```

`>` はエスケープ不要なので、`n > i` と書き換えるほうが楽なことも多いです。

`//` が整数除算です。`7 // 2` は `3` になります。`/` は同義語として受け付けるのではなくエラーにしています。将来 PGSN に浮動小数点数を導入したとき、`/` を通常の除算に割り当てられるようにするためです。

大小比較は整数のみなので、`"a" < "b"` には値がありません。等価比較はデータだけを比べます。基本の値（文字列・整数・真偽値・`undefined`）と、それらから組んだリストとレコードです。だから `"a" == "a"` は `True` ですが、関数どうし・クラスどうし・GSN ノードどうしの比較には、`"a" < "b"` と同じく値がありません。リストが空かどうかは `is_empty` を適用して聞いてください。`empty` との比較で答えが出るのは、要素が基本の値のリストに限られます。

**演算子は再定義できません。** `plus` という名前を束縛しているスコープの中でも `1 + 2` は加算のままです。

### 名前

*名前*とは、`<def>` と `<param>` が導入し `<var>` が参照するものです。名前を保持する属性はすべて同じ規則に従います。`<def>`・`<param>`・`<var>` の `name`、`<def>`・`<var>` の `typeOf`、`<from>`・`<import>` の `as`、`<apply>` の `template`、`<get>` の `of`、`<send>` の `to`、`<arg>` の `name`、そして略記の `var` 属性です。

名前は文字で始まり、以降は文字・数字・アンダースコアを続けられます。文字は ASCII に限りません。`ゴール` は名前として使えます。ただし先頭にアンダースコアは**使えません**。処理系が予約しています。

この規則は Python の識別子と同じで、これは意図的なものです。[式](#式expr)は Python のパーサーで解析されるため、式に書けない名前を許すと、その名前は式から参照できなくなってしまいます。

レコードのラベルは別の名前空間で、制限はありません。`<get>` と `<dt>` の `key`、`<send>` の `method`、`<attribute>` の `name` は任意の文字列です。`<class>` の `name` も同じで、これはクラスが何と呼ばれるかであって、何かが参照する名前ではありません。

### 条件分岐（if・cases）

`if_then_else` は組み込みなので普通に適用もできますが、二分岐をその書き方で読むのは辛いです。`<if>` は同じことを、部分に名前を付けて書きます。

```xml
<if>
    <cond expr="i &lt; threshold"/>
    <then>予算内</then>
    <else>予算超過</else>
</if>
```

`<else>` は必須です。選ばれなかった枝は評価されないので、再帰を条件で止めることができます。

条件が連なる場合は `<cases>` を使います。`<cond>` が成り立つ最初の `<case>` を選び、どれも成り立たなければ `<else>` に落ちます。

```xml
<cases>
    <case><cond expr="severity == 0"/><then>無視できる</then></case>
    <case><cond expr="severity &lt; 3"/><then>許容できる</then></case>
    <else>許容できない</else>
</cases>
```

ここでも `<else>` は必須です。無いと、どれにも当たらなかった `<cases>` は与える値を持たないだけで、間違いが起きた場所から遠く離れたところで表面化します。

`<cond>`・`<then>`・`<else>` はいずれも値を包むだけのラッパーなので、値の書き方はどれでも使えます。`var` と `expr` の略記も含みます。

どちらの形式も `if_then_else` 組み込みの適用を表します。組み込みには横取りできない経路で届くので、`if_then_else` という名前を束縛しているスコープでも `<if>` は条件分岐のままです。

### 式の略記

要素のコンテンツが式ひとつの場合、`expr` 属性は `<expr>` の子要素と同じことを表します。`var` と同様の略記で、2つの綴りは同じものの書き分けです。

```xml
<!-- 完全形 -->
<arg><expr>i + 1</expr></arg>

<!-- 略記 -->
<arg expr="i + 1"/>
```

属性と自身のコンテンツを両方持つことはできません。XML の都合で2点、注意が要ります。属性値の中では `<` を `&lt;` と書く必要があり、f-string を書くなら属性を `'` で囲まないと中の `"` が閉じてしまいます。

```xml
<def name="label" expr='f"コンポーネント {i}"'/>
<li expr="i &lt; n"/>
```

### 変数参照の略記

要素のコンテンツが変数参照のみの場合、`var` 属性で略記できます。
2つの綴りは同じものの書き分けです。

```xml
<!-- 完全形 -->
<tag><var name="x"/></tag>

<!-- 略記 -->
<tag var="x"/>
```

---

## パラメーター（param）

`param` は、それを囲む要素が外から受け取る変数を宣言します。パラメーターを取る要素は3つあります。`<PGSNModule>` は import する側のドキュメントから、`<template>` はそれを呼ぶ `<apply>` から、`<method>` はそれを起動する `<send>` から受け取ります。

```xml
<param name="A1"/>

<!-- デフォルト値付き -->
<param name="threshold">100</param>
```

`<PGSNModule>` では、パラメーターは `<from>` や `<def>` より前に書きます。

どこに書く場合も、パラメーターは位置引数かキーワード引数のどちらかです。2種類の区別と宣言の順序、デフォルト値を持てるのはどちらかについては、[テンプレート定義（template）](#テンプレート定義template)を参照してください。

---

## import（from）

外部の PGSN ファイルから名前を持ち込みます。ドキュメントがアクセスできるのは許可された範囲のファイルだけです。詳しくは下の [import パスと jail](#import-パスと-jail) を参照してください。

### 単一 import

```xml
<from file="security.pgsn" import="secureGoal" as="G1"/>
```

### 複数 import

```xml
<from file="evidence.pgsn">
    <import name="auditEvidence"/>
    <import name="testReport" as="TR"/>
</from>
```

### パラメーターを渡しながら import

```xml
<from file="other.pgsn">
    <import name="someGoal" as="G2"/>
    <arg name="A1" var="A1"/>
    <arg name="threshold" var="threshold"/>
</from>
```

### モジュールそのもの

値が期待される位置に書いた `<from>` は、何も取り出していないモジュールのレコードを表します。こう書くとモジュールは普通の値になります。`<def>` で束縛したり、リストに入れたり、テンプレートに渡したりできます。

```xml
<def name="lib"><from file="security.pgsn"/></def>
<get key="secureGoal" of="lib"/>
```

import の時点で名前を選び出すのは上の形式の役目なので、2つの綴りは混ざりません。値として使う `<from>` は `import` を取らず、束縛として使う `<from>` は `import` を必要とします。

### import パスと jail

ドキュメントはあるディレクトリツリーに閉じ込められており、`file` にはその中のファイルしか書けません。パスの書き方は 2 通りあります。

**相対パス**は、import する側のドキュメントがあるディレクトリを基準に解決されます。

```xml
<from file="modules/security.pgsn" import="secureGoal"/>
<from file="../shared/evidence.pgsn" import="auditEvidence"/>
```

`..` は使えますが、結果が封じ込めルートの内側に留まる場合に限ります。パスを指定して直接開いたドキュメントのルートは、そのドキュメント自身が置かれているディレクトリです。つまり既定では、隣接するファイルとその配下には届き、それより上には届きません。

**jail パス**は `/` で始まり、先頭の要素が *jail* の名前になります。jail は PGSN を実行する側が登録するディレクトリルートです。

```xml
<from file="/lib/security.pgsn" import="secureGoal"/>
```

ここで `lib` はディスク上のディレクトリ名ではなく jail 名です。コマンドラインまたは API で与えた jail テーブルを使って解決されます。

```console
$ pgsn doc main.xml --jail lib=/opt/pgsn-lib
```

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

ドキュメント側から未登録の jail を指定する手段はなく、jail の背後にある実際のディレクトリ構成を知る手段もありません。jail 名に使えるのは英数字と `_`、`-` のみです。

import が jail に入ると、その jail が import 先モジュールの封じ込めルートになります。jail 内のモジュールは相対パスで近傍を import できますが、`..` で外に出ることはできません。import 元のドキュメントがあるツリーに戻ることもできません。ある jail から別の jail へ移るには、必ず対象の jail 名を明示する必要があります。

以下はいずれも拒否されます。

| パス | 理由 |
|------|------|
| `../../etc/passwd` | 封じ込めルートの外に出る |
| `/etc/passwd` | `etc` は登録された jail ではない |
| `/lib/../secret.pgsn` | jail パスに `..` は使えない |
| `/lib/link.pgsn`（`link.pgsn` が jail 外へのシンボリックリンク） | 解決結果が jail の外になる |
| `C:\lib\mod.pgsn` | 絶対パスは jail 名で始まらなければならない |

シンボリックリンクは封じ込め検証の前に展開されるため、jail 内に仕込まれたリンクで脱獄することはできません。

---

## 定義（def）

`def` は名前に値を束縛します。

同じブロックで同じ名前を複数回束縛できます。後の束縛がその位置から先で前の束縛を覆い隠します。書き換えは起きません。前の束縛は、それが既に見えていた場所ではそのまま有効です。つまり代入ではなくシャドーイングです。とくに束縛の値はその束縛が入る*前*のスコープで読まれるので、`<def name="x"><var name="x"/></def>` は自分自身ではなく外側の `x` を指します。自己参照には `recursive="true"` を使ってください。

組み込みの名前も同じ仕組みで最外スコープに束縛されているだけなので、ドキュメントが `head` や `goal` を自分の値に束縛しても構いません。

```xml
<def name="x">expr</def>
```

### `as` 属性（略記）

`def` に `as` 属性を指定すると、値を包む外側のタグ名を省略できます。
`as` は「コンテンツを包む要素」の名前を指定するので、包む要素を書き出さずに済みます。

```xml
<!-- 完全形 -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- 略記 -->
<def name="myGoal" as="Goal">...</def>
```

`<def name="x" as="T">C</def>` と `<def name="x"><T>C</T></def>` は同じ文書の書き分けです。この属性は `<def>` 専用ではありません。コンテンツを持つ要素であればどこでも、`as` はそのコンテンツを包む要素の名前になります。例外は `<from>` と `<import>` で、そこでの `as` は取り込む名前の別名を指定します。その位置で有効なタグ名であれば何でも指定できます（`object` でも `ol` でも `Goal` でも）。唯一の制限は、要素自身が属性を必要とするタグを指定できないことです——`var` は `name`、`get` は `key`、`send` は `method`、名前付きの `class` は `name` が要ります。`as` が動かすのはコンテンツだけで、属性は元の場所に残るからです。

### `typeOf` 属性

値を型と照合します。`<def>` と `<var>` のどちらにも書けます。属性値は
クラスが束縛された**変数名**です。

```xml
<def name="g" typeOf="Goal">
    <Goal><description>system is safe</description><undeveloped/></Goal>
</def>

<var name="g" typeOf="Goal"/>
```

**型付けは構造的です。** ある値が型を満たすのは、その値のクラスが、型の宣言する属性と
メソッドを少なくとも全部宣言しているときです。クラスの出自は関係ありません。`description` と
`defeaters` を持つ自作のクラスは、`Evidence` を継承していなくても `Evidence` を満たしますし、
`Goal` もそれらのラベルを（さらに多く）宣言しているので `Evidence` を満たします。
クラスの**同一性**を比べる場所がどこにもないので、どのコピーについて訊いても答えは同じです。

検査に失敗しても例外にはなりません。値が通らないだけなので、文書は与える値を持たず、
どこで止まったかがパスつきで報告されます。

`<param>` は `typeOf` を取りません。パラメーターは呼ばれたときに決まるので、検査を本体の中に
仕込むことになるからです。使う場所で検査してください。

### 局所定義

`<div>` の中に `<def>` を並べてスコープを限定します。

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- div の値 -->
</div>
```

`<def>` は `<template>` のボディにも、最終的な値要素の前に直接並べることができます。`<div>` で包む必要がありません。

```xml
<template>
    <param name="x"/>
    <def name="doubled"><apply><var name="plus"/><arg var="x"/><arg var="x"/></apply></def>
    <var name="doubled"/>   <!-- 最終値 -->
</template>
```

---

## 変数（var）

定義済みの名前を参照します。

```xml
<var name="x"/>

<!-- 型検査つき -->
<var name="x" typeOf="MyClass"/>
```

### 組み込み（builtin）

以下の名前はあらかじめ定義済みで、`<var name="..."/>` で参照し `apply` に適用できます。これは `pgsn` パッケージが公開する項値の名前とちょうど一致しており、Python から使えるものは同じ名前で XML からも使えます。

- リスト操作: `cons`・`head`・`tail`・`index`・`is_empty`・`concat`・`map_term`・`fold`・`foldr`・`list_all`・`empty`
- 真偽値: `true`・`false`・`if_then_else`・`boolean_and`・`boolean_or`・`boolean_not`・`equal`・`less_than`・`guard`
- 整数: `plus`・`minus`・`times`・`div`・`mod`・`integer_sum`
- レコード: `has_label`・`list_labels`・`add_attribute`・`remove_attribute`・`overwrite_record`・`empty_record`
- 文字列: `format_string`
- クラス／オブジェクト: `define_class`・`instantiate`・`type_of`・`is_subtype`・`base_class`
- その他: `fix`・`repeat`・`undefined`
- GSN コンストラクタ: `goal`・`strategy`・`evidence`・`context`・`assumption`・`defeater`・`undeveloped`・`immediate`・`evidence_as_goal`
- GSN クラス（長い名前）: `goal_class`・`strategy_class`・`evidence_class`・`context_class`・`assumption_class`・`defeater_class`・`gsn_class`・`support_class`・`undeveloped_class`
- GSN クラス（短いエイリアス）: `Goal`・`Strategy`・`Evidence`・`Context`・`Assumption`・`Defeater`・`GSN`・`Support`

例（リストにテンプレートを写像する）:

```xml
<apply>
    <var name="map_term"/>
    <arg var="someTemplate"/>     <!-- 第1引数（テンプレート） -->
    <arg><ol><li>a</li><li>b</li></ol></arg>  <!-- 第2引数（リスト） -->
</apply>
```

---

## テンプレートと適用

### テンプレート定義（template）

関数を値として定義します（λ式相当）。
引数（`param`）には**位置引数**と**キーワード引数**の2種類があります。

- `positional="true"` を付けた `param` が**位置引数**です。
- 付けない `param` が**キーワード引数**です。
- Python と同様、位置引数はすべてキーワード引数より**前に**宣言します（キーワード引数の後ろに位置引数を置くことはできません）。
- **位置引数にデフォルト値は指定できません**（デフォルト値はキーワード引数だけの機能です）。
- 同じ引数を位置でもキーワードでも呼ぶ、という使い方はしません。各引数は宣言時にどちらか一方に固定されます。

```xml
<!-- 引数なし -->
<template>expr</template>

<!-- 位置引数 -->
<template>
    <param name="x" positional="true"/>
    body_expr
</template>

<!-- キーワード引数（デフォルト値も指定可能） -->
<template>
    <param name="arg1">default_expr</param>
    <param name="arg2"/>
    body_expr
</template>

<!-- 位置引数とキーワード引数の混在（位置が先） -->
<template>
    <param name="x" positional="true"/>
    <param name="opt">default_expr</param>
    body_expr
</template>
```

### テンプレート適用（apply）

テンプレートを引数に適用します。
`arg` には**位置引数**（`name` なし）と**キーワード引数**（`name` あり）があり、
位置引数をすべて先に並べ、その後にキーワード引数を並べます。

```xml
<apply>
    expr                      <!-- 適用するテンプレート -->
    <arg>expr1</arg>          <!-- 位置引数（宣言順に解釈） -->
    <arg>expr2</arg>
    <arg name="opt">expr3</arg>  <!-- キーワード引数 -->
</apply>
```

関数が名前付き変数のとき、`template` 属性を使うと内側の `<var>` 要素を省略できます。

```xml
<!-- 略記 -->
<apply template="funcname">
    <arg>expr1</arg>
</apply>

<!-- 完全形（等価） -->
<apply>
    <var name="funcname"/>
    <arg>expr1</arg>
</apply>
```

適用は2項なので、`<arg>` がひとつも無い `<apply>` は何も適用せず、関数そのものになります。`<apply template="f"/>` と `<var name="f"/>` は同じ式です。

---

## クラスとオブジェクト

### クラス定義（class）

```xml
<class name="ClassName">           <!-- クラスの名前（省略可） -->
    <!-- inherit には「クラスに評価される任意の式」を置く。
         var= はその最も一般的な省略形（変数参照）。 -->
    <inherit var="ParentClass"/>       <!-- 継承（省略可） -->
    <attribute name="attr1">default_value</attribute>
    <attribute name="attr2"/>          <!-- デフォルト値なし -->
    <method name="m">
        <!-- 'self' はレシーバーオブジェクトを指し、param として宣言しなくても
             メソッドのbody 内で常に使えます。 -->
        <param name="p1">default</param>
        <param name="p2"/>
        body_expr   <!-- <var name="self"/> でレシーバーにアクセスできる -->
    </method>
</class>
```

> **クラスの名前はラベルであって、クラスを指す手段ではありません。**
> クラスは変数に束縛された通常の値で、名前を引くための表はありません。`<inherit>` と
> `<instanceOf>` はいずれも**クラスに評価される式**を受け取ります（文字列のクラス名では
> ありません）。`<inherit>SomeClass</inherit>` と書くとテキストが文字列 `"SomeClass"`
> として扱われ、クラスとして扱われません。`<inherit var="someClass"/>` のように式を
> 使ってください。
> `name=` が与えるのは「そのクラスが何と呼ばれるか」です。値と一緒に持ち運ばれ、
> そのクラスのインスタンスが何として報告されるかを決めます。`<def>` が導入する名前が
> スコープの中の名前であるのとは別物で、両者を突き合わせる仕組みはありませんし、
> クラスどうしの名前を比べる仕組みもありません。名前を持たないクラスも書けますが、
> そのインスタンスは値に変換できません（何として報告すればよいかが無いため）。
> `as="class"` の略記は属性を持てないので、名前付きのクラスは完全形で書きます:
> `<def name="C"><class name="C">…</class></def>`。

> **型はクラスではありません。**
> `is_subtype` が比べるのは、2つのクラスが宣言する属性名とメソッド名だけで、`inherit` は
> 関与しません。だからクラスは、ラベルを覆っている型すべてを満たします（継承関係の有無は
> 問いません）。逆に「この値はどのクラスに属するか」という問いには答えがなく、
> 「何を持っているか」だけが答えられます。それを尋ねる述語はありません。クラスの等価性は
> 構造比較なので、同一のクラスでも簡約の進み具合が違うコピーどうしは一致せず、答えが
> コピーの出自に左右されてしまうからです。`<object>` の中の `<instanceOf>` はまた別物で、
> 生成するクラスを指す要素です。

### オブジェクト生成（object）

```xml
<object>
    <instanceOf var="MyClass"/>
    <attribute name="attr1">value</attribute>
</object>
```

### キーアクセス（get）

`get` はレコードとオブジェクトの両方に使えます。`key` 属性でラベル名を指定し、`of` 属性で変数レシーバーを略記できます。ラベルを読むこととは、レシーバーにそのラベルを適用することなので、下の3つはまったく同じものです。

```xml
<!-- 略記: key= でラベル名、of= でレシーバー変数を指定 -->
<get key="description" of="my_goal"/>

<!-- レシーバーが複雑な式の場合は子要素に書く -->
<get key="description"><apply template="getGoal"><arg>G1</arg></apply></get>

<!-- Record のキーアクセス（以下3つは等価） -->
<get key="x" of="my_record"/>
<get key="x"><var name="my_record"/></get>
<apply><var name="my_record"/><arg>x</arg></apply>
```

レコードは、作られたときのラベルだけを持ちます。持っていないラベルを読むのは、簡約する規則が無い適用です。
項はそのまま残って正規形に到達しないので、`pgsn doc` や `python_value` は値を得られず、簡約が止まった位置を
パスで示します（[設計の原則](#設計の原則)を参照）。キーを綴り間違えると、ドキュメントは値を持たないまま残り、
穴のまま黙って先へ渡ることはありません。自分で組んだのではないレコードをテンプレートから読めるのは、
そのためです。

### メソッド呼び出し（send）

```xml
<send method="methodName" to="receiverVar">
    <arg name="arg1">expr1</arg>
</send>
```

`method` 属性でメソッド名を指定し、`to` 属性で変数レシーバーを略記できます。
レシーバーが変数以外の複雑な式の場合は `to` を省略し、先頭の子要素として書きます。

```xml
<send method="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

---

## データ型

### リスト（ol）

```xml
<ol>
    <li>expr1</li>
    <li var="x"/>    <!-- 略記 -->
</ol>
```

リストの要素は `ol` だけです。項目の順序は文書が述べていることの一部で、どの出力も書いた順で報告します。
集合はありません。

### 辞書（dl）

キーは文字列リテラルで、`<dt>` のテキストか `key` 属性で書きます。ラベルであって値ではないので、
式は置けません。ラベルを計算して作るレコードは `add_attribute` で組みます。

```xml
<dl>
    <dt>name</dt><dd>value_expr</dd>       <!-- テキストでキーを書く -->
    <dt key="name"/><dd>value_expr</dd>    <!-- 同じキー -->
</dl>
```

### テキスト内のフォーマット文字列

テキストを置ける場所では、`{name}` という記法でスコープ内の変数を埋め込めます。
`format_string` の適用になります。波括弧自体を書きたい場合は `{{` `}}` でエスケープします。

```xml
<template>
    <param name="c" positional="true"/>
    <Evidence>Component {c} のテスト結果</Evidence>
</template>
```

### GSN の地テキストとして description を記述する

GSN ヘッダー要素（`Goal`・`Strategy`・`Evidence`・`Context`・`Assumption`）では、先頭の地テキストが自動的に `description` として扱われます。子要素（`<Strategy>` など）と共存する場合も同じで、`<description>` 要素に書いても同じことを表します。`{name}` 展開もここで使えます。

```xml
<!-- この2つは等価です -->
<Goal>
    システム {name} はセキュアである
    <undeveloped/>
</Goal>

<Goal>
    <description>システム {name} はセキュアである</description>
    <undeveloped/>
</Goal>
```

先頭の地テキストが無い場合、値を表す子要素が1つだけあればそれが description になります。計算した description に `<description>` を被せる必要はありません。

```xml
<Evidence><expr>f"テスト報告書 {i}"</expr></Evidence>
```

値を表す子要素が複数ある場合はエラーになります。どれが description なのかを明示してください。

---

## GSN ノード

GSN ノードは通常の値と同列に扱われます。クラスとして継承・拡張が可能です。

### 共通ヘッダ

GSN ノードはどれも説明（description）から始まり、どれも `Defeater` で異議を立てられます。
`Goal` と `Strategy` はさらに `Context` と `Assumption` で注釈を付けられます。

```xml
<!-- 説明（description要素 または テキスト直書き） -->
<description>説明文</description>

<!-- Context: 議論が成立する文脈。値として任意の式を置ける -->
<Context>テキストによる説明</Context>
<Context var="someObject"/>          <!-- 変数参照 -->
<Context><get key="version" of="release"/></Context>  <!-- 式 -->

<!-- Assumption: 議論が置く仮定。Context と同様、値として任意の式を置ける -->
<Assumption>ゼロデイ攻撃はない</Assumption>
<Assumption var="someObject"/>       <!-- 変数参照 -->
```

**Context と Assumption の使い分け**

`Context` と `Assumption` はどちらもヘッダに付随するドキュメンテーション要素で、値として任意の式（テキスト・変数参照・オブジェクト・リスト等）を1つ置けます。

- `Context` は議論が成立する文脈・前提となる状況や対象を表します。
- `Assumption` は議論が置く仮定を表します。

**どこに書けるか。** `Context` と `Assumption` が付くのは `Goal` と `Strategy` の2つで、
規格が許しているのもこの2つです。戦略は、その推論が依拠する仮定を自分で持てます。
`Evidence` はどちらも取りませんし、`Defeater` も取りません。そこに書いたものは `PGSN.rng` が弾きます。
文書の側は何も言いません。

### Goal

```xml
<Goal>
    <description>システムXはセキュアである</description>
    <Context>規格XXXXによる認証</Context>
    <Assumption>ゼロデイ攻撃はない</Assumption>

    <!-- body は以下のいずれか -->
    <Strategy>...</Strategy>              <!-- Strategy で支持 -->
    <Evidence>...</Evidence>              <!-- Evidence で支持 -->
    <Goal>...</Goal>                      <!-- サブゴールで支持（1つ以上） -->
    <supportedBy var="strategy1"/>        <!-- 変数参照で支持 -->
    <undeveloped/>                        <!-- 未展開 -->
</Goal>
```

> **補足: サブゴールの並記は糖衣構文です**
> Goal の直下に `<Goal>` を複数並べる書き方は、`immediate`（サブゴールを束ねる特殊な Strategy）でラップされます。
> PGSN のコアでは Goal の支持（support）は Strategy か Evidence のいずれかでなければなりません。
> 実行時に計算したゴールのリストを支持にしたい場合は、`immediate` を明示的に適用して Strategy 化します。
>
> ```xml
> <Goal>
>     セキュリティ要件を満たす
>     <supportedBy>
>         <apply><var name="immediate"/><arg var="goals"/></apply>
>     </supportedBy>
> </Goal>
> ```

### Strategy

```xml
<Strategy>
    argument
    <!-- body は以下のいずれか -->
    <Goal>...</Goal>           <!-- サブゴール（1つ以上） -->
    <subGoals var="goals"/>    <!-- 変数参照でまとめて指定 -->
</Strategy>
```

`subGoals` にリスト（`ol`）を渡すことでサブゴールを動的に指定できます。

```xml
<Strategy>
    argument
    <subGoals>
        <ol>
            <li var="goal1"/>
            <li var="goal2"/>
        </ol>
    </subGoals>
</Strategy>
```

### Evidence

Evidence は説明を持ち、その妥当性に異議があれば Defeater を持ちます。

```xml
<Evidence>
    <description>テスト結果報告書</description>
    <Defeater>報告書が最新のリリースより古い</Defeater>
</Evidence>
```

### 反証（Defeater）

GSN v3 で追加された dialectic extension では、*defeater* が議論の一部に対する疑いを記録します。支持ではなく攻撃を表す点が他のノードと違います。どの GSN ノードも defeater を持てます。defeater 自身も GSN ノードなので、さらに反証されることもあります。

```xml
<Goal>システムは安全である
    <Defeater>ハザード H4 が未対応である
        <Evidence>インシデント報告 2026-03</Evidence>
    </Defeater>
    <Defeater>テストスイートが仕様に追従していない
        <Defeater>改訂 7 で更新済みである</Defeater>
    </Defeater>
    <Evidence>テスト報告書</Evidence>
</Goal>
```

書き方は他の GSN ノードと同じで、先頭テキストか `<description>` が description になり、入れ子の `<Evidence>`・`<Strategy>`・`<Goal>`・`<supportedBy>` が support に、入れ子の `<Defeater>` がそれ自身への反証になります。support は省略でき、既定は undeveloped です。対抗論拠を伴う反証は support を埋め、異議を述べるだけの反証は空のままにします。

defeater はゴールだけでなく、戦略やエビデンスにも付きます。

```xml
<Strategy>ハザードごとに議論する
    <Defeater>ハザード一覧が網羅的でない</Defeater>
    <Goal>H1 は緩和されている<Evidence>テスト報告書 H1</Evidence></Goal>
</Strategy>
```

対応する組み込みは `defeater`、クラス値は `defeater_class` です。図では破線の六角形で描かれ、challenge の辺も破線になります。SupportedBy と読み違えないためです。

なお規格そのものには Defeater 要素はありません。規格上の defeater は、Challenges 関係で対象に繋がった普通の Goal または Solution であり、rebutting と undercutting の区別も記法ではなく議論の中身から読み取るものです。PGSN は値の言語で辺を持たないため、攻撃するという役割をクラスとして表現しています。区別は 1 クラスで足ります。

---

## クラスによる GSN の拡張

GSN ノードはクラスとして継承・拡張できます。
拡張したクラスは `<object>` でインスタンス化します（属性を明示します）。

`as="class"` ではなく完全形で書いています。インスタンス化するクラスには自分の名前が要るのに、
`as` は名前を運べないからです。

```xml
<!-- Goal を継承し、属性 URL を追加したクラス -->
<def name="GoalWithURL">
    <class name="GoalWithURL">
        <inherit var="Goal"/>
        <attribute name="URL"/>
    </class>
</def>

<!-- インスタンス化（object 形） -->
<object>
    <instanceOf var="GoalWithURL"/>
    <attribute name="description">システムXはセキュアである</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```

---

## モジュールの例

パラメーターと import を組み合わせた実例です。

```xml
<PGSNModule>
    <!-- 外部から閾値を受け取る -->
    <param name="threshold">100</param>

    <!-- 別ファイルからゴールを持ち込む -->
    <from file="security.pgsn" import="secureGoal" as="G1"/>

    <def name="mainStrategy" as="Strategy">
        テストとレビューによる検証
        <subGoals>
            <ol>
                <li var="G1"/>
            </ol>
        </subGoals>
    </def>

    <def name="main" as="Goal">
        <description>システムはセキュアである</description>
        <Assumption>ゼロデイ攻撃はない</Assumption>
        <supportedBy var="mainStrategy"/>
    </def>
</PGSNModule>
```

`param` を受け取るモジュールは、末尾に単一の値を置く `<PGSN>` ではなく `<PGSNModule>` を使います
（`param` は `<PGSNModule>` の先頭にだけ書けます）。