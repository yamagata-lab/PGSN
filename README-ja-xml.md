# PGSN — Programmable Goal Structuring Notation

PGSN は XML ベースの言語で、GSN（Goal Structuring Notation）をプログラマブルに拡張したものです。
GSN ノード（Goal・Strategy・Evidence）を値として扱い、変数・テンプレート・クラスといったプログラミング構造と組み合わせることができます。

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

`import` と `def` は両形式とも混在して書くことができます。

---

## 値（val）

PGSN における「値」はあらゆる式（expression）または変数参照です。

### 変数参照の略記

要素のコンテンツが変数参照のみの場合、`var` 属性で略記できます。
これは前処理により展開されます。

```xml
<!-- 完全形 -->
<tag><var name="x"/></tag>

<!-- 略記 -->
<tag var="x"/>
```

---

## パラメーター（param）

`param` は `<PGSNModule>` が外部から受け取る変数を宣言します。
`<param>` は `<PGSNModule>` 内のみ有効で、`<from>` や `<def>` より前に書きます。

```xml
<param name="A1" instanceOf="Assumption"/>

<!-- デフォルト値付き -->
<param name="threshold">100</param>
```

---

## import（from）

外部の PGSN ファイルから名前を持ち込みます。セキュリティ上の理由から、ファイルパスは相対パスのみ使用できます。

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

---

## 定義（def）

`def` は名前に値を束縛します。純粋関数型なので再代入はありません。

```xml
<def name="x">expr</def>
```

### `as` 属性（略記）

`def` に `as` 属性を指定すると、値を包む外側のタグ名を省略できます。
これも前処理により展開されます。

```xml
<!-- 完全形 -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- 略記 -->
<def name="myGoal" as="Goal">...</def>
```

`as` に指定できるのは**組み込みタグ名**（`Goal`・`Strategy`・`Evidence`・`template`・`class`・`object`・`div`・`apply`・`ul`・`ol`・`dl`）だけです。
ユーザー定義のクラス名（例: `GoalWithURL`）は `as` には指定できません
（後述「クラスによる GSN の拡張」を参照）。

> **設計上の不変条件**
> `<def name="x" as="T">C</def>` が妥当であることと、脱糖形 `<def name="x"><T>C</T></def>` が妥当であることは等価です。
> このため `var`・`get`・`send` のように要素自身が必須属性（`name`）を持つタグは `as` には使えません。脱糖した `<send>C</send>` が必須属性を欠き不正になるためです。

### `instanceOf` 属性

変数の型を明示したい場合に使います。

```xml
<def name="x" instanceOf="MyClass">...</def>
```

### 局所定義（div）

スコープを限定した定義には `div` を使います。

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- div の値 -->
</div>
```

`<template>` のボディにも、最終的な値要素の前に `<def>` を直接並べることができます。`<div>` で包む必要がありません。

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

<!-- 型を明示する場合 -->
<var name="x" instanceOf="MyClass"/>
```

### 組み込み（builtin）

以下の名前はあらかじめ定義済みで、`<var name="..."/>` で参照し `apply` に適用できます。

- リスト操作: `cons`・`head`・`tail`・`index`・`concat`・`map_term`・`fold`
- 真偽値: `true`・`false`・`if_then_else`・`boolean_and`・`boolean_or`・`boolean_not`・`equal`・`guard`
- 整数: `plus`・`minus`・`times`・`div`・`mod`
- レコード: `has_label`・`list_labels`・`add_attribute`・`remove_attribute`・`overwrite_record`
- 文字列: `format_string`
- クラス／オブジェクト: `define_class`・`instantiate`・`is_instance`・`is_subclass`・`base_class`
- その他: `fix`・`undefined`
- GSN: `goal`・`strategy`・`evidence`・`context`・`assumption`・`undeveloped`・`immediate`・`evidence_as_goal`、および各クラス（`goal_class` ほか）

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

---

## クラスとオブジェクト

### クラス定義（class）

```xml
<class>
    <inherit>ParentClass</inherit>   <!-- 継承（省略可） -->
    <attribute name="attr1">default_value</attribute>
    <attribute name="attr2"/>        <!-- デフォルト値なし -->
    <method name="m">
        <param name="p1">default</param>
        <param name="p2"/>
        body_expr
    </method>
</class>
```

### オブジェクト生成（object）

```xml
<object>
    <instanceOf>MyClass</instanceOf>
    <attribute name="attr1">value</attribute>
</object>
```

### キーアクセス（get）

`get` は `Record` と `PGSNObject` の両方に使えます。内部では `expr` を文字列キー `name` に位置適用するだけなので、`<apply>` に文字列 `<arg>` を渡す書き方と完全に等価です。

```xml
<!-- PGSNObject の属性アクセス -->
<get name="description"><var name="myGoal"/></get>

<!-- Record のキーアクセス（以下2つは等価） -->
<get name="x"><var name="myRecord"/></get>
<apply><var name="myRecord"/><arg>x</arg></apply>
```

