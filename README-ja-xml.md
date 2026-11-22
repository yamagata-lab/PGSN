# PGSN の XML 構文

この文書は PGSN の XML 構文を定めます。PGSN は GSN（Goal Structuring Notation）をプログラミングの構造で拡張したもので、GSN の要素は値になり、名前を付けたり、テンプレートに渡したり、リストから生成したり、クラスで拡張したりできます。構文の仕様はこの文書で、処理系がこれと違う動きをするところは [known_issues-ja.md](known_issues-ja.md) に挙げてあります。`pgsn` のインストールと実行のしかたは [README-ja.md](README-ja.md) に、この文書の英語版は [README-xml.md](README-xml.md) にあります。

最初の2つの節、[最初の議論](#最初の議論)と [GSN の要素](#gsn-の要素)は、順に読む入門です。残りは参照用です。末尾の[要素の一覧](#要素の一覧)に、すべての要素と属性をまとめてあります。

目次：

1. [最初の議論](#最初の議論)
2. [GSN の要素](#gsn-の要素)
3. [値](#値)
4. [名前と定義](#名前と定義)
5. [略記の属性](#略記の属性)
6. [式（expr）](#式expr)
7. [条件分岐（if・cases）](#条件分岐ifcases)
8. [テンプレートと適用](#テンプレートと適用)
9. [クラスとオブジェクト](#クラスとオブジェクト)
10. [ドキュメントとモジュール](#ドキュメントとモジュール)
11. [組み込み](#組み込み)
12. [原則](#原則)
13. [要素の一覧](#要素の一覧)

---

## 最初の議論

ドキュメントは `<PGSN>` 要素で、その中身は値1つです。ここではゴールが1つです。要素の先頭のテキストがその要素の説明になり、中に入れ子にした要素が、何がそれを支えるか、どんな文脈で述べられているか、何がそれに異議を立てるかを表します。

```xml
<PGSN>
    <Goal>
        The braking system is acceptably safe
        <Context>Braking system, release 2.1</Context>
        <Strategy>
            Argue over each identified hazard
            <Assumption>The hazard list is complete</Assumption>
            <Goal>Hazard H1 (loss of braking) is mitigated
                <Solution>Fault tree analysis FTA-1</Solution>
            </Goal>
            <Goal>Hazard H2 (unintended braking) is mitigated
                <Defeater>The analysis predates the last design change</Defeater>
                <Solution>Test report TR-7</Solution>
            </Goal>
            <Goal>Hazard H3 (delayed braking) is mitigated</Goal>
        </Strategy>
    </Goal>
</PGSN>
```

`pgsn doc` はドキュメントを評価して、議論を木として表示します（図にするのは `pgsn render` です）。

```console
$ pgsn doc braking.xml -o -
Evaluating term 'main'...
Goal: The braking system is acceptably safe
├── Context: Braking system, release 2.1
└── Strategy: Argue over each identified hazard
    ├── Assumption: The hazard list is complete
    ├── Goal: Hazard H1 (loss of braking) is mitigated
    │   └── Solution: Fault tree analysis FTA-1
    ├── Goal: Hazard H2 (unintended braking) is mitigated
    │   ├── Defeater: The analysis predates the last design change
    │   │   └── Undeveloped: 
    │   └── Solution: Test report TR-7
    └── Goal: Hazard H3 (delayed braking) is mitigated
        └── Undeveloped: 

Done.
```

H3 には支持が無いので未展開です。Defeater も、疑いを述べるだけで根拠を示していないので未展開です。

ここまでは、ふつうの GSN を XML で書いただけです。PGSN で書けるのは、3つのハザードのゴールを1つずつ書き出さなくて済むことです。次のドキュメントでは、ハザードをリストに持ち、ハザードのゴールの形を*テンプレート*として一度だけ定義し、`map_term` でリストの各項目にそのテンプレートを適用します。

```xml
<PGSN>
    <def name="hazards"><ol>
        <li><dl><dt>name</dt><dd>H1 (loss of braking)</dd><dt>evidence</dt><dd>Fault tree analysis FTA-1</dd></dl></li>
        <li><dl><dt>name</dt><dd>H2 (unintended braking)</dd><dt>evidence</dt><dd>Test report TR-7</dd></dl></li>
        <li><dl><dt>name</dt><dd>H3 (delayed braking)</dd><dt>evidence</dt><dd>Timing analysis TA-2</dd></dl></li>
    </ol></def>

    <def name="mitigated" as="template">
        <param name="h" positional="true"/>
        <Goal>Hazard {h.name} is mitigated
            <Solution>{h.evidence}</Solution>
        </Goal>
    </def>

    <Goal>
        The braking system is acceptably safe
        <Strategy>
            Argue over each identified hazard
            <subGoals expr="map_term(mitigated, hazards)"/>
        </Strategy>
    </Goal>
</PGSN>
```

```console
$ pgsn doc braking2.xml -o -
Evaluating term 'main'...
Goal: The braking system is acceptably safe
└── Strategy: Argue over each identified hazard
    ├── Goal: Hazard H1 (loss of braking) is mitigated
    │   └── Solution: Fault tree analysis FTA-1
    ├── Goal: Hazard H2 (unintended braking) is mitigated
    │   └── Solution: Test report TR-7
    └── Goal: Hazard H3 (delayed braking) is mitigated
        └── Solution: Timing analysis TA-2

Done.
```

ここで使ったものは参照の部分で説明しています。`<def>` は[定義（def）](#定義def)、`<ol>` と `<dl>` は[リスト（ol）](#リストol)と[レコード（dl）](#レコードdl)、`{h.name}` は[テキスト中の書式文字列](#テキスト中の書式文字列)、`<template>` は[テンプレートと適用](#テンプレートと適用)、`as` と `expr` の属性は[略記の属性](#略記の属性)です。テンプレートは別のファイルに置いて、複数のドキュメントから import することもできます。[ドキュメントとモジュール](#ドキュメントとモジュール)を参照してください。

---

## GSN の要素

GSN の要素は値です。名前に束縛でき、リストに入れられ、テンプレートに渡せて、テンプレートから返せます。

### 説明

GSN の要素（`Goal`・`Strategy`・`Solution`・`Defeater`・`Context`・`Assumption`）はどれも説明（`description`）を持ちます。要素の先頭のテキストが説明になります。子要素があってもなくても同じで、`<description>` 要素に書いても同じことを表します。`{...}` の埋め込みは、ほかのテキストと同じく値で埋まります（[テキスト中の書式文字列](#テキスト中の書式文字列)）。

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

先頭のテキストが無い場合、値を表す子要素が1つだけあれば、それが説明になります。計算した説明に `<description>` を被せる必要はありません。

```xml
<Solution><expr>f"テスト報告書 {i}"</expr></Solution>
```

値を表す子要素が複数ある場合はエラーになります。どれが説明なのかを明示してください。

説明が空や空白だけでも（`<description/>` も含めて）コンパイルエラーにはなりません。空文字列になり（[リテラル](#リテラル)）、[GSN の検査](#gsn-v3-に照らした検査)が報告します。ドキュメントの評価中に計算された説明が空のときと同じです。

### Goal

```xml
<Goal>
    <description>システムXはセキュアである</description>
    <Context>規格XXXXによる認証</Context>
    <Assumption>ゼロデイ攻撃はない</Assumption>

    <!-- 支持は以下のいずれか -->
    <Strategy>...</Strategy>              <!-- Strategy で支持 -->
    <Solution>...</Solution>              <!-- Solution で支持 -->
    <Goal>...</Goal>                      <!-- サブゴールで支持（1つ以上） -->
    <supportedBy var="strategy1"/>        <!-- 計算した値で支持 -->
    <undeveloped/>                        <!-- 未展開 -->
</Goal>
```

Goal の支持はちょうど1つです。支持の無い `<Goal>` は、`<undeveloped/>` を書いたのと同じく未展開になります。

Goal の直下に `<Goal>` を複数並べる書き方は略記で、`immediate` で包まれます。`immediate` はそれらを持つ Strategy を作ります。この Strategy は出力に `immediate` という説明で現れます。ドキュメントの評価中に計算したゴールのリストで Goal を支えるには、そのリストに自分で `immediate` を適用します。

```xml
<Goal>
    セキュリティ要件を満たす
    <supportedBy>
        <apply><var name="immediate"/><arg var="goals"/></apply>
    </supportedBy>
</Goal>
```

### Strategy

```xml
<Strategy>
    argument
    <!-- サブゴールは以下のいずれか -->
    <Goal>...</Goal>           <!-- サブゴールを書き並べる（1つ以上） -->
    <subGoals var="goals"/>    <!-- サブゴールをリストとして計算する -->
</Strategy>
```

Strategy にはサブゴールが要ります。`<Goal>` の子要素も `<subGoals>` も無い `<Strategy>` はコンパイルエラーです（`<Strategy> requires sub-goals or <subGoals>`）。Strategy を未完のままにしておくには、サブゴールの中に `<undeveloped/>` を書きます。単独でも、`<Goal>` と並べてもかまいません。その Strategy は未展開になります。GSN v3 では Goal だけでなく Strategy も未展開にでき、図では未展開の印が付きます。

```xml
<Strategy>ハザードごとに議論する<undeveloped/></Strategy>
```

`<subGoals>` はリスト（`ol`）を取るので、サブゴールを計算できます。

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

変数に入ったゴールを並べるときは、上のように `<subGoals>` を使います。`<Goal var="g"/>` はゴール `g` を表しません。`g` の値を説明とする新しいゴールになります（[略記の属性](#略記の属性)）。

### Solution

Solution は、GSN v3 と同じく、証拠となるものへの参照を示します。説明を持ち、その妥当性に異議があれば Defeater を持ちます。

```xml
<Solution>
    <description>テスト結果報告書</description>
    <Defeater>報告書が最新のリリースより古い</Defeater>
</Solution>
```

### Context と Assumption

```xml
<!-- Context: 議論が成立する文脈 -->
<Context>テキストによる説明</Context>
<Context var="someObject"/>                            <!-- 変数参照 -->
<Context><get key="version" of="release"/></Context>  <!-- 式 -->

<!-- Assumption: 議論が置く仮定 -->
<Assumption>ゼロデイ攻撃はない</Assumption>
<Assumption var="someObject"/>                         <!-- 変数参照 -->
```

- `Context` は議論が置かれる状況や、議論の対象を表します。
- `Assumption` は議論が置く仮定を表します。

`Context` と `Assumption` を書けるのは `Goal` と `Strategy` の中で、GSN v3 がこの2つを付けるのもこの2つです。Strategy は、その推論が依拠する仮定を自分で持てます。`Solution` と `Defeater` はどちらも取りません。`<Context>` と `<Assumption>` はそれだけでは値になりません。計算して作るには、組み込みの `context` か `assumption` を適用します。

どちらも値を1つ持ちます。テキスト・変数参照・オブジェクト・リストなど、何でもかまいません。ただし [GSN の検査](#gsn-v3-に照らした検査)は、空でない文字列以外の値を報告します。GSN ではどの要素も何かを述べるものだからです。

### Defeater

GSN v3 の弁証法的拡張（dialectic extension）では、*Defeater* が議論の一部に対する疑いを記録します。支持ではなく疑いを表す点が、ほかの要素と違います。Goal・Strategy・Solution・Defeater はどれも Defeater を持てます。つまり Defeater にも異議を立てられます。

```xml
<Goal>システムは安全である
    <Defeater>ハザード H4 が未対応である
        <Solution>インシデント報告 2026-03</Solution>
    </Defeater>
    <Defeater>テストスイートが古い
        <Defeater>改訂 7 で更新済みである</Defeater>
    </Defeater>
    <Solution>テスト報告書</Solution>
</Goal>
```

`<Defeater>` は Goal と同じように書きます。先頭のテキストか `<description>` が説明になり、入れ子の `<Solution>`・`<Strategy>`・`<Goal>`・`<supportedBy>` が支持に、入れ子の `<Defeater>` がその Defeater 自身への異議になります。支持は省略でき、デフォルト値は未展開です。根拠を示して異議を立てる Defeater は支持を書き、異議を述べるだけの Defeater は省きます。

Defeater は Goal だけでなく、Strategy や Solution にも付きます。

```xml
<Strategy>ハザードごとに議論する
    <Defeater>ハザード一覧が網羅的でない</Defeater>
    <Goal>H1 は緩和されている<Solution>テスト報告書 H1</Solution></Goal>
</Strategy>
```

対応する組み込みは `defeater`、クラス値は `defeater_class` です。

Defeater 要素は PGSN 独自のものです。GSN v3 には Defeater 要素がなく、そこでの defeater は、Challenges 関係で対象に繋がった普通の Goal か Solution です。異議を立てる役割を PGSN が要素にした理由は [PGSN-implementation.md](PGSN-implementation.md) にあります。

### 要素ごとに取れるもの

| 要素 | 説明 | Context・Assumption | Defeater | 支持 |
|---|---|---|---|---|
| `Goal` | あり | 取れる | 取れる | `Strategy`・`Solution`・`Goal`…・`supportedBy`・`undeveloped` のどれか1つ。無ければ未展開 |
| `Strategy` | あり | 取れる | 取れる | `Goal`… と `undeveloped`、または `subGoals`。必須 |
| `Solution` | あり | 取れない | 取れる | なし |
| `Defeater` | あり | 取れない | 取れる | 省略可：`Solution`・`Strategy`・`Goal`…・`supportedBy`。無ければ未展開 |
| `Context`・`Assumption` | あり | 取れない | 取れない | なし |

GSN の要素は評価されると GSN のクラスのオブジェクトになります。その属性は [`<get>`](#ラベルの読み出しget) で読めて、[`<object>`](#オブジェクトobject) で並べて指定できます。

| クラス | 属性 |
|---|---|
| `Goal` | `description`・`contexts`・`assumptions`・`defeaters`・`support` |
| `Strategy` | `description`・`contexts`・`assumptions`・`defeaters`・`sub_goals` |
| `Solution`・`Context`・`Assumption` | `description`・`defeaters` |
| `Defeater` | `description`・`defeaters`・`support` |

### GSN v3 に照らした検査

ドキュメントはどの位置にどんな値でも置けるので、評価できても GSN Community Standard 第3版（GSN v3）が許さない構造になることがあります。`pgsn doc` と `pgsn render` は、評価結果をドキュメントが破りうる規則に照らし、規則を破る要素ごとに、その識別子と木の中での位置を添えて警告を表示します。

```xml
<PGSN><Goal>System is secure<Strategy>Break into sub-goals<subGoals><ol/></subGoals></Strategy></Goal></PGSN>
```

```console
$ pgsn doc check.xml -o -
Evaluating term 'main'...
Warning: S1 at <root>.support: a strategy relates a goal to supporting goals, but this one has none
Goal: System is secure
└── Strategy: Break into sub-goals

Done.
```

規則は次のとおりです。

1. Goal を支持するのは Strategy・Solution・サブゴールのどれかで、Strategy を支持するのは Goal である。
2. 要素の contexts は Context、assumptions は Assumption である。
3. Strategy はサブゴールを1つ以上持つ。
4. 要素に異議を立てるのは Defeater である。
5. どの要素も、説明が空でない文字列である。
6. 構造の一番上が Goal である。

`--strict` を付けると違反はエラーになり、何も書き出さずに終了コード 1 で終わります。同じ検査は Python の `gsn_violations` でも行えます（[README-ja-api.md](README-ja-api.md#結果の読み出し)）。

### 図の描きかた

`pgsn render` は評価結果を GSN v3 に沿って描きます。

- どの要素にも、接頭辞と番号からなる識別子が付きます。接頭辞は、Goal が G、Strategy が S、Solution が Sn、Context が C、Assumption が A、Defeater が CG です。番号は種類ごとに、図が構造をたどる順に振られます。深さ優先で、1つの要素の中では contexts・assumptions・defeaters が支持より先です。GSN の検査の警告も同じ識別子を使います。識別子は図のラベルで、ドキュメントから参照できる名前ではありません。
- 未展開の Goal と Strategy には、箱の下に ◇ の印が付きます。`undeveloped` はそれ自体の要素としては描かれません。支持の無い Defeater には印が付きません。
- SupportedBy は塗りつぶしの矢じり、InContextOf は白抜きの矢じりです。Assumption には A の印が付きます。
- Defeater は破線の六角形で描かれ、その Challenges 関係は、異議の対象を指す開いた矢じりの破線で描かれます。SupportedBy と読み違えないためです。六角形は PGSN 独自の形で、GSN v3 は異議を立てる要素を普通の Goal や Solution として描きます。

---

## 値

コンテンツを受け取る要素は、どれも**式**（評価されて値になるもの）を期待します。名前を書くための特別なスロットも、クラス名を表す文字列もありません。

この節の例では、`<def name="x">` で名前を束縛し、`<var name="x"/>` でそれを参照します。この2つは[名前と定義](#名前と定義)で説明します。

> **重要な原則：裸のテキストは String リテラルになります。**
> 要素の中にテキストを直接書くと、それは `String` 値になります。
> `<inherit>Goal</inherit>` は Goal クラスを参照しません——文字列 `"Goal"` を生成するだけで、クラスではありません。変数を参照するには `<var>` か `var=` 属性を使います。

```xml
<!-- NG: テキストは文字列 "Goal" になり、クラスとして扱われない -->
<inherit>Goal</inherit>

<!-- OK: var= は変数参照の略記 -->
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
| 裸のテキスト | `String`。前後の空白は除かれ、`{...}` は値で埋まります（[テキスト中の書式文字列](#テキスト中の書式文字列)を参照） |
| `<num>3</num>` | `Integer`。`-3` や `1_000` のような10進の整数です。PGSN に浮動小数点数はありません |
| `<str> a {b} </str>` | `String`。書いたとおりに解釈され、空白は保たれ、`{...}` は埋まりません |

空のコンテンツも空文字列です。`<li/>`・`<dd/>`・`<def name="x"/>`・`<description/>` はどれも `""` を表します。中身の無い要素は空のテキストを持つからです。`<x/>` と `<x></x>` は同じものです。例外が2つあります。中身がリストでなければならない要素（`<ol/>` と `<subGoals/>`）は空リストを表します。空の `<arg>` は何も渡さないので、パラメーターはデフォルト値をとります（[テンプレート適用](#テンプレート適用apply)を参照）。

`<num>` が必要なのは、数字に見えても裸のテキストは文字列のままだからです。おかげでゴールに「2024年度の監査に合格」と書いても年が整数になりません。一方、算術の組み込みは整数しか受け取らないので、`<arg>3</arg>` は文字列を渡すことになり、和は計算されません。`<arg><num>3</num></arg>` と書いてください。

### テキスト中の書式文字列

テキストが値を表す場所では、`{...}` で値を埋め込めます。波括弧の中は [`<expr>`](#式expr) と同じ式なので、`{c}` は変数 `c`、`{n + 1}` は `n` より1大きい値、`{h.name}` はレコード `h` のラベル `name` の値です。埋め込む値は文字列・整数・真偽値のどれかでなければなりません。波括弧そのものを書くには `{{` `}}` とエスケープします。このテキストは組み込みの `format_string` の適用になります。

テキストはコンパイルのときには検査しません。式として読めない埋め込みや、対になっていない波括弧は、書いたままテキストに残り、ドキュメントを評価するときに `pgsn doc` が報告します。

```xml
<template>
    <param name="c" positional="true"/>
    <Solution>Component {c} のテスト結果</Solution>
</template>
```

### リスト（ol）

```xml
<ol>
    <li>expr1</li>
    <li var="x"/>    <!-- 略記 -->
</ol>
```

リストを書く要素は `ol` だけで、項目の順序はドキュメントが述べていることの一部です。どの出力も書いた順に報告します。集合はありません。

### レコード（dl）

レコードはラベルに値を対応づけます。ラベルは文字列リテラルで、`<dt>` のテキストか、その `key` 属性で書きます。式ではないので、ラベルを計算して作るレコードは組み込みの `add_attribute` で組みます。

```xml
<dl>
    <dt>name</dt><dd>value_expr</dd>       <!-- ラベルをテキストで書く -->
    <dt key="name"/><dd>value_expr</dd>    <!-- 同じラベル -->
</dl>
```

レコードは [`<get>`](#ラベルの読み出しget) で読みます。

---

## 名前と定義

### 名前

*名前*とは、`<def>` と `<param>` が導入し `<var>` が参照するものです。*ラベル*とは、レコードやオブジェクトを読むときに使うものです。2つは別の規則に従います。

| 名前を持つ属性 | ラベルを持つ属性 |
|---|---|
| `<def>`・`<param>`・`<var>`・`<arg>` の `name` | `<get>` と `<dt>` の `key` |
| `<def>`・`<var>` の `typeOf` | `<send>` の `method` |
| `<from>`・`<import>` の `as` | `<attribute>` と `<method>` の `name` |
| `<apply>` の `template`、`<get>` の `of`、`<send>` の `to` | `<class>` の `name`（クラスが何と呼ばれるか） |
| 略記の `var` 属性 | |

名前は文字で始まり、以降は文字・数字・アンダースコアを続けられます。文字は ASCII に限りません。`ゴール` は名前として使えます。ただし先頭にアンダースコアは**使えません**。処理系が予約しています。Python の予約語（`and`・`if`・`lambda`・`None`・`True` など）も名前ではありません。[式](#式expr)がそれを予約語として持つからで、こうしておけば `<def>` で束縛できる名前はどれも式に書けます。`match` や `type` のような Python のソフトキーワードは名前です。

ラベルは任意の文字列です。

### 定義（def）

`<def>` は、それがあるブロックの残りの部分で、名前に値を束縛します。

```xml
<def name="x">expr</def>
```

同じブロックで同じ名前を複数回束縛できます。後の束縛が、その位置から先で前の束縛を覆い隠します。何も書き換わりません。前の束縛は、それが既に見えていた場所ではそのまま有効です。つまり代入ではなくシャドーイングです。束縛の値はその束縛が入る*前*のスコープで読まれるので、`<def name="x"><var name="x"/></def>` は自分自身ではなく外側の `x` を指します。自己参照は[再帰的な定義](#再帰的な定義)を参照してください。

組み込みの名前も同じ仕組みで最外スコープに束縛されているだけなので、ドキュメントが `head` や `goal` を自分の値に束縛してもかまいません。

### 局所定義

`<div>` の中に `<def>` を並べてスコープを限定します。`<div>` の最後の項目がその値です。

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- div の値 -->
</div>
```

`<def>` は `<template>` の本体にも、最後の値の前に直接並べられます。`<div>` で包む必要はありません。

```xml
<template>
    <param name="x"/>
    <def name="doubled"><apply><var name="plus"/><arg var="x"/><arg var="x"/></apply></def>
    <var name="doubled"/>   <!-- 最後の値 -->
</template>
```

### 再帰的な定義

`recursive="true"` を付けると、定義がそれ自身の値の中から見えるようになり、テンプレートが自分を呼べます。

```xml
<def name="countdown" recursive="true" as="template">
    <param name="n" positional="true"/>
    <if>
        <cond expr="n == 0"/>
        <then><ol/></then>
        <else expr="cons(n, countdown(n - 1))"/>
    </if>
</def>
```

再帰は条件分岐（[`<if>` か `<cases>`](#条件分岐ifcases)）で止めます。選ばれた枝だけが評価されるからです。見えるようになるのはその定義自身だけなので、2つの定義が互いを参照することはできません。

### 変数（var）

`<var>` は、先に束縛された名前か[組み込み](#組み込み)を参照します。

```xml
<var name="x"/>

<!-- 型検査つき -->
<var name="x" typeOf="MyClass"/>
```

### 型の検査（typeOf）

`typeOf` は値を型と照合します。`<def>` と `<var>` のどちらにも書けます。属性値は、クラスが束縛された**名前**です。

```xml
<def name="g" typeOf="Goal">
    <Goal><description>system is safe</description><undeveloped/></Goal>
</def>

<var name="g" typeOf="Goal"/>
```

**型付けは構造的です。** ある値が型を満たすのは、その値のクラスが、型の宣言する属性とメソッドを少なくとも全部宣言しているときです。クラスの出自は関係ありません。`description` と `defeaters` を持つ自作のクラスは、`Solution` を継承していなくても `Solution` を満たしますし、`Goal` もそれらのラベルを含めて宣言しているので `Solution` を満たします。クラスの**同一性**を比べる場所がどこにもないので、どのコピーについて訊いても答えは同じです。

検査に失敗しても、その場ではエラーになりません。値が通らないだけなので、ドキュメントは値を持たず、`pgsn doc` がどこで止まったかをパスで報告します（[原則](#原則)）。

`<param>` は `typeOf` を取りません。使う場所で検査してください。

---

## 略記の属性

略記の属性はコンテンツの代わりです。属性を付けた要素は、そのコンテンツを書き出した要素と同じものです。どの略記も、表に特に書いていなければ、コンテンツを取る要素ならどこにでも書けます。

| 属性 | 表すもの | 書ける場所 |
|---|---|---|
| `var="x"` | コンテンツ `<var name="x"/>` | コンテンツを取る要素すべて |
| `expr="e"` | コンテンツ `<expr>e</expr>` | コンテンツを取る要素すべて |
| `as="T"` | コンテンツを `<T>…</T>` で包むこと | コンテンツを取る要素すべて。ただし `<from>` と `<import>` では `as` は名前の付け替え |
| `template="f"` | 関数としての `<var name="f"/>` | `<apply>` |
| `of="r"` | レシーバーとしての `<var name="r"/>` | `<get>` |
| `to="o"` | レシーバーとしての `<var name="o"/>` | `<send>` |
| `key="k"` | テキスト `k` | `<dt>` |

`var` や `expr` と、要素自身のコンテンツを両方持つことはできません（`<li> has both an 'expr' attribute and content of its own`）。

### var

```xml
<!-- 完全形 -->
<tag><var name="x"/></tag>

<!-- 略記 -->
<tag var="x"/>
```

### expr

```xml
<!-- 完全形 -->
<arg><expr>i + 1</expr></arg>

<!-- 略記 -->
<arg expr="i + 1"/>
```

XML の都合で2点、注意が要ります。属性値の中では `<` を `&lt;` と書く必要があり、f-string を書くなら属性を `'` で囲まないと、中の `"` で属性が閉じてしまいます。

```xml
<def name="label" expr='f"コンポーネント {i}"'/>
<li expr="i &lt; n"/>
```

### as

`as` はコンテンツを包む要素の名前を指定するので、包む要素を書き出さずに済みます。

```xml
<!-- 完全形 -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- 略記 -->
<def name="myGoal" as="Goal">...</def>
```

その位置で有効なタグ名なら、`object` でも `ol` でも `Goal` でも指定できます。

- **例外：** `<from>` と `<import>` では、`as` は取り込む名前の別名を指定します。
- **制限：** 要素自身が属性を必要とするタグは指定できません。`var` は `name`、`get` は `key`、`send` は `method`、名前付きの `class` は `name` が要ります。`as` が動かすのはコンテンツだけで、属性は元の場所に残るからです。

---

## 式（expr）

算術を `<apply>` で書くのは重いので、`<expr>` では Python と同じように式を書けます。

```xml
<def name="next"><expr>i + 1</expr></def>
<def name="label"><expr>f"コンポーネント {i}（全 {total} 個中）"</expr></def>
<def name="size"><expr>"large" if count > 10 else "small"</expr></def>
```

`<expr>` は略記であって、それ以上のものではありません。コンパイルの前に、書かれた位置で、それが略している要素に展開されます。演算子は対応する組み込みの適用に、名前は `<var>` に、呼び出しは `<apply>` に、属性は `<get>` になります。したがって式の中の名前は、その位置に `<var>` を書いたときと同じものを指し、式を通してしか届かないものはありません。

### 式の中に書けるもの

文法は Python の式の一部で、Python と同じように読みます。

| | |
|---|---|
| 整数 | `3`、`1_000`、`0x1F`、`0o17`、`0b101` |
| 文字列 | `"text"`、`'text'`、`"""text"""`、`r"\d"`。エスケープは Python と同じで、隣り合う文字列はつながります |
| f-string | `f"コンポーネント {i}（全 {total} 個中）"`、`f"残り {i + 1} 個"` |
| 真偽値 | `True`、`False` |
| 名前 | `i` — `<var name="i"/>` になります |
| 算術 | `+`、`-`、`*`、`//`、`%`、単項の `-` と `+` |
| 比較 | `==`、`!=`、`<`、`<=`、`>`、`>=`。Python と同じくつなげられて、`a < b < c` は `a < b and b < c` です |
| 論理 | `and`、`or`、`not` |
| 条件式 | `x if c else y` — 選ばれた枝だけが評価されます |
| 呼び出し | `f(x, k=1)` — `<apply>` になります。`f()` はキーワードパラメーターをすべてデフォルト値にします |
| 属性 | `r.key` — `<get key="key">` になります。`obj.m(x)` はメソッドの呼び出しです |
| 括弧 | `(i + 1) * 2` |

演算子の結合の強さは Python と同じで、弱いほうから条件式、`or`、`and`、`not`、比較、`+` と `-`、`*`・`//`・`%`、単項の演算子、呼び出しと属性の順です。

これ以外は、何が見つかったかを示すエラーで拒否されます。とくに、添字（`xs[0]`）、リスト・辞書・タプルの表示（`[a, b]`。リストは `<ol>` で組みます）、`lambda`、内包表記、`in`、`is` はありません。`None` も、PGSN に対応するものが無いのでありません。PGSN には浮動小数点数が無いので浮動小数点数はエラーで、累乗の組み込みも無いので `**` もエラーです。

f-string の埋め込みは式です。変換（`!r`）・書式指定（`:>4`）・`=` は書式文字列に対応するものが無いのでエラーで、対になっていない波括弧もエラーです。`{{` と `}}` は波括弧そのものです。埋め込みの中には、もう一方の引用符で文字列リテラルを書けます。

`True` と `False` は、演算子がつねに組み込みを指すのと同じく、つねに真偽値を表します。`true` と `false` はその組み込みが束縛されている名前で、ほかの名前と同じ扱いです。

### 注意点が3つ

XML では `<` をエスケープする必要があります。`i &lt; n` と書くか、`CDATA` で囲みます。

```xml
<expr>i &lt; n</expr>
<expr><![CDATA[i < n]]></expr>
```

`>` はエスケープ不要なので、`n > i` と書き換えるほうが楽なことも多いです。

`//` が整数除算です。`7 // 2` は `3` になります。`//` と `%` は Python と同じく負の無限大の方向に丸めるので、`-7 // 2` は `-4` です。`/` は同義語として受け付けず、エラーにしています。

**演算子は再定義できません。** `plus` という名前を束縛しているスコープの中でも、`1 + 2` は加算のままです。

### 値の比較

大小比較（`<`・`<=`・`>`・`>=`）は整数だけを比べるので、`"a" < "b"` には値がありません。

等価比較（`==`・`!=`）はデータを比べます。データとは、基本値（文字列・整数・真偽値・`undefined`）と、それらから組んだリストとレコードです。したがって `"a" == "a"` は `True` ですが、関数どうし・クラスどうし・GSN ノードどうしの比較には、`"a" < "b"` と同じく値がありません。

リストが空かどうかは `is_empty` を適用して調べます。`empty` との比較で答えが出るのは、データのリストに限られます。

---

## 条件分岐（if・cases）

`if_then_else` は組み込みなので普通に適用もできますが、二分岐をその書き方で書くと読みにくくなります。`<if>` は同じことを、部分に名前を付けて書きます。

```xml
<if>
    <cond expr="i &lt; threshold"/>
    <then>予算内</then>
    <else>予算超過</else>
</if>
```

`<else>` は必須です。選ばれなかった枝は評価されないので、条件分岐で再帰を止められます。

条件が連なる場合は `<cases>` を使います。`<cond>` が成り立つ最初の `<case>` を選び、どれも成り立たなければ `<else>` に落ちます。

```xml
<cases>
    <case><cond expr="severity == 0"/><then>無視できる</then></case>
    <case><cond expr="severity &lt; 3"/><then>許容できる</then></case>
    <else>許容できない</else>
</cases>
```

ここでも `<else>` は必須です。無いと、どの `<case>` にも当たらなかった `<cases>` には返す値がなく、間違いが書いた場所から遠いところで表に出ます。

条件は真偽値か整数です。正の整数は真、0 と負の整数は偽として扱われます。`and`・`or`・`not` も整数を同じように扱います。それ以外の条件、たとえば文字列を与えると、その条件分岐は値を持ちません。

`<cond>`・`<then>`・`<else>` はいずれも値を包むだけのラッパーなので、値の書き方はどれでも使えます。`var` と `expr` の略記も含みます。

どちらの形式も `if_then_else` 組み込みの適用を表します。どちらもどの束縛にも横取りされない形で組み込みを指すので、`if_then_else` という名前を束縛しているスコープの中でも `<if>` は条件分岐のままです。

---

## テンプレートと適用

### パラメーター（param）

`<param>` は、それを囲む要素が外から受け取る名前を宣言します。パラメーターを取る要素は3つあります。`<template>` はそれを呼ぶ `<apply>` から、`<method>` はそれを起動する `<send>` から、`<PGSNModule>` はそれを import するドキュメントから受け取ります。パラメーターは要素の中の先頭に、ほかのものより前に書きます。

```xml
<param name="A1"/>

<!-- デフォルト値付き -->
<param name="threshold">100</param>
```

パラメーターは**位置パラメーター**か**キーワードパラメーター**のどちらかです。

- `positional="true"` を付けた `param` が**位置パラメーター**です。
- 付けない `param` が**キーワードパラメーター**です。
- Python と同様、位置パラメーターはすべてキーワードパラメーターより**前に**宣言します。
- **位置パラメーターにデフォルト値は指定できません。** デフォルト値はキーワードパラメーターだけの機能です。
- 位置パラメーターには位置引数で、キーワードパラメーターには名前付きの引数で渡します。

### テンプレート定義（template）

`<template>` は関数を値として作ります。

```xml
<!-- パラメーターなし -->
<template>expr</template>

<!-- 位置パラメーター -->
<template>
    <param name="x" positional="true"/>
    body_expr
</template>

<!-- キーワードパラメーター（デフォルト値は省略可） -->
<template>
    <param name="arg1">default_expr</param>
    <param name="arg2"/>
    body_expr
</template>

<!-- 混在（位置が先、キーワードが後） -->
<template>
    <param name="x" positional="true"/>
    <param name="opt">default_expr</param>
    body_expr
</template>
```

### テンプレート適用（apply）

`<apply>` はテンプレートを引数に適用します。`name` の無い `<arg>` が**位置引数**、`name` のある `<arg>` が**キーワード引数**です。位置引数をすべて先に並べ、その後にキーワード引数を並べます。

```xml
<apply>
    expr                      <!-- 適用するテンプレート -->
    <arg>expr1</arg>          <!-- 位置引数（宣言順に対応） -->
    <arg>expr2</arg>
    <arg name="opt">expr3</arg>  <!-- キーワード引数 -->
</apply>
```

関数が名前の付いた変数のときは、`template` 属性を使うと内側の `<var>` 要素を省けます。

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

**キーワード引数はまとめて渡されます。** キーワードパラメーターを持つテンプレートは、それらを位置引数の後に、まとめて1つの引数として受け取ります。呼び出しで省いたキーワードパラメーターはデフォルト値をとります。ところが、キーワード引数を1つも渡さない呼び出しでは、テンプレートはそれを待ったままになります。結果はまだ関数で、`pgsn doc` は `a function is not a value; an argument may be missing` と報告します。中身の無い `<arg>` は何も渡しませんが、キーワード引数として数えます。空の `<arg name="x"/>` では `x` がデフォルト値をとり、名前の無い空の `<arg/>` ではすべてのキーワードパラメーターがデフォルト値をとります。位置引数の後に置きます。

```xml
<apply template="f"><arg/></apply>                    <!-- キーワードパラメーターはすべてデフォルト値 -->
<apply template="f"><arg>expr1</arg><arg/></apply>    <!-- 位置引数を1つ渡し、残りはデフォルト値 -->
```

式でも同じで、キーワードパラメーターを持つテンプレートに `f(x)` と書くと、結果はまだ関数です。`f(x, k=…)` と書くか、デフォルト値をとるなら `f(x)()` と書きます。

`<arg>` が1つも無い `<apply>` は関数そのものです。`<apply template="f"/>` と `<var name="f"/>` は同じです。

---

## クラスとオブジェクト

### クラス定義（class）

```xml
<class name="ClassName">           <!-- クラスの名前（省略可） -->
    <!-- inherit には「クラスに評価される任意の式」を置く。
         var= はその最も一般的な略記（変数参照）。 -->
    <inherit var="ParentClass"/>       <!-- 継承（省略可） -->
    <attribute name="attr1">default_value</attribute>
    <attribute name="attr2"/>          <!-- デフォルト値なし -->
    <method name="m">
        <!-- 'self' はレシーバーオブジェクトを指し、param として宣言しなくても
             メソッドの本体で常に使えます。 -->
        <param name="p1">default</param>
        <param name="p2"/>
        body_expr   <!-- <var name="self"/> でレシーバーにアクセスできる -->
    </method>
</class>
```

> **クラスの名前はラベルであって、クラスを指す手段ではありません。**
> クラスは普通の値で、名前を引くための表はありません。`<inherit>` と
> `<instanceOf>` はいずれも**クラスに評価される式**を受け取ります（文字列のクラス名では
> ありません）。`<inherit>SomeClass</inherit>` は文字列 `"SomeClass"` で、クラスでは
> ありません。`<inherit var="SomeClass"/>` のように式を使ってください。
>
> `name=` が与えるのは「そのクラスが何と呼ばれるか」です。値と一緒に持ち運ばれ、
> そのクラスのインスタンスが何として報告されるかを決めます。`<def>` が導入する名前が
> スコープの中の名前であるのとは別物で、両者を突き合わせる仕組みはありませんし、
> クラスどうしの名前を比べる仕組みもありません。名前を持たないクラスも書けますが、
> そのインスタンスは表示も描画もできません（何として報告すればよいかが無いため）。
> `as="class"` の略記は属性を持てないので、名前付きのクラスは完全形で書きます:
> `<def name="C"><class name="C">…</class></def>`。

> **型はクラスではありません。**
> `is_subtype` が比べるのは、2つのクラスが宣言する属性名とメソッド名だけで、`inherit` は
> 関与しません。したがってクラスは、ラベルを覆っている型すべてを満たします（継承関係の
> 有無は問いません）。「この値はどのクラスに属するか」を尋ねる方法はなく、
> 「何を持っているか」だけが尋ねられます。`<object>` の中の `<instanceOf>` はまた別物で、
> 生成するクラスを指す要素です。

### オブジェクト（object）

```xml
<object>
    <instanceOf var="MyClass"/>
    <attribute name="attr1">value</attribute>
</object>
```

`<object>` は、クラスの属性のうちデフォルト値の無いものをすべて与え、クラスが宣言していない属性は与えません。そうでなければ、そのオブジェクトは値を持ちません。

### ラベルの読み出し（get）

`<get>` はレコードやオブジェクトのラベルを読みます。`key` 属性がラベルを、`of` 属性がレシーバーの入った変数を指定します。下の3つは同じです。

```xml
<get key="x" of="my_record"/>
<get key="x"><var name="my_record"/></get>
<apply><var name="my_record"/><arg>x</arg></apply>
```

レシーバーが複雑な式の場合は、子要素として書きます。

```xml
<get key="description"><apply template="getGoal"><arg>G1</arg></apply></get>
```

レコードは、作られたときのラベルだけを持ちます。持っていないラベルを読むと値が得られず、ドキュメント全体が値を持たなくなります。`pgsn doc` は評価が止まった位置をパスで報告します（[原則](#原則)を参照）。キーを綴り間違えるとドキュメント全体が値を持たなくなるので、穴が空いたまま黙って先へ渡ることはありません。したがって、自分で組んだのではないレコードをテンプレートから読んでも安全です。

### メソッド呼び出し（send）

```xml
<send method="methodName" to="receiverVar">
    <arg name="arg1">expr1</arg>
</send>
```

`method` 属性でメソッド名を、`to` 属性でレシーバーの入った変数を指定します。レシーバーが変数以外の複雑な式の場合は `to` を省き、先頭の子要素として書きます。

```xml
<send method="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

### GSN の拡張

GSN のクラスは継承して拡張できます。拡張したクラスは `<object>` でインスタンス化し、そのクラスがデフォルト値を与えていない属性を並べます（GSN のクラスの属性は[要素ごとに取れるもの](#要素ごとに取れるもの)を参照）。クラスは完全形で書きます。インスタンス化するクラスには自分の名前が要るのに、`as` は名前を運べないからです。

```xml
<!-- Goal を継承し、属性 URL を追加したクラス -->
<def name="GoalWithURL">
    <class name="GoalWithURL">
        <inherit var="Goal"/>
        <attribute name="URL"/>
    </class>
</def>

<!-- インスタンス化 -->
<object>
    <instanceOf var="GoalWithURL"/>
    <attribute name="description">システムXはセキュアである</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```

---

## ドキュメントとモジュール

`pgsn` が受け付けるのは、ファイル名が `.xml` で終わるドキュメントです。ルート要素は `<PGSN>` か `<PGSNModule>` です。

### `<PGSN>` — 値を持つドキュメント

`<PGSN>` ドキュメントは値を1つ持ち、`pgsn doc` はそれを表示し、`pgsn render` はそれを描きます。`<param>` は**使えません**。

```xml
<PGSN>
    <from file="..."/>         <!-- import（0個以上） -->
    <def name="x">...</def>    <!-- 定義（0個以上） -->
    ...                        <!-- 値（1つ） -->
</PGSN>
```

### `<PGSNModule>` — 再利用するモジュール

モジュールは自分の値を持ちません。ほかのドキュメントが import する定義を提供し、そのドキュメントからパラメーターを受け取れます。`<param>` は先頭に書きます。

```xml
<PGSNModule>
    <param name="p"/>          <!-- パラメーター（0個以上、先頭に書く） -->
    <from file="..."/>         <!-- import（0個以上） -->
    <def name="x">...</def>    <!-- 定義（0個以上） -->
</PGSNModule>
```

どちらの形式でも、`<from>` と `<def>` は自由に混ぜて並べられます。モジュールは `pgsn doc` に直接渡せません（`Expected <PGSN>, got <PGSNModule>`）。`<PGSN>` ドキュメントから import して使います。

**モジュールは閉じています。** モジュールが使う名前は、パラメーター、自分で定義するか import した名前、組み込みのどれかです。したがって、モジュールが import する側のドキュメントから値を受け取るのは、パラメーターを通してだけです。それ以外の名前を使うモジュールは、import したときにその名前を挙げて拒否されます。`<PGSN>` ドキュメントにはこの制限はなく、束縛されていない名前があればそこで評価が止まります（[原則](#原則)を参照）。

### import（from）

`<from>` は、別のファイルで定義された名前を持ち込みます。ドキュメントが届くのは、許可された範囲のファイルだけです。[import パスと jail](#import-パスと-jail) を参照してください。

```xml
<!-- 名前を1つ、別名を付けて -->
<from file="security.xml" import="secureGoal" as="G1"/>

<!-- 名前を複数 -->
<from file="evidence.xml">
    <import name="auditEvidence"/>
    <import name="testReport" as="TR"/>
</from>

<!-- モジュールにパラメーターを渡して -->
<from file="other.xml">
    <import name="someGoal" as="G2"/>
    <arg name="A1" var="A1"/>
    <arg name="threshold" var="threshold"/>
</from>
```

### 値としてのモジュール

値が期待される位置に書いた `<from>` は、何も取り出していないモジュールのレコードを表します。こう書くとモジュールは普通の値になります。`<def>` で束縛したり、リストに入れたり、テンプレートに渡したりできます。

```xml
<def name="lib"><from file="security.xml"/></def>
<get key="secureGoal" of="lib"/>
```

import の時点で名前を選び出すのは上の形式の役目なので、2つの書き方は混ざりません。値として使う `<from>` は `import` を取らず、束縛として使う `<from>` は `import` を必要とします。

### 例

閾値を受け取り、別ファイルからゴールを import するモジュールです。

```xml
<PGSNModule>
    <!-- 外部から閾値を受け取る -->
    <param name="threshold">100</param>

    <!-- 別ファイルからゴールを持ち込む -->
    <from file="security.xml" import="secureGoal" as="G1"/>

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
        <Assumption>毎秒 {threshold} リクエストを超えない</Assumption>
        <supportedBy var="mainStrategy"/>
    </def>
</PGSNModule>
```

このモジュールから自分の閾値で `main` を import し、それを値とする `<PGSN>` ドキュメントです。

```xml
<PGSN>
    <from file="module.xml" import="main">
        <arg name="threshold"><num>5</num></arg>
    </from>
    <var name="main"/>
</PGSN>
```

### import パスと jail

ドキュメントはあるディレクトリツリー（*封じ込めルート*）に閉じ込められており、`file` にはその中のファイルしか書けません。パスの書き方は2通りあります。

**相対パス**は、import する側のドキュメントがあるディレクトリを基準に解決されます。

```xml
<from file="modules/security.xml" import="secureGoal"/>
<from file="../shared/evidence.xml" import="auditEvidence"/>
```

`..` は使えますが、結果が封じ込めルートの内側に留まる場合に限ります。パスを指定して直接開いたドキュメントのルートは、それを含む登録済みの jail があればその jail、なければそのドキュメント自身が置かれているディレクトリです。つまり既定では、隣接するファイルとその配下には届き、それより上には届きません。

**jail パス**は `/` で始まり、先頭の要素が *jail* の名前になります。jail は PGSN を実行する側が登録するディレクトリルートです。

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

ここで `lib` はディスク上のディレクトリ名ではなく jail 名です。コマンドラインか API で与えた jail の表を使って解決されます（`/opt/pgsn-lib` は、共有モジュールを置いた実在のディレクトリに読み替えてください）。

```console
$ pgsn doc main.xml -o - --jail lib=/opt/pgsn-lib
```

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

ドキュメント側から未登録の jail を指定する手段はなく、jail の背後にある実際のディレクトリ構成を知る手段もありません。jail 名に使えるのは ASCII の英数字と `_`、`-` だけです。

import が jail に入ると、その jail が import 先モジュールの封じ込めルートになります。jail 内のモジュールは相対パスで近傍を import できますが、`..` で外に出ることはできません。import 元のドキュメントがあるツリーに戻ることもできません。ある jail から別の jail へ移るには、必ず対象の jail 名を明示する必要があります。

以下はいずれも拒否されます。

| パス | 理由 |
|------|------|
| `../../etc/passwd` | 封じ込めルートの外に出る |
| `/etc/passwd` | `etc` は登録された jail ではない |
| `/lib/../secret.xml` | jail パスに `..` は使えない |
| `/lib/link.xml`（`link.xml` が jail 外へのシンボリックリンク） | 解決結果が jail の外になる |
| `C:\lib\mod.xml` | バックスラッシュは使えない |

シンボリックリンクは封じ込めの検証の前に展開されるため、jail 内に仕込まれたリンクで外に出ることはできません。

---

## 組み込み

以下の名前はあらかじめ定義されています。`<var name="..."/>` で参照し、`<apply>` か `<expr>` で適用します。どれも `pgsn` パッケージが同じ名前で公開している組み込みの項で、それぞれが取る引数は [README-ja-api.md](README-ja-api.md#組み込みの項) にあります。クラスの短い別名は XML にしかありません。項を組み立てる Python の関数（`string`・`lambda_abs`・`let` など）と読み込みの関数は、XML の要素がその役をするので、XML には対応するものがありません。

| 種類 | 名前 |
|---|---|
| リスト | `cons`・`head`・`tail`・`index`・`is_empty`・`concat`・`map_term`・`fold`・`foldr`・`list_all`・`empty` |
| 真偽値 | `true`・`false`・`if_then_else`・`boolean_and`・`boolean_or`・`boolean_not`・`equal`・`less_than`・`guard` |
| 整数 | `plus`・`minus`・`times`・`div`・`mod`・`integer_sum`・`repeat` |
| レコード | `has_label`・`add_attribute`・`remove_attribute`・`overwrite_record`・`empty_record` |
| 文字列 | `format_string` |
| クラスとオブジェクト | `define_class`・`instantiate`・`type_of`・`is_subtype`・`base_class` |
| その他 | `fix`・`undefined` |
| GSN のコンストラクタ | `goal`・`strategy`・`solution`・`context`・`assumption`・`defeater`・`undeveloped`・`immediate`・`solution_as_goal` |
| GSN のクラス | `goal_class`・`strategy_class`・`solution_class`・`context_class`・`assumption_class`・`defeater_class`・`gsn_class`・`support_class`・`undeveloped_class` |
| GSN のクラスの短い別名 | `Goal`・`Strategy`・`Solution`・`Context`・`Assumption`・`Defeater`・`GSN`・`Support` |

例（リストにテンプレートを写像する）：

```xml
<apply>
    <var name="map_term"/>
    <arg var="someTemplate"/>                 <!-- 第1引数：テンプレート -->
    <arg><ol><li>a</li><li>b</li></ol></arg>  <!-- 第2引数：リスト -->
</apply>
```

---

## 原則

言語のどこでも成り立つ性質が5つあります。ここまでの節は、それを表す構文を説明しています。

**すべてが値です。** Goal も Strategy も Solution も、クラスもテンプレートも、文字列やリストと同じ値です。名前に束縛でき、リストに入れられ、テンプレートに渡せて、テンプレートから返せます。コンテンツを取る要素は、どこでも式を取ります。

**何も書き換わりません。** `<def>` はそれ以降のスコープで名前を束縛するだけで、前の束縛が意味していたものを変えることはありません。同じ名前をもう一度束縛するのは、代入ではなくシャドーイングです。したがってドキュメントは値を1つ持ち、何度評価しても同じ値を持ちます。

**欠けた値は、欠けた場所ではなく、必要になった場所で報告されます。** 定義されていない名前、存在しないレコードのラベル、`typeOf` の検査に通らない値を読んでも、その場ではエラーになりません。それに依存する議論の部分が値を持たないだけです。`pgsn doc` や `pgsn render` が議論を表示したり描いたりするのにその値を必要としたとき、値が欠けている位置へのパスを添えてエラーを報告します。たとえば次のようになります。

    Error: PGSN term cannot be converted to a Python value at path '<root>.support': name 's' is not defined.

引数をすべて与えられていないテンプレートも値ではなく、同じように報告されます。何からも必要とされない部分は評価されないので、そこにある間違いは報告されません。XML の構文の誤りと、拒否された import はこれとは別で、ドキュメントを読んだ時点で報告されます。

**外へ出る道は `import` だけで、それも閉じ込められています。** ドキュメントはファイルを読まず、ネットワークに触れず、時計も見ません。自分の外にあるものへの唯一の接続は `<from>` で、そこに書けるのは、ドキュメントが閉じ込められたディレクトリツリーの中にあるファイルか、PGSN を実行した人が登録した jail の中にあるファイルだけです。[import パスと jail](#import-パスと-jail) を参照してください。閉じ込めが決めるのはドキュメントが何に届くかで、何を消費するかではありません。PGSN はドキュメントが使うメモリと時間を制限しないので、他人が書いたドキュメントは、それらを制限した仮想マシンかコンテナの中で実行してください。

**比べられるのはデータだけです。** 等価比較が比べるのは基本値（文字列・整数・真偽値・`undefined`）と、それらで組まれたリストとレコードです。関数どうし、クラスどうし、GSN ノードどうしを比べても値は出ません。値はアドレスも時刻も持たないので、コピーと元を見分けることはできず、同じ説明で書かれた2つのノードを見分けることもできません。[値の比較](#値の比較)を参照してください。

---

## 要素の一覧

属性の列には、その要素自身の属性を挙げます。コンテンツを取る要素は、ほかに[略記の属性](#略記の属性) `var`・`expr`・`as` も取ります。

| 要素 | コンテンツ | 属性 | 節 |
|---|---|---|---|
| `<PGSN>` | `<from>` と `<def>`、その後に値1つ | – | [ドキュメントとモジュール](#ドキュメントとモジュール) |
| `<PGSNModule>` | `<param>`、その後に `<from>` と `<def>` | – | [ドキュメントとモジュール](#ドキュメントとモジュール) |
| `<from>` | `<import>` と `<arg>`、または無し | `file`・`import`・`as` | [import（from）](#importfrom) |
| `<import>` | 空 | `name`・`as` | [import（from）](#importfrom) |
| `<def>` | 値1つ | `name`・`typeOf`・`recursive` | [定義（def）](#定義def) |
| `<var>` | 空 | `name`・`typeOf` | [変数（var）](#変数var) |
| `<div>` | `<def>`、その後に値1つ | – | [局所定義](#局所定義) |
| `<num>` | 10進の整数 | – | [リテラル](#リテラル) |
| `<str>` | 書いたままのテキスト | – | [リテラル](#リテラル) |
| `<expr>` | 式 | – | [式（expr）](#式expr) |
| `<ol>` | `<li>` | – | [リスト（ol）](#リストol) |
| `<li>` | 値1つ | – | [リスト（ol）](#リストol) |
| `<dl>` | `<dt>` と `<dd>` の対 | – | [レコード（dl）](#レコードdl) |
| `<dt>` | テキストのラベル、または空 | `key` | [レコード（dl）](#レコードdl) |
| `<dd>` | 値1つ | – | [レコード（dl）](#レコードdl) |
| `<if>` | `<cond>`・`<then>`・`<else>` | – | [条件分岐](#条件分岐ifcases) |
| `<cases>` | `<case>`、その後に `<else>` | – | [条件分岐](#条件分岐ifcases) |
| `<case>` | `<cond>`・`<then>` | – | [条件分岐](#条件分岐ifcases) |
| `<cond>`・`<then>`・`<else>` | 値1つ | – | [条件分岐](#条件分岐ifcases) |
| `<template>` | `<param>`・`<def>`、その後に値1つ | – | [テンプレート定義](#テンプレート定義template) |
| `<param>` | デフォルト値、または空 | `name`・`positional` | [パラメーター](#パラメーターparam) |
| `<apply>` | 関数（または `template=`）、その後に `<arg>` | `template` | [テンプレート適用](#テンプレート適用apply) |
| `<arg>` | 値1つ、または空 | `name` | [テンプレート適用](#テンプレート適用apply) |
| `<class>` | `<inherit>`・`<attribute>`・`<method>` | `name` | [クラス定義](#クラス定義class) |
| `<inherit>` | クラス | – | [クラス定義](#クラス定義class) |
| `<attribute>` | デフォルト値か属性の値、または空 | `name` | [クラス定義](#クラス定義class)、[オブジェクト](#オブジェクトobject) |
| `<method>` | `<param>`、その後に値1つ | `name` | [クラス定義](#クラス定義class) |
| `<object>` | `<instanceOf>`、その後に `<attribute>` | – | [オブジェクト](#オブジェクトobject) |
| `<instanceOf>` | クラス | – | [オブジェクト](#オブジェクトobject) |
| `<get>` | レシーバー（または `of=`） | `key`・`of` | [ラベルの読み出し](#ラベルの読み出しget) |
| `<send>` | レシーバー（または `to=`）、その後に `<arg>` | `method`・`to` | [メソッド呼び出し](#メソッド呼び出しsend) |
| `<Goal>` | 説明・`<Context>`・`<Assumption>`・`<Defeater>`・支持1つ | – | [Goal](#goal) |
| `<Strategy>` | 説明・`<Context>`・`<Assumption>`・`<Defeater>`・サブゴール | – | [Strategy](#strategy) |
| `<Solution>` | 説明・`<Defeater>` | – | [Solution](#solution) |
| `<Defeater>` | 説明・`<Defeater>`・省略できる支持 | – | [Defeater](#defeater) |
| `<Context>`・`<Assumption>` | 値1つ | – | [Context と Assumption](#context-と-assumption) |
| `<description>` | 値1つ | – | [説明](#説明) |
| `<supportedBy>` | 支持 | – | [Goal](#goal) |
| `<subGoals>` | ゴールのリスト | – | [Strategy](#strategy) |
| `<undeveloped/>` | 空 | – | [Goal](#goal)、[Strategy](#strategy) |
