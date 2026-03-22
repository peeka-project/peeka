---
layout: default
title: stack コマンド
parent: コマンドリファレンス
nav_order: 4
permalink: /commands/stack
---

# stack コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`stack` コマンドは、関数が呼び出されたときに完全な呼び出しスタック情報をキャプチャし、開発者が関数の呼び出しパスを追跡するのを助けます。複雑な呼び出しチェーンの分析や問題の原因の特定に適した強力なデバッグツールです。

**核心機能**：
- 関数呼び出し時に完全な呼び出しスタックをキャプチャ
- 呼び出しチェーン上のファイル名、行番号、関数名、コードスニペットを表示
- 条件フィルタリングをサポート（特定の条件を満たす場合だけキャプチャ）
- 設定可能なスタック深度（長すぎる出力を避ける）
- リアルタイムストリーミング出力（JSON 形式）

**watch コマンドとの違い**：
- `watch`：関数の**パラメータ、戻り値、実行時間**を観測
- `stack`：関数の**呼び出しパス**（どこから呼び出されたか）を観測

## TUI での使用法

TUI モードでは **`4`** キーを押して **Stack ビュー**に切り替えると、以下のインタラクティブ機能が利用できます：

- **パターン入力**：ターゲットプロセスからリアルタイムに取得した関数名のオートコンプリートをサポート
- **パラメータ設定**：キャプチャ回数、条件式、スタック深度を視覚的に設定可能
- **呼び出しスタックの可視化**：テーブル形式でリアルタイムに呼び出しスタックを表示
  - ファイル名、行番号、関数名、コード内容を表示
  - キャプチャごとに完全な呼び出しチェーンを表示（最内層から最外層まで）
- **ショートカット操作**：
  - 入力モード後に Enter でキャプチャ開始
  - `c` キーでキャプチャ記録をクリア
  - Delete キーで選択された記録を削除
  - 上下方向キーで呼び出しスタックの階層を閲覧

**CLI との同等性**：以下の例はすべて CLI コマンドでデモンストレーションしていますが、TUI は同じ機能をグラフィカルなインターフェースで提供します。
---

## 使用場面

### 1. 呼び出し元の追跡

**シナリオ**：ある関数が複数の場所から呼び出されていて、特定の呼び出しパスを特定したい。

```bash
# process_order 関数がどこから呼び出されたかを確認
peeka-cli stack "myapp.orders.process_order"
```

**出力例**：
```json
{
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [{"order_id": 12345}],
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    },
    {
      "filename": "/usr/lib/python3.14/http/server.py",
      "lineno": 89,
      "function": "handle_request",
      "code_context": "self.handle_one_request()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "Thread-5"
}
```

### 2. 再帰呼び出しの分析

**シナリオ**：再帰関数がスタックオーバーフローを起こし、再帰深度と呼び出しパターンを分析する必要がある。

```bash
# スタック深度を 20 層に制限し、長すぎる出力を避ける
peeka-cli stack "myapp.utils.recursive_func" --depth 20
```

### 3. 異常な呼び出しパスの特定

**シナリオ**：特定の条件下で関数がエラーを起こし、エラーが発生したときの呼び出しチェーンを追跡したい。

```bash
# user_id が 999 の場合だけ呼び出しスタックをキャプチャ
peeka-cli stack "myapp.auth.check_permission" \
  --condition "params[0] == 999"
```

### 4. ホットスポット呼び出しパスの分析

**シナリオ**：性能分析で、どのパスが最も頻繁に特定の関数を呼び出しているかを知りたい。

```bash
# 最初の 100 回の呼び出しをキャプチャし、呼び出しパスの分布を統計
peeka-cli stack "myapp.db.execute_query" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn
```

### 5. クロスモジュール呼び出しの追跡

**シナリオ**：マイクロサービスアーキテクチャで、リクエストが異なるモジュール間を渡るパスを追跡したい。

