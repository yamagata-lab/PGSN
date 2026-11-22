# PGSN: Programmable Goal Structuring Notation

アシュアランスケース生成のための関数型プログラミング環境

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## PGSN とは

PGSN では、GSN（Goal Structuring Notation）のアシュアランスケースをプログラムとして書きます。Goal を1つずつ手で描く代わりに、パターン（Goal のテンプレートや、属性を足した Goal のクラス）を一度定義し、そこから議論を生成します。たとえば要件のリストから、要件ごとにサブゴールを1つずつ作れます。

PGSN は2つの形で書けます。どちらか一方だけでアシュアランスケースを書き切れます。

- **XML**。`pgsn` コマンドで評価します。XML ドキュメントは閉じ込められていて、import するモジュール以外のファイルは開けず、ネットワークやシステムにもアクセスできません。ただし PGSN はドキュメントが使うメモリと時間を制限しないので、他人が書いたドキュメントは、それらを制限した仮想マシンかコンテナの中で実行してください。仕様は [README-ja-xml.md](README-ja-xml.md) にあります。
- **Python**。Python に埋め込んだライブラリとして使います。Python の力をすべて使えるので、信頼できるコードに使ってください。仕様は [README-ja-api.md](README-ja-api.md) にあります。

この文書の英語版は [README.md](README.md) です。

## 特長

- **アシュアランスケースを関数型のプログラムとして記述**：Goal・Strategy・Solution は値で、名前を付けたり、テンプレートに渡したり、リストから生成したりできます。
- **再利用できる**：アシュアランスの構造を部品から組み立て、部品を別のファイルから import できます。
- **オブジェクト指向**：GSN のクラスを継承して、新しいノードの種類を定義できます。
- **GSN v3 に沿った出力**：`pgsn render` は評価結果を GSN Community Standard 第3版に沿って、弁証法的拡張（Defeater）も含めて描きます。`pgsn doc` と `pgsn render` は、評価結果を規格の構造の規則に照らして検査します。
- **閉じた XML**：XML ドキュメントからは、import するモジュール以外のファイルは開けず、ネットワークやシステムにもアクセスできません。import できるのは、自身のディレクトリか、許可したディレクトリ（jail）の中だけです。評価のステップ数には上限があり、止まらないドキュメントを止めます。1ステップの重さには限りがないので、メモリと時間は制限しません。
- **信頼できるコードには Python**：`.py` の入力は普通の Python のプログラムで、実行した人の権限で動きます。信頼できる `.py` ファイルだけを実行してください。

## インストール

**利用者：**

```shell
pip install git+https://github.com/yamagata-lab/PGSN.git
```

**開発者**（編集可能なインストール）：

```shell
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
pip install -e '.[dev]'
```

**開発者、conda を使う場合**（Graphviz も入ります）：

```shell
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
conda env create -f environment.yml -n PGSN
conda activate PGSN
pip install -e '.[dev]'
```

図を描くには Graphviz のプログラム（`dot`）が要ります。要るのは `pgsn render`、`save_gsn`、`gsn_dot` が返すグラフを画像にするときです。pip では入らないので、システムのパッケージマネージャーで入れるか、上の conda 環境を使ってください。

## クイックスタート

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

`pgsn doc` はドキュメントを評価し、得られた議論をテキストの木として `-o` で指定したファイルに書き出します（`-o -` なら画面に表示します）。

```console
$ pgsn doc examples/gsn.xml -o -
Evaluating term 'main'...
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded

Done.
```

`pgsn render` は同じ議論を図に描きます。

```console
$ pgsn render examples/gsn.xml -o gsn -f png     # gsn.png を書き出す
```

