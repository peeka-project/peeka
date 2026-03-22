---
layout: default
title: Peeka logger コマンドガイド
parent: コマンドリファレンス
nav_order: 6
permalink: /commands/logger
---

# Peeka logger コマンドガイド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## コマンド概要

`logger` コマンドを使用すると、プロセスを再起動したり設定ファイルを変更したりすることなく、実行時に Python アプリケーションのログレベルを動的に表示および調整できます。これは本番環境での問題のトラブルシューティングに強力なツールです。

**コア機能**:
- すべてのロガーと現在のログレベルを一覧表示
- 特定のロガーの設定情報をクエリ
- ロガーのログレベルを動的に変更
- 複数のロガーに対するワイルドカードパターンマッチングをサポート
- プロセスを再起動せずに変更がすぐに有効

**一般的なシナリオ**:
- トラブルシューティングのために本番環境で一時的に DEBUG ログを有効化
- サードパーティライブラリの冗長なログを抑制
- パフォーマンス最適化のために動的にログレベルを調整
- ログ欠落の診断（ロガー設定を確認）

---

## 使用場面

### 1. 本番環境で一時的にデバッグログを有効化

**シナリオ**: 本番環境で問題が発生し、トラブルシューティングのために一時的に DEBUG ログを有効にする必要があるが、サービスを再起動できない。

```bash
# ステップ 1: 現在のログレベルを確認
peeka-cli logger --action get --logger myapp.payment

# 出力:
# {"status": "success", "name": "myapp.payment", "level": "INFO", "level_num": 20}

# ステップ 2: 一時的に DEBUG レベルを有効化
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 出力:
# {"status": "success", "name": "myapp.payment", "old_level": "INFO", "new_level": "DEBUG"}

# ステップ 3: トラブルシューティング完了後に元のレベルを復元
peeka-cli logger --action set --logger myapp.payment --level INFO
```

**効果**: プロセスを再起動せずにすぐに有効になり、ログファイルに詳細なデバッグ情報が出力され始めます。

### 2. サードパーティライブラリの冗長なログを抑制

**シナリオ**: サードパーティライブラリ（urllib3 や boto3 など）が過剰な DEBUG ログを出力して、アプリケーションのログが見えなくなる。

```bash
# "urllib3" を含むすべてのロガーを表示
peeka-cli logger --action list --pattern "urllib3*"

# urllib3 のデバッグログを抑制
peeka-cli logger --action set --logger urllib3 --level WARNING

# boto3 についても同様に実行
peeka-cli logger --action set --logger botocore --level WARNING
```

**効果**: サードパーティライブラリは WARNING 以上のレベルのログだけを出力するようになり、アプリケーションのログがはっきり見えるようになります。

### 3. ログ欠落の診断

**シナリオ**: 特定のモジュールのログが出力されない、ロガー設定の問題が疑われる。

```bash
# ステップ 1: ロガーが存在するか確認
peeka-cli logger --action get --logger myapp.missing_logs

# 出力が "Logger not found" なら、ロガーがまだ初期化されていない
# 出力レベルが ERROR なら、ログレベルが高すぎる

# ステップ 2: すべてのロガーを表示して、関連するものを見つける
peeka-cli logger --action list --pattern "myapp.*"

# ステップ 3: レベルを下げるかロガーを作成（set アクションは自動作成します）
peeka-cli logger --action set --logger myapp.missing_logs --level DEBUG
```

### 4. バッチでモジュールのログレベルを表示

**シナリオ**: すべてのアプリケーションモジュールのログ設定が期待通りか確認する。

```bash
# すべてのアプリケーションロガーを表示（すべて "myapp" で始まると仮定）
peeka-cli logger --action list --pattern "myapp.*" | jq .

# フォーマットされたロガーリストを出力して、設定レビューが容易になる
```

### 5. パフォーマンス最適化: 不要なログを無効化

**シナリオ**: 本番環境でログ I/O がパフォーマンスボトルネックになっていて、一部のログを一時的に無効にする必要がある。

```bash
# コアでないモジュールすべてのログレベルを WARNING に上げる
peeka-cli logger --action set --logger myapp.analytics --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING
peeka-cli logger --action set --logger myapp.metrics --level WARNING
```