```bash
# API エントリー関数の呼び出しチェーンを追跡
peeka-cli stack "myapp.api.handle_request"
```
---

## コマンドフォーマット

```bash
# 必須：最初にターゲットプロセスにアタッチ
peeka-cli attach <pid>

# 次に stack コマンドを実行
peeka-cli stack <pattern> [options]
```

### パラメータ説明

**必須パラメータ**：
- `pattern`：ターゲット関数のパターン（`module.Class.method` の形式）

**任意パラメータ**：
- `-n, --times`：キャプチャ回数（-1 は無限、デフォルト -1）
- `--condition`：条件式（条件を満たす場合だけキャプチャ）
- `--depth`：スタック深度制限（デフォルト 10）

---

## パラメータ詳細

### pattern - 関数パターン

追跡したいターゲット関数を指定し、以下のフォーマットをサポート：

| フォーマット | 説明 | 例 |
|------|------|------|
| `module.function` | モジュールレベル関数 | `myapp.utils.calculate` |
| `module.Class.method` | クラスメソッド | `myapp.models.User.save` |
| `module.Class.static_method` | 静的メソッド | `myapp.utils.Helper.validate` |

**注意点**：
- モジュールのルートから始まる完全限定名を使用する必要がある
- ワイルドカードはサポートされていない（`watch` コマンドと同じ）
- ターゲット関数は既にメモリにロードされている必要がある

### --times, -n - キャプチャ回数

キャプチャする回数を制御し、膨大なデータの生成を避けます。

| 値 | 動作 | 適した場面 |
|----|------|----------|
| `-1`（デフォルト）| 無限にキャプチャ | 持続的なモニタリング、本番環境の問題調査 |
| `1` | 1 回キャプチャしたら自動停止 | 一度だけ呼び出しスタックを見れば十分 |
| `N` | N 回キャプチャしたら自動停止 | サンプリング分析、呼び出しパスの統計 |

**例**：
```bash
# 最初の呼び出しだけを見る
peeka-cli stack "myapp.func" -n 1

# 50 回のサンプルをキャプチャ
peeka-cli stack "myapp.func" -n 50
```

### --condition - 条件式

条件を満たす場合だけ呼び出しスタックをキャプチャし、無関係なデータの出力を避けます。

**利用可能な変数**：
- `params`：関数の位置引数（tuple）
- `kwargs`：関数のキーワード引数（dict）
- `target`：インスタンスメソッドの `self` オブジェクト

**サポートされる演算子**：
- 比較：`==`, `!=`, `>`, `<`, `>=`, `<=`
- 論理：`and`, `or`, `not`
- メンバー確認：`in`, `not in`
- 文字列：`str(x).startswith()`, `str(x).endswith()`
- 長さ：`len(params)`, `len(kwargs)`
- インデックスアクセス：`params[0]`, `kwargs.get('key')`

**例**：
```bash
# 最初の引数が 100 より大きい場合だけキャプチャ
peeka-cli stack "myapp.func" --condition "params[0] > 100"

# 引数の数が 2 より大きい場合だけキャプチャ
peeka-cli stack "myapp.func" --condition "len(params) > 2"

# キーワード引数 user_id が 999 と等しい場合だけキャプチャ
peeka-cli stack "myapp.check_permission" \
  --condition "kwargs.get('user_id') == 999"

# 複合条件
peeka-cli stack "myapp.process" \
  --condition "params[0] > 10 and len(params) < 5"
```

**セキュリティ**：
- `simpleeval` ライブラリを基に実装され、すべての危険な操作が無効化されている
- 許可されないもの：`eval`, `exec`, `__import__`, `open`, `compile`
- 許可されないアクセス：`__class__`, `__subclasses__`
- ホワイトリストに登録された安全な操作だけがサポートされている

### --depth - スタック深度制限

キャプチャする呼び出しスタックの階層数を制御し、長すぎる出力を避けます。

