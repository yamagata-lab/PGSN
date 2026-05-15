# PGSN — Programmable Goal Structuring Notation

PGSN は XML ベースの言語で、GSN（Goal Structuring Notation）をプログラマブルに拡張したものです。
GSN ノード（Goal・Strategy・Evidence）を値として扱い、変数・テンプレート・クラスといったプログラミング構造と組み合わせることができます。

---

## 基本構造

PGSN ドキュメントのルート要素は `<PGSN>` で、以下の順序で構成されます。

```xml
<PGSN>
    <param name="p"/>          <!-- パラメーター（0個以上） -->
    <from file="..."/>         <!-- import（0個以上） -->
    <def name="x">...</def>    <!-- 定義（0個以上） -->
    ...                        <!-- 値（1つ） -->
</PGSN>
```

`import` と `def` は混在して書くこともできます。

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

`param` はこの PGSN モジュールが外部から受け取る変数を宣言します。
必ず `<PGSN>` の先頭に書きます。

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

`def` に `as` 属性を指定すると、値の型（タグ名）を省略できます。
これも前処理により展開されます。

```xml
<!-- 完全形 -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- 略記 -->
<def name="myGoal" as="Goal">...</def>
```

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

---

## 変数（var）

定義済みの名前を参照します。

```xml
<var name="x"/>

<!-- 型を明示する場合 -->
<var name="x" instanceOf="MyClass"/>
```

---

## テンプレートと適用

### テンプレート定義（template）

関数を値として定義します（λ式相当）。

```xml
<!-- 引数なし -->
<template>expr</template>

<!-- 引数あり。デフォルト値も指定可能 -->
<template>
    <param name="arg1">default_expr</param>
    <param name="arg2"/>
    body_expr
</template>
```

### テンプレート適用（apply）

テンプレートを引数に適用します。

```xml
<apply>
    expr               <!-- 適用するテンプレート -->
    <arg name="arg1">expr1</arg>
    <arg name="arg2">expr2</arg>
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

### 属性アクセス（get）

```xml
<get name="attr">expr</get>
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

### 辞書（dl）

キーには値を直接置くか、`key` 属性で文字列キーを指定します。

```xml
<dl>
    <dt>key_expr</dt><dd>value_expr</dd>   <!-- 式をキーにする場合 -->
    <dt key="name"/><dd>value_expr</dd>    <!-- 文字列キーの場合 -->
</dl>
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

<!-- Assumption: 名前付きの仮定。変数参照が必須 -->
<Assumption>説明テキスト<var name="A1"/></Assumption>
<Assumption var="A1"/>               <!-- 略記 -->
```

**Context と Assumption の使い分け**

- `Context` は議論の前提となる状況や対象を指します。任意の式（変数・オブジェクト・リスト等）を直接値として置けるため、外部データへの参照も表現できます。
- `Assumption` は自由変数を導入します。その変数は、ドキュメントのどこかで `def`か`param`を通じて束縛されなければなりません。束縛するゴールが `undeveloped` であっても構いません。これは「仮定の存在は認めるが、その正当化は後回しにする」という意思表示です。これは意図的な設計上の選択であり、すべての仮定は議論構造の中に明示的な受け手を持たなければなりません。

### Goal

```xml
<Goal>
    <description>システムXはセキュアである</description>
    <Context>規格XXXXによる認証</Context>
    <Assumption>ゼロデイ攻撃はない<var name="A1"/></Assumption>

    <!-- body は以下のいずれか -->
    <Strategy>...</Strategy>              <!-- Strategy で支持 -->
    <Evidence>...</Evidence>              <!-- Evidence で支持 -->
    <Goal>...</Goal>                      <!-- サブゴールで支持（1つ以上） -->
    <supportedBy var="strategy1"/>        <!-- 変数参照で支持 -->
    <undeveloped/>                        <!-- 未展開 -->
</Goal>
```

### Strategy

```xml
<Strategy>
    argument
    <!-- body は以下のいずれか -->
    <Goal>...</Goal>           <!-- サブゴール（1つ以上） -->
    <subGoals var="goals"/>    <!-- 変数参照でまとめて指定 -->
</Strategy>
```

`subGoals` に集合（`ul`）を渡すことでサブゴールを動的に指定できます。

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

```xml
<def name="GoalWithURL">
    <class>
        <inherit>Goal</inherit>
        <attribute name="URL"/>
    </class>
</def>

<def name="myGoal" as="GoalWithURL">
    システムXはセキュア
    <attribute name="URL">https://example.com/evidence</attribute>
    <undeveloped/>
</def>
```

---

## モジュールの例

パラメーターと import を組み合わせた実例です。

```xml
<PGSN>
    <!-- 外部から仮定を受け取る -->
    <param name="A1" instanceOf="Assumption"/>

    <!-- 別ファイルからゴールを持ち込む -->
    <from file="security.pgsn" import="secureGoal" as="G1"/>

    <!-- Assumption を supportedBy で束縛する -->
    <def name="mainStrategy" as="Strategy">
        テスト・レビューを行う
        <subGoals>
            <ul>
                <li var="G1"/>
            </ul>
        </subGoals>
    </def>

    <Goal>
        <description>システムはセキュア</description>
        <Assumption>ゼロデイ攻撃はない<var name="A1"/></Assumption>
        <Strategy var="mainStrategy"/>
    </Goal>
</PGSN>
```