---

## TUI での使用法

TUI モードでは、**`7`** キーを押して **Logger ビュー** に切り替えると、以下のインタラクティブ機能が利用できます：

- **ロガーリスト表示**: すべてのロガーと現在のレベルを自動的にロードして表示
  - ロガー名でソート
  - ロガー名、現在のレベル、レベル番号を表示
  - リアルタイム更新ボタン
- **レベル変更**: 選択したロガーのレベルを素早く調整
  - DEBUG, INFO, WARNING, ERROR, CRITICAL をサポート
  - 変更はすぐに有効
- **パターンフィルタリング**: fnmatch ワイルドカード（`*` と `?`）をサポートしてロガーをフィルタリング
- **クイック操作**:
  - 上/下矢印キーでロガーを選択
  - Enter を押して選択したロガーのレベルを変更
  - `r` を押してロガーリストを更新

**CLI との同等性**: 以下の例はデモンストレーションのために CLI コマンドを使用しています。TUI はグラフィカルインターフェースで同じ機能を提供します。

## コマンドフォーマット

```bash
peeka-cli logger [--action ACTION] [options]
```

**必須**:
- 最初に `peeka-cli attach <pid>` でターゲットプロセスにアタッチする必要があります

**オプションパラメータ**:
- `--action`: 操作タイプ（`list`、`get`、`set`、デフォルト `list`）
- `--logger`: ロガー名（`get` と `set` 操作で必須）
- `--level`: ログレベル（`set` 操作で必須）
- `--pattern`: マッチングパターン（`list` 操作でオプション）

---

## 操作

### 1. list - すべてのロガーを一覧表示

**目的**: プロセス内で初期化されたすべてのロガーとそれらの現在のログレベルを表示します。

**構文**:
```bash
peeka-cli logger --action list [--pattern <pattern>]
```

**パラメータ**:
- `--pattern` (オプション): fnmatch スタイルのパターン（`*` と `?` ワイルドカードをサポート）

**例**:
```bash
# すべてのロガーを一覧表示
peeka-cli logger --action list

# myapp 名前空間のロガーだけを一覧表示
peeka-cli logger --action list --pattern "myapp.*"

# "db" を含むすべてのロガーを一覧表示
peeka-cli logger --action list --pattern "*db*"
```

**出力**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "myapp.api", "level": "DEBUG", "level_num": 10}
  ],
  "count": 3
}
```

### 2. get - 特定のロガーをクエリ

**目的**: 特定のロガーの詳細な設定を表示します。

**構文**:
```bash
peeka-cli logger --action get --logger <name>
```

**パラメータ**:
- `--logger` (必須): 完全なロガー名（ワイルドカードはサポートされていません）

**例**:
```bash
peeka-cli logger --action get --logger myapp.payment
```

**成功時の出力**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**失敗時の出力**:
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### 3. set - ロガーレベルを変更

**目的**: ロガーのログレベルを動的に変更し、すぐに有効になります。

**構文**:
```bash
peeka-cli logger --action set --logger <name> --level <level>
```

**パラメータ**:
- `--logger` (必須): ロガー名（存在しない場合は自動作成されます）
- `--level` (必須): 新しいログレベル（以下のサポートされているレベルを参照）

**サポートされているログレベル**:
| レベル | 値 | 説明 |
|------|------|------|
| `DEBUG` | 10 | 詳細なデバッグ情報 |
| `INFO` | 20 | 一般的な情報メッセージ |
| `WARNING` | 30 | 警告メッセージ（デフォルトレベル） |
| `ERROR` | 40 | エラーメッセージ |
| `CRITICAL` | 50 | 重大なエラー |
| `NOTSET` | 0 | 未設定（親ロガーから継承） |

**例**:
```bash
# DEBUG ログを有効化
peeka-cli logger --action set --logger myapp.auth --level DEBUG