| 値 | 説明 | 適した場面 |
|----|------|----------|
| `10`（デフォルト）| 10 層の呼び出しスタック | 一般的なデバッグシナリオ |
| `5` | 5 層の呼び出しスタック | 直近の数層の呼び出しだけに関心がある |
| `20` | 20 層の呼び出しスタック | 深度のある再帰分析 |
| `50` | 50 層の呼び出しスタック | 極端なシナリオ（推奨されない） |

**注意**：
- スタック深度は**ターゲット関数の呼び出し元**から数えて計算される（ターゲット関数自体は含まれない）
- 深度が大きいほど、出力データ量が大きくなる
- 必要に応じて合理的な深度（5-20 層）を設定することが推奨される

**例**：
```bash
# 直近 3 層の呼び出し元だけを見る
peeka-cli stack "myapp.func" --depth 3

# 深度のある再帰を分析（最大 30 層）
peeka-cli stack "myapp.recursive_func" --depth 30
```
---

## 出力フォーマット

`stack` コマンドは JSON Lines 形式（1 行に 1 つの JSON オブジェクト）を出力し、ストリーム処理とツールへの統合に適しています。

### 完全な出力例

```json
{
  "watch_id": "watch_20260131_001",
  "timestamp": 1738339200.123456,
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [
    {"order_id": 12345, "amount": 99.99}
  ],
  "kwargs": {
    "priority": "high"
  },
  "target": {
    "__attrs__": {
      "user_id": 999,
      "session": "<Session object>"
    }
  },
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/rate_limiter.py",
      "lineno": 78,
      "function": "rate_limit_decorator",
      "code_context": "return func(*args, **kwargs)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "ThreadPoolExecutor-3",
  "cost": 0.0
}
```

### フィールド説明

| フィールド | 型 | 説明 |
|------|------|------|
| `watch_id` | string | 観測タスクの一意な識別子 |
| `timestamp` | float | Unix タイムスタンプ（秒、小数を含む） |
| `location` | string | 観測位置（`AtEnter` は関数入口） |
| `pattern` | string | ターゲット関数のパターン |
| `params` | array | 関数の位置引数 |
| `kwargs` | object | 関数のキーワード引数 |
| `target` | object | インスタンスメソッドの `self` オブジェクト（クラスメソッドにのみ存在） |
| `stack` | array | 呼び出しスタックフレームの配列（最も重要なフィールド） |
| `thread_id` | int | スレッド ID |
| `thread_name` | string | スレッド名 |
| `cost` | float | 実行時間（ミリ秒、`AtEnter` では 0.0） |

### stack 配列の要素

各スタックフレーム（frame）は以下のフィールドを含みます：

| フィールド | 型 | 説明 |
|------|------|------|
| `filename` | string | ソースコードファイルの絶対パス |
| `lineno` | int | ソースコードの行番号 |
| `function` | string | 関数/メソッド名 |
| `code_context` | string | その行のソースコード内容（前後の空白を除去） |

**スタックフレームの順序**：
- `stack[0]`：**最も近い呼び出し元**（ターゲット関数を直接呼び出した場所）
- `stack[1]`：呼び出し元の呼び出し元
- `stack[n]`：インデックスが大きいほど呼び出しチェーンの根に近づく
---

## 使用例

### 例 1：基本的な呼び出しスタック追跡

**シナリオ**：`calculate_price` 関数がどこから呼び出されたかを確認する。

```bash
peeka-cli stack "myapp.pricing.calculate_price"
```

