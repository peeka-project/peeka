---
layout: default
title: watch コマンド
parent: コマンドリファレンス
nav_order: 2
permalink: /commands/watch
---

# watch コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`watch` コマンドは、指定した Python 関数の実行を**オブザーブ**（観測）し、関数の**引数**、**戻り値**、**例外情報**、**実行時間**などのデータを取得します。Peeka の最も中心的な診断コマンドであり、本番環境でのリアルタイムな障害調査や性能分析に適しています。


## TUI での使用法

TUI モードでは **`2`** キーを押して **Watch ビュー**に切り替えると、以下のインタラクティブ機能が利用できます：

- **パターン入力**：ターゲットプロセスからリアルタイムに取得した関数名のオートコンプリートをサポート
- **パラメータ設定**：深度、回数、観測位置、条件式を視覚的に設定可能
- **リアルタイムストリーミング観測**：観測データをテーブルで表示し、自動更新
- **ショートカット操作**：
  - 入力モード後に Enter で観測開始
  - `s` キーで現在の観測を停止
  - `c` キーで観測記録をクリア
  - `r` キーでビューをリフレッシュ

**CLI との同等性**：以下の例はすべて CLI コマンドでデモンストレーションしていますが、TUI は同じ機能をグラフィカルなインターフェースで提供します。

## 使用場面

- **障害調査**：関数が正しく呼び出されているか、パラメータは正しいか、戻り値は期待通りかを確認
- **性能分析**：関数の実行時間を統計し、遅い呼び出しを特定
- **条件付き診断**：特定の条件を満たす呼び出しだけを観測（例：パラメータが特定の値より大きい場合のみ）
- **例外分析**：関数が投げる例外情報とスタックをキャプチャ
- **リアルタイムモニタリング**：JSON 形式でストリーム出力されるので、監視システムへの統合が容易

## コマンドフォーマット

```bash
peeka-cli attach <pid>    # まずターゲットプロセスにアタッチ
peeka-cli watch <pattern> [options]
```

### パラメータ説明

| パラメータ                | 説明                         | デフォルト     | 例                                      |
|-----------------------|----------------------------|-------------|-----------------------------------------|
| `pattern`             | 関数マッチングパターン                     | -       | `module.Class.method`                   |
| `-x, --depth`         | 出力オブジェクトの深度                     | `2`     | `-x 3`                                  |
| `-n, --times`         | 観測回数（-1 は無限）              | `-1`    | `-n 10`                                 |
| `--condition` | 条件式（`cost` 変数をサポート）   | なし       | `--condition "params[0] > 100"` |
| `-b, --before`        | 関数呼び出し前に観測（AtEnter）          | `false` | `-b`                                    |
| `-e, --exception`     | 例外が投げられたときだけ観測（AtExceptionExit） | `false` | `-e`                                    |
| `-s, --success`       | 正常リターン時だけ観測（AtExit）          | `false` | `-s`                                    |
| `-f, --finish`        | 関数終了後に観測（成功または例外）            | `true`  | `-f`                                    |

**注意**：

- `-b/-e/-s/-f` のいずれも指定しない場合、デフォルトで `-f`（すべての終了ケースを観測）になります
- `--condition` パラメータで後方互換性のため `--condition` が使われていますが、現在もサポートされています

### 関数マッチングパターン (pattern)

以下のフォーマットをサポートしています：

```python
# 1. モジュールレベルの関数
"mymodule.my_function"

# 2. クラスのメソッド
"mymodule.MyClass.my_method"

# 3. ネストされたクラスのメソッド
"mypackage.mymodule.OuterClass.InnerClass.method"

# 4. モジュールパス
"package.subpackage.module.function"
```

**注意**：インポートのルートから始まる完全なモジュールパスを使用する必要があり、ワイルドカードマッチングは現在サポートされていません。

## 基本的な使い方

### 1. 関数呼び出しの観測

```bash
# まずターゲットプロセスにアタッチ
peeka-cli attach 12345

# 5 回の呼び出しを観測
peeka-cli watch "calculator.Calculator.add" -n 5
```

**出力例**：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "calculator.Calculator.add",
  "params": [
    10,
    20
  ],
  "kwargs": {},
  "target": {
    "__attrs__": {
      "name": "calc1"
    }
  },
  "returnObj": 30,
  "success": true,
  "throwExp": null,
  "cost": 0.045,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**フィールド説明**：