# INFO レベルのログを無効化（警告とエラーだけを保持）
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# デフォルトレベルを復元
peeka-cli logger --action set --logger myapp.auth --level INFO
```

**出力**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**注意**:
- ロガー名は大文字小文字を区別しません（内部的に大文字に変換されます）
- ロガーが存在しない場合、`logging.getLogger(name)` を使用して自動的に作成されます
- 変更はプロセスを再起動せずにすぐに有効
- 変更は永続的ではありません（プロセス再起動後に元の設定に戻ります）

---

## パラメータ

### --pattern - マッチングパターン

`list` アクションで使用されてロガーリストをフィルタリングします。

**サポートされているワイルドカード**:
- `*`: 任意の長さの文字に一致（空文字も含む）
- `?`: 単一文字に一致
- `[seq]`: seq 内の任意の文字に一致
- `[!seq]`: seq 内の文字以外に一致

**例**:
| パターン | 一致するもの | 一致しないもの |
|------|----------|------------|
| `myapp.*` | `myapp.auth`、`myapp.db` | `myapp`、`webapp.auth` |
| `*db*` | `myapp.db`、`database`、`mongodb` | `myapp.cache` |
| `myapp.api.v?` | `myapp.api.v1`、`myapp.api.v2` | `myapp.api.v10` |
| `myapp.[ad]*` | `myapp.auth`、`myapp.db` | `myapp.cache` |

**使用法**:
```bash
# myapp 名前空間のすべてのロガーを一覧表示
peeka-cli logger --action list --pattern "myapp.*"

# データベース関連のすべてのロガーを一覧表示
peeka-cli logger --action list --pattern "*db*"

# すべての API バージョンロガーを一覧表示
peeka-cli logger --action list --pattern "*.api.v?"
```

### --logger - ロガー名

操作するロガーの完全な名前を指定します。

**命名規則**:
- 通常はモジュールパスを使用（`myapp.module.submodule` のように）
- Python の標準的な慣習: `logger = logging.getLogger(__name__)`
- サードパーティライブラリは通常パッケージ名を使用（`urllib3`、`boto3` のように）

**ロガー名を見つける方法**:
```bash
# 方法 1: すべてのロガーを一覧表示してターゲットを見つける
peeka-cli logger --action list | jq -r '.loggers[].name'

# 方法 2: パターンマッチングを使用して範囲を絞る
peeka-cli logger --action list --pattern "myapp.payment*"

# 方法 3: コード内の getLogger 呼び出しを確認
grep -r "getLogger" myapp/ | grep -v ".pyc"
```

### --level - ログレベル

新しいログレベルを指定します（`set` アクションでのみ使用されます）。

**レベル選択の推奨**:
| シナリオ | 推奨レベル | 説明 |
|------|----------|------|
| 本番環境通常操作 | `INFO` | 重要なビジネス情報を記録 |
| 本番環境トラブルシューティング | `DEBUG` | 一時的に詳細なログを有効化 |
| パフォーマンス最適化（ログを減らす） | `WARNING` | 例外的な状況だけを記録 |
| サードパーティライブラリログを無効化 | `ERROR` または `CRITICAL` | 重大なエラーだけを記録 |
| 親ロガー設定を継承 | `NOTSET` | 親ロガーのレベルを使用 |

**レベル継承関係**:
```
root logger (default WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG) ← 自身のレベルを使用
       └─ myapp.db (NOTSET)  ← myapp の INFO を継承
```

---

## 出力フォーマット

### list アクション出力

```json
{
  "status": "success",
  "loggers": [
    {
      "name": "myapp.auth",
      "level": "INFO",
      "level_num": 20
    },
    {
      "name": "myapp.db",
      "level": "DEBUG",
      "level_num": 10
    }
  ],
  "count": 2
}
```

**フィールドの説明**:
- `status`: 操作ステータス (`success` または `error`)
- `loggers`: ロガーリスト（名前でソートされています）
- `name`: 完全なロガー名
- `level`: ログレベル名 (`INFO` のように）
- `level_num`: ログレベルの数値 (`20` のように）
- `count`: マッチしたロガーの数

### get アクション出力

**成功**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**失敗**（ロガーが存在しない）:
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### set アクション出力

**成功**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**失敗**（無効なレベル）:
```json
{
  "status": "error",
  "error": "Invalid level: INVALID. Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL, NOTSET"
}
```

---

## 使用例

### 例 1: すべてのロガー設定を表示

```bash
peeka-cli logger --action list | jq .
```

**出力**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "root", "level": "WARNING", "level_num": 30},
    {"name": "myapp", "level": "INFO", "level_num": 20},
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "urllib3.connectionpool", "level": "WARNING", "level_num": 30}
  ],
  "count": 5
}
```