**出力**：
```json
{
  "watch_id": "watch_001",
  "timestamp": 1738339200.123,
  "location": "AtEnter",
  "pattern": "myapp.pricing.calculate_price",
  "params": [{"product_id": 789, "quantity": 5}],
  "stack": [
    {
      "filename": "/app/myapp/api/cart.py",
      "lineno": 234,
      "function": "checkout",
      "code_context": "total = calculate_price(cart_items)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 89,
      "function": "checkout_view",
      "code_context": "result = cart.checkout()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**解釈**：
- `calculate_price` は `cart.py:234` の `checkout` 関数から呼び出されている
- `checkout` は `views.py:89` の `checkout_view` 関数から呼び出されている

### 例 2：条件フィルタリングによる追跡

**シナリオ**：パラメータが負の場合だけ追跡したい（異常な状況の可能性が高い）。

```bash
peeka-cli stack "myapp.utils.process_value" \
  --condition "params[0] < 0" \
  -n 10
```

**出力**（パラメータが負の場合だけ出力される）：
```json
{
  "watch_id": "watch_002",
  "timestamp": 1738339201.456,
  "location": "AtEnter",
  "pattern": "myapp.utils.process_value",
  "params": [-5],
  "stack": [
    {
      "filename": "/app/myapp/data/processor.py",
      "lineno": 67,
      "function": "validate_input",
      "code_context": "result = process_value(user_input)"
    }
  ],
  "thread_id": 140234567891,
  "thread_name": "WorkerThread-2"
}
```

**用途**：異常な入力の発生源を素早く特定できる。

### 例 3：スタック深度の制限

**シナリオ**：直近の 3 層の呼び出し元だけに関心がある。

```bash
peeka-cli stack "myapp.db.execute_query" --depth 3
```

**出力**：
```json
{
  "watch_id": "watch_003",
  "timestamp": 1738339202.789,
  "location": "AtEnter",
  "pattern": "myapp.db.execute_query",
  "params": ["SELECT * FROM users WHERE id = ?", [999]],
  "stack": [
    {
      "filename": "/app/myapp/models/user.py",
      "lineno": 123,
      "function": "get_by_id",
      "code_context": "return db.execute_query(sql, params)"
    },
    {
      "filename": "/app/myapp/api/users.py",
      "lineno": 45,
      "function": "get_user",
      "code_context": "user = User.get_by_id(user_id)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 78,
      "function": "user_profile_view",
      "code_context": "return get_user(request.user_id)"
    }
  ]
}
```

### 例 4：1 回キャプチャしたら停止

**シナリオ**：一度だけ呼び出しスタックを確認すれば十分で、呼び出しパスを確認できたら停止したい。

```bash
peeka-cli stack "myapp.cache.get" -n 1
```

**動作**：最初の呼び出しをキャプチャした後、自動的に追跡を停止します。

### 例 5：jq と組み合わせた分析

**シナリオ：すべての呼び出し元を抽出し、どのファイルが最も頻繁にターゲット関数を呼び出しているか統計する。**

```bash
peeka-cli stack "myapp.logger.log" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn | head -10
```

**出力**：
```
    45 /app/myapp/api/views.py:123
    23 /app/myapp/middleware/auth.py:67
    12 /app/myapp/utils/helper.py:234
    ...
```

**解釈**：`views.py:123` が最も頻繁に（45 回）呼び出していることがわかる。

### 例 6：マルチスレッド呼び出しの分析

**シナリオ**：どのスレッドがターゲット関数を呼び出しているか分析する。

```bash
peeka-cli stack "myapp.shared.resource.access" -n 50 | \
  jq -r '.thread_name' | sort | uniq -c
```

**出力**：
```
    30 WorkerThread-1
    15 WorkerThread-2
     5 MainThread
```

---

## 完全な診断フロー

### フロー 1：異常な呼び出しパスの特定

**目標**：関数が特定の条件で例外を投げていて、どの呼び出しパスがトリガーしているかを見つける。

```bash
# 手順 1：異常なパラメータの呼び出しだけを追跡
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" \
  -n 20 > stack_trace.jsonl

# 手順 2：呼び出しパスを分析
jq -r '.stack[] | "\(.filename):\(.lineno) - \(.function)"' stack_trace.jsonl