| フィールド            | 説明                 | 例                                            |
|---------------|--------------------|------------------------------------------------|
| `watch_id`    | 観測 ID              | `"watch_a1b2c3d4"`                             |
| `timestamp`   | タイムスタンプ                | `1705586200.123`                               |
| `location`    | 観測位置               | `"AtEnter"` / `"AtExit"` / `"AtExceptionExit"` |
| `func_name`   | 関数名                | `"module.Class.method"`                        |
| `params`      | 位置引数                | `[10, 20]`                                     |
| `kwargs`      | キーワード引数              | `{"debug": true}`                              |
| `target`      | ターゲットオブジェクト（self、インスタンスメソッドのみ）   | `{"__attrs__": {...}}`                         |
| `returnObj`   | 戻り値                  | `30`                                           |
| `success`     | 成功したかどうか               | `true` / `false`                               |
| `throwExp`    | 例外情報                | `"ValueError: ..."`                            |
| `cost`        | 実行時間（ミリ秒）        | `0.045`                                        |
| `thread_id`   | スレッド ID              | `140234567890`                                 |
| `thread_name` | スレッド名                | `"MainThread"`                                 |

### 2. 出力深度の調整

```bash
# 深度 1：オブジェクトの型だけを表示
peeka-cli watch "service.UserService.get_user" -x 1

# 深度 3：3 層のネスト構造まで表示
peeka-cli watch "service.UserService.get_user" -x 3
```

**深度の比較**：

```python
# 元のオブジェクト
user = {
    "id": 1,
    "name": "Alice",
    "profile": {
        "age": 25,
        "address": {
            "city": "Beijing"
        }
    }
}

# depth=1
{"id": 1, "name": "Alice", "profile": "{'age': 25, 'address': {...}}"}

# depth=2
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": "{'city': 'Beijing'}"}}

# depth=3
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": {"city": "Beijing"}}}
```

### 3. 無限観測（ストリーミング出力）

```bash
# 継続的に観測し、手動で停止（Ctrl+C）
peeka-cli watch "api.handler.process_request"
```

適した場面：

- 本番環境でのリアルタイムモニタリング
- 間欠的に発生する問題の再現待ち
- 長時間のデータ収集と分析

### 4. 静的メソッドとクラスメソッドの観測

```bash
# 静的メソッド
peeka-cli watch "utils.Helper.static_method"

# クラスメソッド
peeka-cli watch "models.User.from_dict"
```

## 観測タイミングの制御

Peeka は複数の観測タイミングをサポートしており、関数実行のさまざまな段階で観測できます。

### 観測タイミングフラグ

| フラグ                | 説明    | 観測タイミング   | location フィールド                  | 利用可能なデータ                         |
|-------------------|-------|--------|------------------------------|------------------------------|
| `-b, --before`    | 関数呼び出し前 | 関数に入った時  | `AtEnter`                    | `params`, `kwargs`, `target` |
| `-s, --success`   | 成功リターン時 | 正常リターン後  | `AtExit`                     | 上記 + `returnObj`, `cost`     |
| `-e, --exception` | 例外スロー時 | 例外が投げられた後  | `AtExceptionExit`            | 上記 + `throwExp`, `cost`      |
| `-f, --finish`    | 関数終了時 | 成功または例外後 | `AtExit` / `AtExceptionExit` | すべてのフィールド                         |

**デフォルトの動作**：何も指定しない場合、デフォルトで `-f`（すべての終了ケースを観測）になります。

### 使用例

#### 1. 関数入口の状態を観測（-b）

```bash
# 関数が呼び出されたときのパラメータを観測
peeka-cli watch "service.UserService.update_user" -b
```

**出力**：

```json
{
  "location": "AtEnter",
  "params": [{"id": 1, "name": "Alice"}],
  "kwargs": {"force": true},
  "target": {"__attrs__": {"db": "..."}},
  "returnObj": null,
  "cost": 0.0
}
```

**用途**：

- 関数が呼び出されたことを確認
- 渡されたパラメータが正しいかチェック
- 関数入口ロジックのデバッグ

#### 2. 成功リターンのみ観測（-s）

```bash
# 成功した呼び出しだけを観測し、例外は無視
peeka-cli watch "api.handler.process" -s
```

**出力**（成功時のみ）：

```json
{
  "location": "AtExit",
  "params": [{"user_id": 123}],
  "returnObj": {"status": "ok"},
  "success": true,
  "cost": 45.2
}
```