### メソッド呼び出し（send）

```xml
<send name="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

---

## データ型

### 集合（ul）・リスト（ol）

```xml
<ul>
    <li>expr1</li>
    <li var="x"/>    <!-- 略記 -->
</ul>

<ol>
    <li>expr1</li>
    <li>expr2</li>
</ol>
```

`ul` と `ol` は XML 構文上は同型ですが、順序を保ちたい場合（例: `map_term` に渡すリスト）は `ol` を使います。

### 辞書（dl）

キーには値を直接置くか、`key` 属性で文字列キーを指定します。

```xml
<dl>
    <dt>key_expr</dt><dd>value_expr</dd>   <!-- 式をキーにする場合 -->
    <dt key="name"/><dd>value_expr</dd>    <!-- 文字列キーの場合 -->
</dl>
```

### テキスト内のフォーマット文字列

テキストを置ける場所では、`{name}` という記法でスコープ内の変数を埋め込めます。
前処理により `format_string` の適用へ展開されます。波括弧自体を書きたい場合は `{{` `}}` でエスケープします。

```xml
<template>
    <param name="c" positional="true"/>
    <Evidence>Component {c} のテスト結果</Evidence>
</template>
```

### GSN の地テキストとして description を記述する

GSN ヘッダー要素（`Goal`・`Strategy`・`Evidence`・`Context`・`Assumption`）では、先頭の地テキストが自動的に `description` として扱われます。子要素（`<Strategy>` など）と共存する場合、前処理により `<description>` 要素へ持ち上げられます。`{name}` 展開もここで使えます。

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

---

## GSN ノード

GSN ノードは通常の値と同列に扱われます。クラスとして継承・拡張が可能です。

### 共通ヘッダ（gsn_header）

Goal・Strategy・Evidence はすべて共通のヘッダ構造を持ちます。

```xml
<!-- 説明（description要素 または テキスト直書き） -->
<description>説明文</description>

<!-- Context: 議論が成立する文脈。値として任意の式を置ける -->
<Context>テキストによる説明</Context>
<Context var="someObject"/>          <!-- 変数参照 -->
<Context><get name="version">expr</get></Context>  <!-- 式 -->

<!-- Assumption: 議論が置く仮定。Context と同様、値として任意の式を置ける -->
<Assumption>ゼロデイ攻撃はない</Assumption>
<Assumption var="someObject"/>       <!-- 変数参照 -->
```

**Context と Assumption の使い分け**

`Context` と `Assumption` はどちらもヘッダに付随するドキュメンテーション要素で、値として任意の式（テキスト・変数参照・オブジェクト・リスト等）を1つ置けます。

- `Context` は議論が成立する文脈・前提となる状況や対象を表します。
- `Assumption` は議論が置く仮定を表します。

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
> Goal の直下に `<Goal>` を複数並べる書き方は、前処理により `immediate`（サブゴールを束ねる特殊な Strategy）でラップされます。
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

`subGoals` に集合（`ul`）やリスト（`ol`）を渡すことでサブゴールを動的に指定できます。

```xml
<Strategy>
    argument
    <subGoals>
        <ul>
            <li var="goal1"/>
            <li var="goal2"/>
        </ul>
    </subGoals>
</Strategy>
```

### Evidence

```xml
<Evidence>
    <description>テスト結果レポート</description>
    <Context>テスト環境の説明</Context>
</Evidence>
```

---

## クラスによる GSN の拡張

GSN ノードはクラスとして継承・拡張できます。
拡張したクラスは `<object>` でインスタンス化します（属性を明示します）。

```xml
<!-- Goal を継承し、属性 URL を追加したクラス -->
<def name="GoalWithURL" as="class">
    <inherit>Goal</inherit>
    <attribute name="URL"/>
</def>

<!-- インスタンス化（object 形） -->
<object>
    <instanceOf>GoalWithURL</instanceOf>
    <attribute name="description">システムXはセキュア</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```

> ユーザー定義のクラス名を `as` 属性に書く略記（例: `<def name="myGoal" as="GoalWithURL">...`）はサポートしません。
> `as` は組み込みタグ名に限られるため、拡張クラスのインスタンス化には上記の `<object>` 形を使ってください。

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
        テスト・レビューを行う
        <subGoals>
            <ul>
                <li var="G1"/>
            </ul>
        </subGoals>
    </def>

    <def name="main" as="Goal">
        <description>システムはセキュア</description>
        <Assumption>ゼロデイ攻撃はない</Assumption>
        <supportedBy var="mainStrategy"/>
    </def>
</PGSNModule>
```

`param` を受け取るモジュールは、末尾に単一の値を置く `<PGSN>` ではなく `<PGSNModule>` を使います
（`param` は `<PGSNModule>` の先頭にだけ書けます）。