### 例 2: トラブルシューティングのために一時的に DEBUG ログを有効化

```bash
# 1. 現在のレベルを確認
peeka-cli logger --action get --logger myapp.payment
# 出力: {"status": "success", "name": "myapp.payment", "level": "INFO", ...}

# 2. DEBUG を有効化
peeka-cli logger --action set --logger myapp.payment --level DEBUG
# 出力: {"status": "success", "old_level": "INFO", "new_level": "DEBUG"}

# 3. 別のターミナルでログファイルを監視
tail -f /var/log/myapp.log | grep payment

# 4. トラブルシューティング後に復元
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 例 3: 冗長なサードパーティライブラリログを抑制

```bash
# すべてのサードパーティライブラリロガーで DEBUG レベルのものを表示
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# バッチで無効化（WARNING 以上だけを保持）
for logger in urllib3 botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
done
```

### 例 4: ロガーが存在するか確認

```bash
# 方法 1: get アクションを使用
result=$(peeka-cli logger --action get --logger myapp.missing 2>&1)
echo "$result" | jq -r .status
# 出力: error （存在しない場合）

# 方法 2: すべてを一覧表示して検索
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name == "myapp.missing")'
# 出力がない （存在しない場合）
```

### 例 5: 新しいロガーを作成してレベルを設定

```bash
# set アクションは存在しないロガーを自動作成します
peeka-cli logger --action set --logger myapp.new_module --level DEBUG

# 作成されたことを確認
peeka-cli logger --action get --logger myapp.new_module
# 出力: {"status": "success", "name": "myapp.new_module", "level": "DEBUG", ...}
```

### 例 6: バッチで特定のモジュール設定を表示

```bash
# myapp.api サブモジュールすべてのログレベルを表示
peeka-cli logger --action list --pattern "myapp.api.*" | \
  jq -r '.loggers[] | "\(.name): \(.level)"'
```

**出力**:
```
myapp.api.v1: INFO
myapp.api.v2: DEBUG
myapp.api.auth: WARNING
```

---

## 完全な診断ワークフロー

### ワークフロー 1: 本番環境の問題のトラブルシューティング

**シナリオ**: 本番環境で支払い処理が失敗していて、問題を特定するために一時的にデバッグログを有効にする必要がある。

```bash
# ステップ 1: 支払いモジュールの現在のログレベルを確認
peeka-cli logger --action get --logger myapp.payment
# 出力: {"level": "INFO"}

# ステップ 2: DEBUG ログを有効化
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# ステップ 3: 同時にログファイルを監視
tail -f /var/log/myapp.log | grep -A 5 -B 5 "payment"

# ステップ 4: 問題を再現（支払いフローをトリガ）

# ステップ 5: デバッグログを確認して問題を特定

# ステップ 6: 問題解決後に元のレベルを復元
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### ワークフロー 2: ログ欠落の診断

**シナリオ**: 特定のモジュールのログが完全に欠落していて、原因を確認する必要がある。

```bash
# ステップ 1: ロガーが存在するか確認
peeka-cli logger --action get --logger myapp.analytics
# 出力が "Logger not found" なら、初期化されていません

# ステップ 2: 親ロガーのレベルを確認
peeka-cli logger --action get --logger myapp
# 出力: {"level": "WARNING"}

# ステップ 3: ロガーを作成して DEBUG に設定
peeka-cli logger --action set --logger myapp.analytics --level DEBUG

# ステップ 4: ログが出力され始めたことを確認
tail -f /var/log/myapp.log | grep analytics
```

### ワークフロー 3: パフォーマンス最適化 - ログ I/O を削減

**シナリオ**: システムの負荷が高く、ログ I/O がボトルネックになっていて、一部のログを一時的に無効にする必要がある。