**用途**：

- 成功呼び出しの戻り値を分析
- 成功呼び出しの性能を統計
- 例外ケースを無視

#### 3. 例外ケースのみ観測（-e）

```bash
# 例外を投げた呼び出しだけを観測
peeka-cli watch "database.query" -e
```

**出力**（例外発生時のみ）：

```json
{
  "location": "AtExceptionExit",
  "params": ["SELECT * FROM users"],
  "throwExp": "DatabaseError: Connection timeout",
  "success": false,
  "cost": 5000.0
}
```

**用途**：

- エラーケースに集中して分析
- 例外が発生する条件を分析
- エラー率のモニタリング

#### 4. 完全な実行プロセスを観測（-b -s）

```bash
# 入口と成功リターンを同時に観測
peeka-cli watch "calculator.calculate" -b -s
```

**出力**：1 回の呼び出しにつき 2 件のレコードが生成されます：

```json
// 1 件目：入口
{
  "location": "AtEnter",
  "params": [
    10,
    20
  ],
  "returnObj": null
}

// 2 件目：出口
{
  "location": "AtExit",
  "params": [
    10,
    20
  ],
  "returnObj": 30,
  "cost": 0.123
}
```

**用途**：

- パラメータが関数実行中に変更されるか観察
- 完全な関数実行フローをトレース
- 関数の副作用を分析

#### 5. すべてのケースを観測（-b -e -s）

```bash
# 入口、成功、例外すべてのケースを観測
peeka-cli watch "service.critical_operation" -b -e -s
```

**出力**：実行結果に応じて 2 件または 3 件のレコードが生成されます：

- 常に `AtEnter` レコードが 1 件生成される
- 成功時には `AtExit` レコードが 1 件生成される
- 例外時には `AtExceptionExit` レコードが 1 件生成される

**用途**：

- 複雑な関数の完全な診断
- 開発環境でのデバッグ
- 本番環境での深い分析

## 条件フィルタリング

### 条件式の構文

Peeka は **simpleeval** ライブラリを使用して安全な条件式評価を実現し、以下の構文をサポートしています：

#### サポートされる操作

| タイプ      | 演算子/関数                                                 | 例                                   |
|---------|--------------------------------------------------------|--------------------------------------|
| **比較**  | `>`, `<`, `>=`, `<=`, `==`, `!=`                       | `params[0] > 100`                    |
| **論理**  | `and`, `or`, `not`                                     | `params[0] > 10 and params[1] < 100` |
| **算術**  | `+`, `-`, `*`, `/`, `%`, `**`                          | `params[0] + params[1] > 100`        |
| **メンバー**  | `in`, `not in`                                         | `'error' in str(result)`             |
| **関数**  | `len()`, `str()`, `int()`, `float()`, `bool()`         | `len(params) > 2`                    |
| **文字列** | `.startswith()`, `.endswith()`, `.upper()`, `.lower()` | `str(params[0]).startswith('test_')` |
| **アクセス**  | `[]`, `.get()`                                         | `kwargs.get('debug') == True`        |

#### 使用可能な変数

| 変数       | 説明         | 型     | 利用可能なタイミング             |
|----------|------------|--------|------------------|
| `params` | 位置引数       | tuple  | すべてのタイミング             |
| `kwargs` | キーワード引数      | dict   | すべてのタイミング             |
| `target` | ターゲットオブジェクト（self） | object | すべてのタイミング（インスタンスメソッドのみ）      |
| `cost`   | 実行時間（ミリ秒）   | float  | `-s/-e/-f` でのみ利用可能 |

**注意**：

- `cost` 変数は関数実行完了後（`-s/-e/-f`）でのみ利用可能で、`-b` では利用できません
- `target` はインスタンスメソッドを観測する場合にのみ利用可能で、モジュールレベルの関数や静的メソッドでは `None` になります

**セキュリティ保護**：

- ❌ `__import__`, `eval`, `exec`, `compile`, `open` などの危険な関数は禁止
- ❌ `__class__`, `__subclasses__` などのリフレクション属性へのアクセスも禁止
- ❌ 任意のコードの実行は禁止

### 条件フィルタリングの例

#### 1. パラメータフィルタリング

