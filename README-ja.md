# PGSN: Programmable Goal Structuring Notation

アシュアランスケース生成のための関数型プログラミング環境

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## PGSNとは？

**PGSN** は、**Goal Structuring Notation (GSN)** に基づいて構造化されたアシュアランスケースを構築・変換するための、関数型プログラミング言語および実行環境です。従来のGSNが静的な図表を中心とするのに対し、PGSNは関数型およびオブジェクト指向の構文を用いて、GSN要素を動的かつ構造的に生成できます。

**PGSN** は2つの形で書けます。Python に埋め込まれた DSL と、`pgsn` コマンドで評価する XML 構文です。
どちらか一方だけでアシュアランスケースを書き切れます。Python API の仕様は
[README-ja-api.md](README-ja-api.md)、XML 構文の仕様は [README-ja-xml.md](README-ja-xml.md) にあります。

---

## 特長

- **関数型プログラミングによるGSN記述**：アシュアランスケースを関数として記述
- **構成的・再利用可能**：GSN構造を柔軟に組み立て可能
- **オブジェクト指向サポート**：クラス／継承によるノード定義の拡張
- **閉じた評価**：XML ドキュメントが外に手を伸ばす方法はありません（言語にファイル・ネットワーク・システムへのアクセスがない）。import できるファイルも、自身のディレクトリか、与えられたディレクトリルートの下だけです。評価はステップ数で上限が決まります。`.py` の入力は別で、これは Python のプログラムなので、`pgsn` はあなたの権限でそのまま実行します。信頼できる `.py` ファイルだけを渡してください

---

## インストール

利用者向け
```shell
pip install git+https://github.com/yamagata-lab/pgsn.git
```

ライブラリの開発も行う場合
```bash
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
pip install -e '.[dev]'
```

`pgsn render` と `gsn_dot` には Graphviz のプログラム（`dot`）が要りますが、pip では入りません。システムのパッケージマネージャーで入れるか、それを含む下の conda 環境を使ってください。

condaを使ってライブラリの開発を行う場合
```bash
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
conda env create -f environment.yml -n PGSN
conda activate PGSN
pip install -e '.[dev]'
```


---
## コマンドライン

XML ドキュメントの例 `examples/gsn.xml`：

```xml
<PGSN>
    <Goal>
        System is secure
        <Strategy>
            Break into sub-goals
            <Goal>Input validated<Solution>Static analysis passed</Solution></Goal>
            <Goal>Output sanitized<Solution>Fuzzing test succeeded</Solution></Goal>
        </Strategy>
    </Goal>
</PGSN>
```

`pgsn doc` はこれを評価し、構造を木として表示します。

```shell
% pgsn doc examples/gsn.xml
Generating 'None' from 'examples/gsn.xml'
Evaluating term 'main'...
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded

Done.
```

`.py` の入力は、表示する項を `main`（`--term-name` で別の名前にできます）に束縛する Python のプログラムです。[基本例](#基本例)を参照してください。`pgsn render` は同じ構造を SVG・PNG・PDF の図に描き、他のコマンドとオプションは `pgsn --help` で一覧できます。コマンドが失敗すると `Error:` を表示して終了コード 1 で終わります。入力ファイルが無い、`--jail` の書き方が誤っている、といった使い方の誤りは終了コード 2 で終わります。

### GSN の規則の検査

`pgsn doc` と `pgsn render` は、評価した構造を GSN v3 の規則のうち文書が破りうるものに照らし、違反を要素の識別子とパスを添えて警告として報告します。

```shell
Warning: S1 at <root>.support: a strategy relates a goal to supporting goals, but this one has none
```

規則は次のとおりです。Goal を支持するのは Strategy・Solution・サブゴールのどれかで、Strategy を支持するのは Goal であること。contexts と assumptions の中身がそれぞれ Context と Assumption であること。Strategy がサブゴールを1つ以上持つこと。異議を立てる要素が Defeater であること。どの要素も description が空でない文字列であること。構造の一番上が Goal であること。`--strict` を付けると違反はエラーになり、何も書き出さずに終了コード 1 で終わります。

### XML import のための jail

XML ドキュメントは他のドキュメントを import できますが、既定では自身のディレクトリ配下のファイルにしか届きません。共有モジュール群へのアクセスを許可するには、それを *jail*（名前の付いたディレクトリルート）として登録し、ドキュメント側からは `/<名前>/...` で参照します。

```shell
PGSN % pgsn doc main.xml --jail lib=/opt/pgsn-lib
```

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

`--jail` は複数回指定でき、`.xml` 入力にのみ適用されます。ドキュメント自身のディレクトリと登録された jail の外にあるものは import できません。`..` で封じ込めルートの外に出ることはできず、シンボリックリンクは検証前に展開されます。詳細は [README-ja-xml.md](README-ja-xml.md) を参照してください。

---

## 公開 API

`import pgsn` がサポート対象のインターフェースです。

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
print(pgsn.gsn_tree(term).show(stdout=False, sorting=False))
```

公開しているのは、PGSN 定数および項を構築する関数（`string`、`record`、`lambda_abs`、`map_term` など）、GSN ノードとクラスを構築する関数（`goal`、`strategy`、`solution`、`goal_class` など）、変換・描画の関数（`python_value`、`gsn_tree`、`gsn_dot`、`save_gsn`）、そして XML フロントエンドとその設定（`load_xml`、`load_xml_string`、`Config`、`Jails`、`configure`）です。

これら以外 — `pgsn.dsl`、`pgsn.gsn`、`pgsn.pgsn_term`、`pgsn.pgsn_xml`、`pgsn.helpers`、`pgsn.cli` — は内部実装であり、予告なく変更されることがあります。

詳細なリファレンスは [README-ja-api.md](README-ja-api.md) にあります。

---

## 基本例

```python
from pgsn import *

g = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=solution(description="Static analysis passed")),
            goal(description="Output sanitized",
                 support=solution(description="Fuzzing test succeeded"))
        ]
    )
)