```bash
# ステップ 1: DEBUG レベルのすべてのロガーを表示
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# 出力:
# myapp.api
# myapp.cache
# myapp.db
# myapp.reporting

# ステップ 2: コアモジュール（api, db）は DEBUG のまま、他を無効化
peeka-cli logger --action set --logger myapp.cache --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# ステップ 3: システム負荷の変化を観察
# (top、htop、または監視システムを使用)

# ステップ 4: 必要に応じて復元
peeka-cli logger --action set --logger myapp.cache --level DEBUG
peeka-cli logger --action set --logger myapp.reporting --level DEBUG
```

### ワークフロー 4: バッチでサードパーティライブラリログを調整

**シナリオ**: 複数のサードパーティライブラリが過剰なデバッグログを出力していて、バッチで無効化する必要がある。

```bash
# ステップ 1: アプリケーションでないすべてのロガーを一覧表示
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | .name'

# 出力:
# urllib3
# urllib3.connectionpool
# botocore
# requests

# ステップ 2: バッチで WARNING に設定
cat <<'EOF' | bash
for logger in urllib3 urllib3.connectionpool botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
  echo "Set $logger to WARNING"
done
EOF

# ステップ 3: 確認
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | "\(.name): \(.level)"'
```

---

## 重要な注意点

### 1. 変更は一時的であること

**重要**: logger コマンドの変更は**永続的ではありません**。

- 変更はすぐに有効になりますが、プロセス再起動後に元の設定に戻ります
- 永続的な変更には、設定ファイル（`logging.conf` やコード内の `logging.basicConfig()`）を更新してください

### 2. ルートロガーへの影響

**ルートロガー**はすべてのロガーのデフォルトの親です：
- デフォルトレベルは `WARNING`
- 明示的にレベルを設定されていないすべてのロガーはルートロガーから継承します
- ルートロガーを変更すると、すべての子ロガーに影響します（子ロガーが明示的にレベルを設定していない限り）

**例**:
```bash
# ルートロガーを表示
peeka-cli logger --action get --logger root

# グローバルに DEBUG を有効化（注意して使用してください！）
peeka-cli logger --action set --logger root --level DEBUG
```

**警告**: ルートロガーを変更するとログ爆発が発生する可能性があるので、必要な場合にだけ使用してください。

### 3. ロガー作成タイミング

**注意**: `list` と `get` は**初期化された**ロガーだけを表示します。

- ロガーは `logging.getLogger(name)` が最初に呼び出されたときに作成されます
- コードが関連するモジュールまで実行されていない場合、ロガーはリストに表示されません
- `set` アクションは存在しないロガーを自動作成します

### 4. レベル継承メカニズム

Python ログレベル継承ルール：
```
root (WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG)    ← 自身のレベルを使用
       ├─ myapp.db (NOTSET)     ← myapp の INFO を継承
       └─ myapp.cache (NOTSET)  ← myapp の INFO を継承
```

**実際の有効レベル**:
- `myapp.auth`: DEBUG（自身のレベル）
- `myapp.db`: INFO（myapp から継承）
- `myapp.cache`: INFO（myapp から継承）

### 5. ハンドラへの影響

**注意**: logger コマンドはロガーの**レベル**だけを変更し、ハンドラの設定は変更しません。

- ロガーレベルが DEBUG でも、ハンドラレベルが INFO なら、DEBUG ログは出力されません
- ハンドラ設定を確認するには：`logger.handlers[0].level` をコードで確認する必要があります

### 6. パフォーマンスへの影響

ログレベルを変更すること自体には**パフォーマンスオーバーヘッドはありません**が、ログレベルの変更は以下に影響します：
- **レベルを下げる**（INFO → DEBUG のように）: ログ量が増加し、I/O オーバーヘッドが上昇します
- **レベルを上げる**（DEBUG → WARNING のように）: ログ量が減少し、パフォーマンスが向上します

**推奨**:
- デバッグ後にすぐに元のレベルを復元してください
- 長時間 DEBUG レベルを有効にしたままにすることを避けてください
- 定期的にログファイルサイズを確認してください

---

## FAQ

### Q1: ログレベルを変更した後もログが出力されないのはなぜ？