```bash
# 最初のパラメータが 100 より大きい呼び出しだけを観測
peeka-cli watch "calculator.multiply" --condition "params[0] > 100"

# パラメータの数でフィルタリング
peeka-cli watch "api.handler" --condition "len(params) > 3"

# 複数条件の組み合わせ
peeka-cli watch "service.query" --condition "params[0] > 10 and params[1] < 100"
```

#### 2. キーワード引数フィルタリング

```bash
# debug パラメータが True の呼び出しだけを観測
peeka-cli watch "logger.log" --condition "kwargs.get('debug') == True"

# パラメータに特定のキーが存在するか確認
peeka-cli watch "api.request" --condition "'user_id' in kwargs"
```

#### 3. 文字列マッチング

```bash
# パラメータが特定のプレフィックスで始まる場合
peeka-cli watch "db.query" --condition "str(params[0]).startswith('SELECT')"

# パラメータに特定の部分文字列が含まれる場合
peeka-cli watch "handler.process" --condition "'error' in str(params[0])"
```

#### 4. 型チェック

```bash
# パラメータの型でフィルタリング
peeka-cli watch "converter.convert" --condition "isinstance(params[0], dict)"
```

#### 5. 複雑な条件

```bash
# 複数の条件を組み合わせ
peeka-cli watch "service.process" \
  --condition "len(params) > 2 and params[0] > 100 and 'debug' in kwargs"

# 文字列操作
peeka-cli watch "parser.parse" \
  --condition "len(str(params[0])) > 50 and str(params[0]).endswith('.json')"
```

#### 6. 性能フィルタリング（cost 変数）

```bash
# 実行時間が 100ms を超える呼び出しだけを観測
peeka-cli watch "database.query" --condition "cost > 100"

# 性能とパラメータの条件を組み合わせ
peeka-cli watch "api.handler" --condition "cost > 50 and len(params) > 0"

# 遅い呼び出しの戻り値を観測
peeka-cli watch "service.process" -s --condition "cost > 200"
```

**注意**：

- `cost` 変数は `-s/-e/-f` でのみ利用可能（関数実行完了後）
- `-b` で `cost` を使用すると、常に `cost=0` になるため条件は常に true になります

#### 7. オブジェクト状態によるフィルタリング（target 変数）

```bash
# 特定のオブジェクト状態を満たす呼び出しだけを観測（インスタンスメソッドのみ）
# 注意：現在のバージョンでは target 変数は利用可能ですが、simpleeval は属性アクセス（target.attr）をサポートしていません
# 条件の中で target が存在するかどうかはチェックできます
peeka-cli watch "service.UserService.update" --condition "params[0] > 0"
```

**制限**：

- 現在のバージョンでは `target` 変数は利用可能ですが、simpleeval は属性アクセス（`target.field_name`）をサポートしていません
- 将来のバージョンでオブジェクト属性アクセスが拡張される予定です

### 条件式のデバッグ

条件式が期待通りに動作しない場合は、以下を確認してください：

1. **構文エラー**：式が Python の構文に一致しているか確認
2. **変数のスペル**：`params` と `kwargs` を使用しているか確認（`args` ではなく）
3. **インデックスの範囲**：`params[i]` のインデックスが範囲外になっていないか確認
4. **型の誤り**：パラメータの実際の型に注意
5. **プリントデバッグ**：条件を追加せずにまず 1 回観測し、実際の params と kwargs の内容を確認

**例**：実際のパラメータ内容を確認

```bash
# まず条件なしで 1 回呼び出しを観測
peeka-cli watch "mymodule.func" -n 1

# 出力を確認：
# {"params": [100, "test"], "kwargs": {"debug": true}, ...}

# 次に実際の出力に基づいて条件を記述
peeka-cli watch "mymodule.func" --condition "params[0] > 50"
```

## 出力フォーマット

### JSON フィールド説明

毎回の関数呼び出しで 1 つの JSON レコードが出力されます：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "module.Class.method",
  "params": [1, 2],
  "kwargs": {"key": "value"},
  "target": {"__attrs__": {"field": "value"}},
  "returnObj": 42,
  "success": true,
  "throwExp": null,
  "cost": 1.234,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**フィールド説明**：