gsn_tree(g.fully_eval()).show(sorting=False)
```

これは[コマンドライン](#コマンドライン)の例を Python で書いたものです。`examples/gsn.py` はこれを `main` に束縛しているので、`pgsn doc examples/gsn.py` も同じ木を表示します。

---

## 応用例

### 例1：テンプレートによる再利用

同じ説明文を持つ goal + solution の構造を生成する再利用可能な関数を定義します。

```python
from pgsn import *

# 再利用できる goal + solution のテンプレートを定義
mk_goal_with_evidence = lambda_abs_keywords(
    {"desc": variable("desc")},
    goal(
        description=variable("desc"),
        support=solution(description=variable("desc"))
    )
)

# テンプレートを複数のゴールに適用
g1 = mk_goal_with_evidence(desc="No hardcoded passwords")
g2 = mk_goal_with_evidence(desc="Input sanitized")
g3 = mk_goal_with_evidence(desc="Logging enabled")

# Strategy でトップレベルのゴールを組み立てる
top = goal(
    description="System is secure",
    support=strategy(
        description="Apply security principles",
        sub_goals=[g1, g2, g3]
    )
)

gsn_tree(top.fully_eval()).show(sorting=False)
```

---

### 例2：`map_term` を用いた一括生成

複数の要件から自動的に goal + solution の構造を生成します。

```python
from pgsn import *

requirements = ["Firewall enabled", "Encrypted communication", "Access control active"]


goal_template = lambda_abs(variable("desc"),
    goal(description=variable("desc"),
         support=solution(description=variable("desc")))
)

goals = map_term(goal_template, requirements)

secure_goal = goal(
    description="Security requirements fulfilled",
    support=immediate(goals)
)

gsn_tree(secure_goal.fully_eval()).show(sorting=False)
```

---

### 例3：オブジェクト指向によるノード拡張

Goal を継承した独自のクラスを定義し、メタデータを加えてインスタンス化します。

```python
from pgsn import *

# Goal の派生クラスを定義
CustomGoal = define_class(inherit=goal_class, name="GoalWithProject", attributes=["project"])

g = instantiate(CustomGoal, description="Secure connection established",
                project='Alpha',
                support=solution(description="Verified by audit"))

gsn_tree(g.fully_eval()).show(sorting=False)
```
---

## 技法と応用のまとめ

| 目的              | 使用技法                              |
|-------------------|-----------------------------------------|
| テンプレートの再利用 | ラムダ抽象とキーワード引数の定義              |
| 構造の一括生成       | `map_term` を用いたリスト展開                  |
| メタデータの付加     | クラス定義と `instantiate` による構成           |

これらの技法を組み合わせれば、分野ごとの GSN テンプレートを作ったり、アシュアランスケースの生成を自動化したり、構造上の制約をプログラムで検査したりできます。

---

## よく使う関数一覧

| 関数                         | 説明                                           |
|----------------------------|------------------------------------------------|
| `goal(...)`                | GSNのゴール（主張）を定義                     |
| `strategy(...)`            | ゴールを裏付ける推論戦略を記述                |
| `solution(...)`            | ゴールを支える証拠への参照を記述              |
| `context(...)`             | ゴールや戦略に対する文脈情報を追加            |
| `assumption(...)`          | 仮定を明示                                    |
| `defeater(...)`            | それを持つノードに異議を立てる                |
| `undeveloped`              | ゴールがまだ支持されていないことを示す        |
| `immediate(...)`           | サブゴールを直接接続                          |
| `map_term(...)`            | リストに対して関数適用を行い複数ノード生成    |
| `lambda_abs(...)`          | 引数付きのラムダ抽象（位置引数）              |
| `lambda_abs_keywords(...)` | 引数付きのラムダ抽象（キーワード引数）        |
| `define_class(...)`        | クラスを定義（`inherit=` で親を指定）         |
| `instantiate(...)`         | クラスをインスタンス化                        |

---

## アーキテクチャ

| レイヤー           | コンポーネント          | 概要                                       |
|--------------------|------------------------|--------------------------------------------|
| コア               | `pgsn_term.py`         | ラムダ計算に基づくインタープリター             |
| Python DSL         | `dsl.py`・`gsn.py`     | プログラムから GSN ノードを組み立てる      |
| XML フロントエンド | `pgsn_xml.py`          | XML 構文をコアへコンパイル                 |
| サンドボックス     | `jail.py`・`config.py` | import が届く範囲を封じ込める              |
| CLI                | `cli.py`               | `pgsn doc`・`pgsn render`・`pgsn compile`  |

---

## ライセンス

MITライセンス – 詳細は [LICENSE](LICENSE) をご覧ください。

© 国立研究開発法人産業技術総合研究所 (AIST) 2023–2024  
山形頼之 2025-