**考えられる理由**:
1. **ハンドラレベルが高すぎる**: ロガーレベルは DEBUG だが、ハンドラレベルが INFO
2. **ログがフラッシュされていない**: 一部のハンドラはバッファリングがあるので、フラッシュを待つ必要があります
3. **ロガー名が間違っている**: 実際に使用されているロガー名が変更したものと異なる
4. **親ロガーレベルが高すぎる**: 子ロガーが DEBUG でも、親ロガーがフィルタリングする

**診断方法**:
```bash
# 1. ロガーレベルが変更されたことを確認
peeka-cli logger --action get --logger myapp.target

# 2. 親ロガーレベルを確認
peeka-cli logger --action get --logger myapp

# 3. ルートロガーレベルを確認
peeka-cli logger --action get --logger root

# 4. すべてのロガーを表示して名前が正しいことを確認
peeka-cli logger --action list --pattern "myapp.*"
```

### Q2: 複数のロガーをバッチで変更するには？

**方法 1**: シェルループを使用
```bash
for logger in myapp.auth myapp.db myapp.cache; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done
```

**方法 2**: ファイルから読み込み
```bash
# loggers.txt ファイルの内容:
# myapp.auth
# myapp.db
# myapp.cache

while read logger; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done < loggers.txt
```

**方法 3**: 動的クエリからバッチ変更
```bash
# INFO レベルのすべてのロガーを DEBUG に変更
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "INFO") | .name' | \
  while read logger; do
    peeka-cli logger --action set --logger "$logger" --level DEBUG
  done
```

### Q3: 変更は他のプロセスに影響しますか？

**回答**: いいえ。

- 各プロセスは独立したロガー設定を持っています
- 変更は指定された PID プロセスだけに影響します
- 他のプロセスのロガーは影響を受けません

### Q4: すべてのロガーを元の状態に復元するには？

**方法**: プロセスを再起動します（ロガー設定がリロードされます）。

**注意**: logger コマンドは「スナップショットを復元」機能を提供していないので、以下が推奨されます：
1. 変更する前に元のレベルを記録しておく
2. または単純にプロセスを再起動して設定を復元する

**元のレベルを記録する例**:
```bash
# 変更前に現在の設定を保存
peeka-cli logger --action list > logger_backup.json

# 変更後に復元
jq -r '.loggers[] | "\(.name) \(.level)"' logger_backup.json | \
  while read name level; do
    peeka-cli logger --action set --logger "$name" --level "$level"
  done
```

### Q5: パターンマッチングがロガーを見つけないのはなぜ？

**考えられる理由**:
1. **パターン構文エラー**: fnmatch は正規表現をサポートしていなく、`*` と `?` だけをサポートしています
2. **ロガーが初期化されていない**: コードがまだそのモジュールまで実行されていません
3. **大文字小文字の区別**: ロガー名は大文字小文字を区別します

**デバッグ方法**:
```bash
# 1. パターンなしですべてのロガーを一覧表示
peeka-cli logger --action list | jq -r '.loggers[].name'

# 2. ターゲットロガーの正確な名前を確認

# 3. 正しいパターンを使用
peeka-cli logger --action list --pattern "myapp.*"
```

### Q6: 存在しないロガーを作成できますか？

**回答**: はい、`set` アクションを使用します。

```bash
# 新しいロガーを作成してレベルを設定
peeka-cli logger --action set --logger myapp.new_logger --level DEBUG

# 確認
peeka-cli logger --action get --logger myapp.new_logger
# 出力: {"status": "success", "name": "myapp.new_logger", "level": "DEBUG"}
```

**注意**:
- 新しく作成されたロガーはプロセス再起動後に自動的に再作成されません
- アプリケーションコードで明示的に `logging.getLogger(name)` を呼び出す必要があります

---

## 高度なテクニック

### 1. 動的ログレベルトグルスクリプト

**シナリオ**: 頻繁にデバッグログの有効/無効を切り替えるので、自動化スクリプトを作成する。

```bash
#!/bin/bash
# toggle_debug.sh - myapp.payment のログレベルをトグル

PID=12345
LOGGER="myapp.payment"

current=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)

if [ "$current" == "DEBUG" ]; then
  echo "Disabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level INFO
else
  echo "Enabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level DEBUG
fi
```