| フィールド            | 型      | 説明                                   |
|---------------|---------|--------------------------------------|
| `watch_id`    | string  | 観測セッション ID                              |
| `timestamp`   | float   | 呼び出し時間（Unix 時間）                       |
| `location`    | string  | 観測位置（AtEnter/AtExit/AtExceptionExit） |
| `func_name`   | string  | 関数の完全名                               |
| `params`      | array   | 位置引数リスト                               |
| `kwargs`      | object  | キーワード引数辞書                              |
| `target`      | object  | ターゲットオブジェクト（self、インスタンスメソッドのみ）                     |
| `returnObj`   | any     | 戻り値（成功時）                             |
| `success`     | boolean | 成功したかどうか                               |
| `throwExp`    | string  | 例外情報（失敗時）                            |
| `cost`        | float   | 実行時間（ミリ秒）                             |
| `thread_id`   | int     | スレッド ID                                |
| `thread_name` | string  | スレッド名                                 |

### 例外のキャプチャ

関数が例外を投げた場合：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExceptionExit",
  "func_name": "calculator.Calculator.divide",
  "params": [
    10,
    0
  ],
  "kwargs": {},
  "returnObj": null,
  "success": false,
  "throwExp": "ZeroDivisionError: division by zero",
  "cost": 0.032,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**注意**：Peeka は例外情報をキャプチャしますが**例外を抑制しません**。例外は引き続き正常に投げられます。

## データ処理と分析

### jq を使用した処理

```bash
# 1. 戻り値を抽出
peeka-cli watch "calculator.add" | jq '.returnObj'

# 2. 実行時間を抽出
peeka-cli watch "api.handler" | jq '.cost'

# 3. 遅い呼び出し（100ms 超）をフィルタリング
peeka-cli watch "db.query" | jq 'select(.cost > 100)'

# 4. 失敗した呼び出しだけを表示
peeka-cli watch "service.process" | jq 'select(.success == false)'

# 5. フォーマットされた出力
peeka-cli watch "func" | jq '{time: .timestamp, cost: .cost, result: .returnObj}'
```

### 統計分析

```bash
# 呼び出し回数を統計
peeka-cli watch "func" -n 100 | wc -l

# 平均実行時間を計算
peeka-cli watch "func" -n 100 | jq '.cost' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# 成功率を計算
peeka-cli watch "func" -n 100 | jq '.success' | \
  awk '{total++; if($1=="true") success++} END {print "success rate:", success/total*100, "%"}'

# 最も遅い呼び出しを見つける
peeka-cli watch "func" -n 100 | jq -s 'max_by(.cost)'
```

### ファイルに保存

```bash
# JSONL 形式で保存（1 行に 1 つの JSON）
peeka-cli watch "func" > observations.jsonl

# 後で分析
cat observations.jsonl | jq 'select(.cost > 10)'
```

### リアルタイムモニタリング

```bash
# エラー率をリアルタイムでモニタリング
peeka-cli watch "api.handler" | \
  jq -r 'if .success then "✓" else "✗ " + .throwExp end'

# 実行時間をリアルタイムで表示
peeka-cli watch "db.query" | \
  jq -r '"\(.timestamp | strftime("%H:%M:%S")) - \(.cost)ms"'
```

## 性能への影響

### 性能オーバーヘッド

| シナリオ                  | オーバーヘッド    | 説明          |
|---------------------|-------|-------------|
| **条件フィルタリングなし**           | < 2%  | 基本的なパラメータキャプチャとシリアル化 |
| **条件フィルタリングあり**            | < 3%  | 条件式評価のオーバーヘッドが追加 |
| **深度走査（depth=3）**   | < 5%  | ネストされたオブジェクトの深度走査    |
| **高頻度呼び出し（>1000 QPS）** | 5-10% | 高頻度なシリアル化とネットワーク転送  |

### 性能最適化の提案

1. **条件フィルタリングを使用する**：すべての呼び出しをキャプチャするのを避ける
   ```bash
   # 遅い呼び出しだけをキャプチャ
   peeka-cli watch "func" --condition "params[0] > 1000" -n 100
   ```

2. **観測回数を制限する**：`-n` パラメータを使用
   ```bash
   peeka-cli watch "func" -n 50  # 50 回だけ観測
   ```

3. **出力深度を下げる**：複雑なオブジェクトに対して
   ```bash
   peeka-cli watch "func" -x 1  # 1 層だけ表示
   ```

4. **高頻度関数の観測を避ける**：毎秒数千回呼び出されるような基本ツール関数の観測は避ける

5. **診断完了後に速やかに停止する**：
   ```bash
   # Ctrl+C で観測を停止
   ```

### メモリへの影響

- **バッファサイズ**：デフォルトで 10000 件の観測記録（約 10-50MB）
- **自動淘汰**：制限を超えると自動的に古いデータを破棄