# 手順 3：最も頻繁な異常な発生源を特定
jq -r '.stack[0] | "\(.filename):\(.lineno)"' stack_trace.jsonl | \
  sort | uniq -c | sort -rn
```

**出力例**：
```
    12 /app/myapp/api/refund.py:89
     3 /app/myapp/jobs/reconcile.py:234
```

**結論**：`refund.py:89` が主な問題の発生源なので、そこの入力検証ロジックを確認する。

### フロー 2：性能ホットスポットパス分析

**目標**：特定のデータベースクエリ関数が頻繁に呼び出されていて、どのパスが最も頻繁かを見つける。

```bash
# 手順 1：200 回の呼び出しをキャプチャしてファイルに保存
peeka-cli stack "myapp.db.query" -n 200 > query_stacks.jsonl

# 手順 2：最初の 3 層の呼び出しパスを統計
jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' \
  query_stacks.jsonl | sort | uniq -c | sort -rn | head -10
```

**出力例**：
```
    89 /app/myapp/api/list.py:123 -> /app/myapp/models/user.py:45
    34 /app/myapp/api/search.py:67 -> /app/myapp/models/user.py:45
    12 /app/myapp/jobs/sync.py:234 -> /app/myapp/models/user.py:45
```

**結論**：`list.py:123` のパスが最も頻度が高い（89 回）ので、このパスを優先的に最適化する。

### フロー 3：再帰深度分析

**目標**：再帰関数がスタックオーバーフローを起こし、再帰深度を分析する。

```bash
# 手順 1：50 層までスナップショットを撮影
peeka-cli stack "myapp.tree.traverse" --depth 50 -n 10 > recursion.jsonl

# 手順 2：各呼び出しのスタック深度を計算
jq '.stack | length' recursion.jsonl

# 手順 3：最も深い呼び出しを見つける
jq -s 'max_by(.stack | length)' recursion.jsonl > deepest.json