どちらも評価結果を GSN v3 の規則に照らし、規則を破る要素ごとに警告を表示します。`--strict` を付けると違反はエラーになります。規則の一覧は [GSN v3 に照らした検査](README-ja-xml.md#gsn-v3-に照らした検査)にあります。

## 同じケースを Python で

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

これは `examples/gsn.xml` と同じアシュアランスケースを作ります。`pgsn` コマンドは `.py` の入力も受け付けます。そのプログラムを実行し、変数 `main` の値を表示します（別の変数は `--term-name` で指定します）。`examples/gsn.py` は上のケースを `main` に入れているので、`pgsn doc examples/gsn.py -o -` も同じ木を表示します。`.py` の入力は実行した人の権限で動く普通の Python のプログラムなので、信頼できるファイルだけを実行してください。

## もう一歩進んで

たいていの用途は、次の3つの技法で足ります。

| 目的 | 技法 | 例 |
|---|---|---|
| パターンの再利用 | パラメーターを持つテンプレート | `examples/secure_with_template.xml` |
| リストから構造を生成 | テンプレートをリストの各項目に適用する `map_term` | `examples/map_term.xml` |
| ノードに追加のデータを付ける | GSN のクラスを継承したクラス | `examples/custom_goal.xml` |

どの例にも、隣に Python 版があります（`examples/secure_with_template.py`・`examples/map_term.py`・`examples/custom_goal.py`）。

### 再利用できる Goal のテンプレート

同じ説明の Solution に支持された Goal を作るテンプレートを、3回適用します。

```xml
<PGSN>
    <def name="mkGoalWithEvidence" as="template">
        <param name="desc"/>
        <Goal>{desc}<Solution>{desc}</Solution></Goal>
    </def>

    <def name="g1" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">No hardcoded passwords</arg></def>
    <def name="g2" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">Input sanitized</arg></def>
    <def name="g3" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">Logging enabled</arg></def>

    <Goal>
        System is secure
        <Strategy>
            Apply security principles
            <subGoals><ol><li var="g1"/><li var="g2"/><li var="g3"/></ol></subGoals>
        </Strategy>
    </Goal>
</PGSN>
```

### 要件ごとに Goal を1つ

`map_term` は、リストの要件ごとにテンプレートを適用します。

```xml
<PGSN>
    <def name="goalTemplate" as="template">
        <param name="desc" positional="true"/>
        <Goal>{desc}<Solution>{desc}</Solution></Goal>
    </def>

    <def name="goals" as="apply">
        <var name="map_term"/>
        <arg var="goalTemplate"/>
        <arg><ol>
            <li>Firewall enabled</li>
            <li>Encrypted communication</li>
            <li>Access control active</li>
        </ol></arg>
    </def>

    <Goal>
        Security requirements fulfilled
        <supportedBy><apply><var name="immediate"/><arg var="goals"/></apply></supportedBy>
    </Goal>
</PGSN>
```

`immediate` は、並べたサブゴールをそのまま持つだけの Strategy を作ります。出力にどう現れるかは [known_issues-ja.md](known_issues-ja.md) に挙げてあります。

### 追加のデータを持つ Goal のクラス

`Goal` を継承し、属性 `project` を加えたクラスです。

```xml
<PGSN>
    <def name="GoalWithProject">
        <class name="GoalWithProject">
            <inherit var="Goal"/>
            <attribute name="project"/>
        </class>
    </def>

    <object>
        <instanceOf var="GoalWithProject"/>
        <attribute name="description">Secure connection established</attribute>
        <attribute name="project">Alpha</attribute>
        <attribute name="support"><Solution>Verified by audit</Solution></attribute>
    </object>
</PGSN>
```

## コマンドライン

| コマンド | すること |
|---|---|
| `pgsn doc FILE -o OUT` | ドキュメントを評価し、テキストの木として書き出す（`-d json` で JSON）。`-o -` は標準出力 |
| `pgsn render FILE -o NAME -f svg\|png\|pdf` | ドキュメントを評価して図に描く。`NAME` には拡張子を付けない。`--label-width N` でラベルを `N` 桁で折り返す |
| `pgsn compile FILE -o OUT` | ドキュメントを JSON にコンパイルする |

`pgsn --help` と `pgsn COMMAND --help` で、すべてのオプションを一覧できます。`doc` と `render` に共通のオプションは次のとおりです。

- `-s`・`--steps N` は評価のステップ数の上限を決めます。
- `--strict` は GSN v3 の規則への違反をエラーにします。コマンドは何も書き出さず、終了コード 1 で終わります。
- `--jail NAME=DIR` は共有モジュールのディレクトリへのアクセスを許可します（下を参照）。

コマンドが失敗すると `Error:` を表示して終了コード 1 で終わります。入力ファイルが無い、`pgsn doc` に `-o` が無い、`--jail` の書き方が誤っている、といった使い方の誤りは終了コード 2 で終わります。

### XML import のための jail

XML ドキュメントは他のドキュメントを import できますが、既定では自身のディレクトリ配下のファイルにしか届きません。共有モジュール群へのアクセスを許可するには、それを *jail*（名前の付いたディレクトリルート）として登録し、ドキュメント側からは `/<名前>/...` で参照します。

```console
$ pgsn doc main.xml -o - --jail lib=/opt/pgsn-lib
```

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

`/opt/pgsn-lib` と `main.xml` は、自分のディレクトリとドキュメントに読み替えてください。`--jail` は複数回指定でき、`.xml` の入力にだけ適用されます。ドキュメント自身のディレクトリと登録された jail の外にあるものは import できません。`..` でドキュメント自身のディレクトリ（jail の中ならその jail）より上には出られず、シンボリックリンクはその検証の前に展開されます。規則の全体は [README-ja-xml.md](README-ja-xml.md#import-パスと-jail) にあります。

## Python から使う

サポート対象のインターフェースは `import pgsn` です。`pgsn.__all__` にあるものはすべて公開で、それ以外（`pgsn.dsl`・`pgsn.gsn` などのサブモジュールすべてを含む）は内部実装で、予告なく変更されることがあります。XML ドキュメントは `pgsn.load_xml` で読み込み、項は上のように Python で組み立てます。

```python
import pgsn

term = pgsn.load_xml("examples/gsn.xml")
print(pgsn.gsn_tree(term).show(stdout=False, sorting=False))
```

仕様は [README-ja-api.md](README-ja-api.md) にあります。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [README-ja-xml.md](README-ja-xml.md) | XML の構文。入門と参照 |
| [README-ja-api.md](README-ja-api.md) | Python API |
| [known_issues-ja.md](known_issues-ja.md) | 今の版が誤って動くところ、まだできないところ |
| `examples/` | 実行できるドキュメント。小さなものから EU AI Act のケース生成器まで |
| [PGSN-implementation.md](PGSN-implementation.md) | 処理系がなぜそう実装されているか。開発に加わる人向け（英語） |

どのドキュメントにも英語版があります（`README.md`・`README-xml.md`・`README-api.md`・`known_issues.md`）。

## ライセンス

MIT ライセンス – 詳細は [LICENSE](LICENSE) をご覧ください。

© 国立研究開発法人産業技術総合研究所 (AIST) 2023–2024  
山形頼之 2025-