## よくある問題

### 1. データが観測できない

**考えられる原因**：

- 関数が呼び出されていない
- 関数名のスペルが間違っている
- 条件式が厳しすぎる
- 既に観測回数制限（-n パラメータ）に達している

**調査手順**：

```bash
# 1. 関数名が正しいか確認（Python インタラクティブで確認）
python3 -c "import mymodule; print(mymodule.MyClass.my_method)"

# 2. 条件式を削除して、まず 1 回観測
peeka-cli watch "mymodule.func" -n 1

# 3. プロセスが存在するか確認
ps aux | grep 12345
```

### 2. 条件式でエラーが発生する

**よくあるエラー**：

```bash
# ❌ エラー：禁止された操作を使用
--condition "__import__('os').system('ls')"  # セキュリティによりブロックされる

# ❌ エラー：インデックス範囲外
--condition "params[5] > 10"  # 関数には 3 つのパラメータしかない

# ❌ エラー：変数名の間違い
--condition "args[0] > 10"  # params を使用するべき

# ✓ 正しい
--condition "len(params) > 2 and params[0] > 10"
```

**デバッグ方法**：

1. 条件なしで 1 回観測し、実際のパラメータを確認
2. 単純な条件からテスト（例えば `len(params) > 0`）
3. 徐々に条件の複雑さを増やしていく

### 3. 出力深度が足りない

```bash
# 問題：オブジェクトが "{'key': {...}}" と表示される
peeka-cli watch "func" -x 2

# 解決：深度を増やす
peeka-cli watch "func" -x 3
```

**注意**：最大深度は 4 です。深すぎる走査は性能問題を引き起こすため制限されています。

### 4. 観測はビジネスに影響しますか？

**安全保障**：

- ✓ 例外は抑制されない（正常に投げられる）
- ✓ 観測が失敗しても元の関数の実行に影響はない
- ✓ 自動的にリソースがクリーンアップされる（メモリ、接続）
- ✓ 低い性能オーバーヘッド（< 5%）

**ベストプラクティス**：

- 低負荷時に初回使用する
- 低頻度関数から観測を始める
- 条件フィルタリングを使用してデータ量を減らす
- 観測後は速やかに停止する

### 5. 観測を停止するには？

```bash
# 方法 1：Ctrl+C で現在の観測を停止
# 方法 2：reset コマンドを使用して観測強化を削除
peeka-cli reset "pattern"

# 方法 3：対話モードですべての観測を停止（現在 CLI は直接サポートしていません。Ctrl+C で停止してください）
```

## 高度なテクニック

### 1. マルチプロセス観測

```bash
# 複数のプロセスを並行して観測
for pid in 12345 12346 12347; do
  peeka-cli attach $pid
  peeka-cli watch "api.handler" > "logs/watch_$pid.jsonl" 2>&1 &
done
```

### 2. 定期的な観測

```bash
# 毎時間 100 回ずつ観測
while true; do
  peeka-cli watch "scheduler.task" -n 100 >> hourly_samples.jsonl
  sleep 3600
done
```

### 3. アラート統合

```bash
# エラー率を監視し、閾値を超えたらアラート
peeka-cli watch "api.handler" | \
  jq -r 'select(.success == false) | .throwExp' | \
  while read error; do
    echo "Alert: $error" | mail -s "API Error" admin@example.com
  done
```

### 4. Prometheus との統合

```python
# 観測データを Prometheus メトリクスに変換
import json
from prometheus_client import Counter, Histogram

call_counter = Counter('function_calls_total', 'Total calls', ['function', 'status'])
duration_histogram = Histogram('function_duration_seconds', 'Duration', ['function'])

for line in sys.stdin:
    data = json.loads(line)
    func = data['func_name']
    status = 'success' if data['success'] else 'error'

    call_counter.labels(function=func, status=status).inc()
    duration_histogram.labels(function=func).observe(data['cost'] / 1000)
```

## 参考資料

- [simpleeval ドキュメント](https://github.com/danthedeckie/simpleeval)
- [Peeka アーキテクチャ設計](../architecture.md)
- [Peeka 開発ガイド](../ai-skill.md)

## 更新履歴

| バージョン    | 日付      | 更新内容               |
|-------|---------|--------------------|
| 0.1.0 | 2025-01 | 初期バージョン、基本的な watch 機能をサポート |