# 手順 4：最も深い呼び出しのパスを分析
jq '.stack[] | "\(.function) at \(.filename):\(.lineno)"' deepest.json
```

**出力例**：
```
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
... (48 回繰り返し)
process_tree at /app/myapp/api/views.py:123
```

**結論**：再帰深度が 48 層に達しているので、再帰終了条件を最適化するか、反復実装に変更する必要がある。
---

## 注意点

### 1. 性能への影響

**影響の程度**：
- **スタックフレームのキャプチャ**：1 回のキャプチャあたり約 0.5-2ms の追加オーバーヘッド（スタック深度に依存）
- **JSON シリアライズ**：1 回あたり約 0.2-0.5ms
- **ネットワーク転送**：1 回あたり約 0.1-0.3ms（Unix Domain Socket）

**全体のオーバーヘッド**：約 1-3ms/回（高頻度関数でも累積すると 5-10% CPU になることがある）

**最適化の提案**：
- `--condition` を使用してキャプチャ回数を減らす
- 合理的な `--depth` を設定する（デフォルトの 10 層で通常は十分）
- 超高頻度関数（毎秒 1 万回以上呼び出される）の追跡は避ける
- `-n` を使用してキャプチャ回数を制限する（デバッグ完了後に速やかに停止する）

### 2. 出力データ量

**データ量の見積もり**：
- スタックフレーム 1 つあたり約 200-300 バイト（JSON）
- 10 層の呼び出しスタックで約 2-3 KB
- 1000 回のキャプチャで約 2-3 MB

**管理の提案**：
- ファイルに出力する：`peeka-cli stack ... > output.jsonl`
- 定期的に出力ファイルをクリーンアップ
- ストリーム処理（`jq`）を使用し、一度に全部をメモリにロードしない

### 3. スレッド安全性

**注意点**：
- マルチスレッド環境では、異なるスレッドの呼び出しスタックがインターリーブされて出力される
- `thread_id` と `thread_name` フィールドを使用してスレッドを区別できる
- `jq` を使用して特定のスレッドをフィルタリングできる：
  ```bash
  peeka-cli stack "myapp.func" | \
    jq 'select(.thread_name == "WorkerThread-1")'
  ```

### 4. 条件式の制限

**制限**：
- `cost` 変数はサポートされていない（`stack` は関数入口でキャプチャされ、実行がまだ完了していないため）
- 戻り値（`returnObj`）にアクセスできない（同様の理由）
- 複雑なオブジェクトメソッド呼び出しをサポートしていない（例：`params[0].some_method()`）

**利用可能な変数**：`params`、`kwargs`、`target` のみ

### 5. スタックフレーム数の制限

**制限**：
- デフォルトで最大 10 層をキャプチャ（`--depth` で調整可能）
- Python インタープリタのデフォルトの最大再帰深度は 1000（`sys.getrecursionlimit()`）
- `--depth` を 50 以上に設定することは推奨されない（データ量が大きすぎるため）
---

## よくある問題

### Q1: 実行中の stack 追跡を停止するには？

**A**:
- `reset` コマンドを使用して強化を削除します：
  ```bash
  peeka-cli reset "pattern"
  ```

**注意**：
- Ctrl+C を使用してクライアントのストリーミング受信を停止しても、ターゲットプロセス中の強化は依然として実行されています
- 完全にクリーンアップするには `reset` コマンドを使用する必要があります
- 観測が不要になったら速やかに reset してください

### Q2: なぜ code_context フィールドが None になるの？

**原因**：
- ソースコードファイルにアクセスできない（`.pyc` コンパイル済みコード）
- ソースコードファイルが削除または移動されている
- Python の組み込みモジュール（C 拡張）

**解決方法**：
- ソースコードファイルが存在しアクセス可能であることを確認してください
- C 拡張モジュールではソースコードを取得できないのは正常な現象です

### Q3: stack コマンドと watch コマンドを同時に使用できますか？

**答え**：はい、同時に使用できます。

**例**：
```bash
# ターミナル 1：呼び出しスタックを追跡
peeka-cli stack "myapp.func" > stack.jsonl

# ターミナル 2：パラメータと戻り値を観測
peeka-cli watch "myapp.func" > watch.jsonl
```

**注意**：
- 2 つのコマンドはそれぞれ別のデコレータを注入するので、性能影響が累加されます
- 必要に応じて使用し、過度な追跡は避けてください

### Q4: 標準ライブラリ関数の呼び出しスタックを追跡できますか？

**答え**：完全なモジュールパスを使用すれば追跡できます。

**例**：
```bash
# json.dumps の呼び出しスタックを追跡
peeka-cli stack "json.dumps" --depth 5

# logging モジュールの info メソッドを追跡
peeka-cli stack "logging.Logger.info" --depth 3
```

**注意**：
- 標準ライブラリ関数は通常呼び出し頻度が非常に高いので、条件フィルタリングと回数制限を使用することを推奨します
- 一部の C 拡張関数ではコード内容を取得できません

---

## まとめ

`stack` コマンドは関数の呼び出しパスを追跡する強力なツールで、特に以下の場面に適しています：
- 異常な呼び出し元の特定
- 複雑な呼び出しチェーンの分析
- 性能ホットスポット呼び出しパスの分析
- 再帰深度の診断

**ベストプラクティス**：
- 条件フィルタリングを使用して無関係なデータを減らす
- 合理的なスタック深度を設定する（5-20 層）
- キャプチャ回数を制限する（膨大なデータの生成を避ける）
- `jq` と組み合わせて強力なデータ分析を行う
- デバッグ完了後に速やかに追跡を停止する

**次のステップ**：
- [`watch`](watch.md) コマンド（パラメータと戻り値の観測）を理解する
- [`memory`](memory.md) コマンド（メモリ分析）を理解する
- 開発ガイドの [AI エージェントスキル](../ai-skill.md) を参照する