### 2. ログレベル変更のモニタリング

**シナリオ**: 本番環境で誤って DEBUG が有効になっていないか定期的に確認する。

```bash
#!/bin/bash
# check_debug_loggers.sh - すべての DEBUG レベルロガーを確認

PID=12345

debug_loggers=$(peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name')

if [ -n "$debug_loggers" ]; then
  echo "WARNING: Found DEBUG loggers in production:"
  echo "$debug_loggers"
  # アラートを送信（Slack、メールなど）
else
  echo "All loggers are at safe levels."
fi
```

### 3. Prometheus と統合

**シナリオ**: ロガー設定を Prometheus モニタリングにエクスポートする。

```bash
#!/bin/bash
# export_logger_metrics.sh

PID=12345

peeka-cli logger --action list | \
  jq -r '.loggers[] | "logger_level{name=\"\(.name)\"} \(.level_num)"' \
  > /var/lib/node_exporter/textfile_collector/logger_levels.prom
```

**Prometheus クエリ**:
```promql
# すべての DEBUG レベルロガーをクエリ
logger_level{level="10"}

# 本番環境の DEBUG ロガーを検出するアラートルール
ALERT ProductionDebugLogger
  IF logger_level{name=~"myapp.*", level="10"} > 0
  FOR 5m
  ANNOTATIONS {
    summary = "Production logger at DEBUG level",
    description = "Logger {{ $labels.name }} is at DEBUG level in production."
  }
```

### 4. ログレベル分析

**シナリオ**: アプリケーション内のログレベルの分布をカウントする。

```bash
peeka-cli logger --action list --pattern "myapp.*" | \
  jq -r '.loggers[] | .level' | sort | uniq -c
```

**出力**:
```
     12 DEBUG
     45 INFO
      8 WARNING
```

### 5. 一時的なログリダイレクト

**シナリオ**: 一時的にモジュールのログレベルを調整して、出力を別ファイルにリダイレクトする。

```bash
# 1. DEBUG ログを有効化
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 2. 別のターミナルでログを監視
tail -f /var/log/myapp.log | grep "payment" > payment_debug.log

# 3. 問題を再現

# 4. 監視を停止（Ctrl+C）

# 5. ログレベルを復元
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 6. 自動復元スクリプト

**シナリオ**: DEBUG を有効にした後、5分後に自動的に復元して、無効のまま忘れることを回避する。

```bash
#!/bin/bash
# temp_debug.sh - 一時的に DEBUG を有効にして、5分後に自動復元

PID=$1
LOGGER=$2
DURATION=${3:-300}  # デフォルト 5 分

# 元のレベルを保存
original=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)
echo "Original level: $original"

# DEBUG を有効化
peeka-cli logger --action set --logger $LOGGER --level DEBUG
echo "DEBUG enabled. Will auto-restore in $DURATION seconds..."

# バックグラウンドで待機してから復元
(
  sleep $DURATION
  peeka-cli logger --action set --logger $LOGGER --level $original
  echo "Restored to $original"
) &
```

**使用法**:
```bash
./temp_debug.sh 12345 myapp.payment 300
```

---

## まとめ

`logger` コマンドは本番環境でのログ診断に強力なツールで、特に以下に適しています：
- 問題のトラブルシューティングのために一時的にデバッグログを有効化
- サードパーティライブラリからの冗長なログを抑制
- パフォーマンス最適化のために動的にログレベルを調整
- ログ欠落の問題を診断

**ベストプラクティス**:
- 変更前に元のレベルを記録（復元を容易にするため）
- デバッグ後にすぐに元のレベルを復元
- 長時間の DEBUG レベルを避ける（ログ爆発を防止）
- `--pattern` を使用してロガーをフィルタリング（効率を向上）
- `jq` と組み合わせて強力なデータ分析を行う

**次のステップ**:
- [`watch`](watch.md) コマンドを学ぶ（関数呼び出しをオブザーブ）
- [`stack`](stack.md) コマンドを学ぶ（呼び出しスタックをトレース）
- [`memory`](memory.md) コマンドを学ぶ（メモリ分析）
