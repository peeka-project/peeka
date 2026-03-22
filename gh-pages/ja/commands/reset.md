---
layout: default
title: reset コマンド
parent: コマンドリファレンス
nav_order: 10
---

# reset コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`reset` コマンドは、**拡張されたメソッドを元の状態に回復**するために使用されます。`watch`、`stack` などのコマンドによって注入された観測ロジックを削除します。これはクリーンアップコマンドで、すべての拡張を選択的にリセットしたり、特定のパターンに一致する拡張のみをリセットしたりできます。


## 使用場面

- **診断終了後のクリーンアップ**：障害調査が完了した後、注入されたすべての観測ロジックを削除
- **観測の再設定**：異なるパラメータで再観測する前に、既存の拡張をリセット
- **選択的クリーンアップ**：特定のモジュールまたはクラスの拡張のみを削除し、他の観測を保持
- **現在の状態の確認**：すべてのアクティブな拡張をリストアップし、システム状態を把握
- **性能回復**：観測ロジックを削除して性能オーバーヘッドを除去

## TUI での使用法

**注意**：reset コマンドは TUI で**独立したビューがありません**が、コマンド入力ボックスから実行できます：

- TUI メイン画面で `:` を押してコマンドモードに入る
- `reset` コマンドを入力してリセットを実行

**よく使われる操作**：
- すべての拡張をリストアップ：`: reset --list` または `: reset -l`
- すべての拡張をリセット：`: reset`
- 特定のパターンをリセット：`: reset "myapp.service.*"`

**ショートカット**：各ビューには通常独立した「停止」ボタンがあるので、手動で reset コマンドを入力する必要はありません。

**CLI との同等性**：以下の例はデモンストレーションのために CLI コマンドを使用しています。

## コマンドフォーマット

```bash
peeka-cli reset [pattern] [options]
```

**使用前提**：事前に `peeka-cli attach <pid>` でターゲットプロセスにアタッチする必要があります

### パラメータ説明

| パラメータ           | 説明                    | デフォルト | 例                  |
|--------------|------------------------|-----|---------------------|
| `pattern`    | オプションのマッチングパターン（ワイルドカード対応）      | なし   | `"myapp.service.*"` |
| `-l, --list` | 現在の拡張をリストアップするだけでリセットしない       | -   | `--list`            |

### パターンマッチングルール

`pattern` パラメータは Unix shell スタイルのワイルドカードをサポートしています（fnmatch ベース）：

| ワイルドカード | 意味     | 例                                | マッチ                               |
|-----|--------|-----------------------------------|----------------------------------|
| `*` | 任意の文字にマッチ | `myapp.service.*`                 | `myapp.service.UserService`      |
| `?` | 単一文字にマッチ | `myapp.?.query`                   | `myapp.a.query`, `myapp.b.query` |
| なし   | 完全一致   | `myapp.service.UserService.query` | 完全に同一のパターンのみにマッチ                       |

**注意**：パターンマッチングは**保存されているパターン**に対して行われ、関数名に対してではありません。

## 出力フォーマット

### reset 操作レスポンス

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query"
    },
    {
      "watch_id": "watch_e5f6g7h8",
      "pattern": "myapp.service.UserService.update"
    }
  ],
  "count": 2
}
```

**フィールド説明**：

| フィールド         | 型     | 説明                      |
|------------|--------|-------------------------|
| `status`   | string | 操作状態（`success`/`error`） |
| `action`   | string | 操作タイプ（`reset`）           |
| `affected` | array  | リセットされた拡張のリスト                |
| `count`    | int    | 正常にリセットされた数                 |

**affected 配列の要素**：

| フィールド         | 型     | 説明           |
|------------|--------|--------------|
| `watch_id` | string | 観測セッション ID      |
| `pattern`  | string | 元の関数マッチングパターン    |
| `error`    | string | （オプション）リセット失敗時のエラー |

### list 操作レスポンス

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**フィールド説明**：

| フィールド         | 型     | 説明           |
|------------|--------|--------------|
| `status`   | string | 操作状態         |
| `action`   | string | 操作タイプ（`list`） |
| `enhanced` | array  | 現在の拡張リスト       |
| `total`    | int    | 拡張の合計数         |

**enhanced 配列の要素**：

| フィールド         | 型     | 説明                       |
|------------|--------|--------------------------|
| `watch_id` | string | 観測セッション ID                  |
| `pattern`  | string | 関数マッチングパターン                   |
| `command`  | string | 拡張を作成したコマンド（`watch`/`stack`） |
| `count`    | int    | キャプチャされた観測回数                 |

## 使用例

### 例 1：すべての拡張をリセット

```bash
# すべての拡張をリセット
peeka-cli reset
```

**出力**：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.query"},
    {"watch_id": "watch_002", "pattern": "myapp.handler.process"},
    {"watch_id": "stack_003", "pattern": "myapp.api.handle"}
  ],
  "count": 3
}
```

**用途**：

- 診断終了後の完全なクリーンアップ
- システムを観測なしの状態に回復
- すべての性能オーバーヘッドを除去

### 例 2：パターンによるリセット

```bash
# myapp.service モジュールの拡張のみをリセット
peeka-cli reset "myapp.service.*"

# 特定クラスのすべてのメソッドをリセット
peeka-cli reset "myapp.service.UserService.*"

# 特定メソッドをリセット
peeka-cli reset "myapp.service.UserService.query"
```

**出力**（2 つの拡張にマッチした場合）：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.UserService.query"},
    {"watch_id": "watch_002", "pattern": "myapp.service.UserService.update"}
  ],
  "count": 2
}
```

**用途**：

- 特定モジュールの選択的クリーンアップ
- 他のモジュールの観測を保持
- 特定関数の観測パラメータを再設定

### 例 3：マッチするパターンがない場合

```bash
# パターンがどの拡張にもマッチしない
peeka-cli reset "nonexistent.*"
```

**出力**：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [],
  "count": 0
}
```

### 例 4：現在の拡張をリストアップ

```bash
# すべてのアクティブな拡張を表示
peeka-cli reset --list
```

**出力**：

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**用途**：

- 現在のシステム状態の把握
- 観測がまだアクティブか確認
- リセットが必要な拡張を決定

### 例 5：拡張が空の場合のリストアップ

```bash
# アクティブな拡張がない場合
peeka-cli reset --list
```

**出力**：

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [],
  "total": 0
}
```

### 例 6：jq との併用

```bash
# リセットされた数を抽出
peeka-cli reset | jq '.count'
# 出力: 3

# 影響を受けたパターンのリストを抽出
peeka-cli reset "myapp.*" | jq -r '.affected[].pattern'
# 出力:
# myapp.service.query
# myapp.handler.process

# 現在の拡張数を統計
peeka-cli reset --list | jq '.total'
# 出力: 5

# 特定のコマンドの拡張を表示
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# 観測回数でソート
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## 典型的なワークフロー

### ワークフロー 1：診断後のクリーンアップ

```bash
# 1. 診断を開始
peeka-cli watch "myapp.service.query" -n 100

# 2. 観測データを確認（100 回後に自動停止）
# ... データを分析 ...

# 3. 診断終了、すべての拡張をクリーンアップ
peeka-cli reset

# 検証
peeka-cli reset --list
# 出力: {"total": 0}
```

### ワークフロー 2：観測の再設定

```bash
# 1. 現在深度 2 で観測中
peeka-cli watch "myapp.service.query" -x 2

# 2. より深い出力（深度 3）が必要になった
# 先に現在の観測をリセット
peeka-cli reset "myapp.service.query"

# 3. 新しいパラメータで再観測
peeka-cli watch "myapp.service.query" -x 3
```

### ワークフロー 3：マルチモジュール診断

```bash
# 1. 複数のモジュールを観測
peeka-cli watch "myapp.service.*" &
peeka-cli watch "myapp.handler.*" &
peeka-cli watch "myapp.api.*" &

# 2. service モジュールの診断が完了したので、service だけをクリーンアップ
peeka-cli reset "myapp.service.*"

# 3. 他のモジュールの観測は継続して実行
# handler と api の観測は引き続き実行される

# 4. すべて終了後にクリーンアップ
peeka-cli reset
```

### ワークフロー 4：定期的な状態チェック

```bash
#!/bin/bash
# check_enhancements.sh - 定期的に拡張状態をチェック

while true; do
  TOTAL=$(peeka-cli reset --list | jq '.total')
  echo "$(date): アクティブな拡張の数 = $TOTAL"

  if [ "$TOTAL" -gt 10 ]; then
    echo "警告：拡張の数が多すぎます。クリーンアップを検討してください"
  fi

  sleep 300  # 5 分ごとにチェック
done
```

## 注意点

### ⚠️ Monitor コマンドは影響を受けない

`reset` コマンドは**`watch` と `stack` コマンドによって作成された拡張のみに影響**します。`monitor` コマンドは独立した追跡メカニズムを使用しているため、reset でクリーンアップされません。

```bash
# monitor は影響を受けない
peeka-cli monitor "myapp.service.query"  # 監視を開始

peeka-cli reset                        # リセットしても monitor は停止しない

# monitor を停止するには個別に処理が必要
peeka-cli reset "myapp.service.*"
```

### ⚠️ パターンマッチングルール

パターンは**保存されているパターン**に対してマッチングされ、関数名に対してではありません：

```bash
# 仮に事前に以下を実行したとする：
peeka-cli watch "myapp.service.UserService.query"

# ✅ 正しい：保存されたパターンにマッチ
peeka-cli reset "myapp.service.*"              # マッチ成功
peeka-cli reset "myapp.service.UserService.*"  # マッチ成功

# ❌ 誤り：クラス名でマッチングしようとしても機能しない
peeka-cli reset "UserService.*"                # マッチしない
```

### ⚠️ リセットは取り消しできない

リセット操作は直ちに拡張ロジックを削除するため、**取り消しができません**。引き続き観測が必要な場合は、`watch` または `stack` コマンドを再度実行する必要があります。

```bash
# リセット後は再観測が必要
peeka-cli reset "myapp.service.query"
peeka-cli watch "myapp.service.query" -n 100  # 再度観測を開始
```

### ⚠️ 性能回復

リセット後、関数は元の状態に回復し、性能オーバーヘッドは直ちに消滅します：

| 状態        | 性能オーバーヘッド |
|-----------|------|
| 拡張前       | 0%   |
| watch 観測中 | 2-5% |
| リセット後       | 0%   |

### ⚠️ 並行セーフティ

reset コマンドはスレッドセーフですが、高並行シナリオではエッジケースが発生する可能性があります：

- リセット中に、進行中の観測は引き続きデータを生成する可能性がある
- リセット後に直ちに行われる呼び出しは元の関数を使用する

## よくある質問

### Q1: reset とストリーミング観測の停止の違いは何ですか？

**A**:

- `reset`：関数に注入されたデコレータを削除し、拡張ロジックを永久に削除する
- `Ctrl+C`（または CLI を閉じる）：クライアントのストリーミング受信を停止するが、拡張ロジックは引き続きターゲットプロセス内で実行される

**タイミング説明**：

```
Ctrl+C でストリーミングクライアントを停止：観測データの返却は停止するが、拡張は実行を継続
reset で拡張を削除：ターゲットプロセス内のデコレータを削除し、元の関数に完全に回復
```

**推奨される使用法**：

- 一時的な観測の一時停止：`Ctrl+C` を使用（クライアント接続を切断するだけ）
- 徹底的なクリーンアップ：`reset` コマンドを使用（注入されたロジックを削除）
- 今後観測しない関数：先に `reset`、次に他の診断を開始

```bash
# 方法 1：一時停止（クライアント切断）
# Ctrl+C

# 方法 2：徹底クリーンアップ（拡張を削除）
peeka-cli reset "myapp.service.*"
```

### Q2: 特定の watch_id をリセットするには？

**A**: reset は直接 watch_id パラメータをサポートしていませんが、正確なパターンマッチングで実現できます：

```bash
# 1. watch_id に対応するパターンを確認
peeka-cli reset --list | jq '.enhanced[] | select(.watch_id == "watch_001")'
# 出力: {"watch_id": "watch_001", "pattern": "myapp.service.query", ...}

# 2. 正確なパターンでリセット
peeka-cli reset "myapp.service.query"
```

**または直接 watch stop**：

```bash
peeka-cli reset "watch_001"
```

### Q3: reset は実行中の関数に影響しますか？

**A**: 影響しません。reset は関数参照を置き換えるだけで、実行中の呼び出しを中断しません。

**タイミング説明**：

```
時刻 T0: 関数 A が実行を開始（拡張バージョンを使用）
時刻 T1: reset を実行（関数参照を置き換え）
時刻 T2: 関数 A は実行を継続（拡張バージョンに入っているので継続）
時刻 T3: 関数 A が終了（観測データを生成）
時刻 T4: 新しい関数 A の呼び出し（元のバージョンを使用）
```

### Q4: パターンがどの拡張にもマッチしないのはエラーですか？

**A**: エラーではなく、`count: 0` を返します。

```bash
peeka-cli reset "nonexistent.*"
# 出力: {"status": "success", "count": 0}
```

これは予期された動作であり、スクリプトでの使用に便利です（マッチしなくてもエラーにならない）。

### Q5: すべての watch をリセットして stack を保持するには？

**A**: 現在のバージョンではコマンドタイプでフィルタリングすることはサポートされていませんが、パターンマッチングで間接的に実現できます：

```bash
# watch と stack が異なるモジュールを使用している場合
peeka-cli reset "myapp.service.*"  # 仮に watch だけがこのモジュールを観測しているとする
```

**将来の計画**：`--command watch` パラメータでフィルタリングすることをサポートする予定です。

### Q6: reset --list の出力が多すぎる場合は？

**A**: jq でフィルタリングできます：

```bash
# watch コマンドの拡張だけを表示
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# 特定のモジュールの拡張だけを表示
peeka-cli reset --list | jq '.enhanced[] | select(.pattern | startswith("myapp.service"))'

# 観測回数でソート
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## 高度なテクニック

### テクニック 1：自動クリーンアップスクリプト

```bash
#!/bin/bash
# auto_cleanup.sh - 診断終了後に自動クリーンアップ

PID=$1
PATTERN=${2:-"*"}  # デフォルトですべてをクリーンアップ

# 診断を実行
peeka-cli watch "$PATTERN" -n 100

# 完了を待機（100 回後に自動停止）
sleep 5

# 自動クリーンアップ
peeka-cli reset "$PATTERN"
echo "$PATTERN の拡張をクリーンアップしました"
```

### テクニック 2：拡張状態監視

```bash
#!/bin/bash
# monitor_enhancements.sh - 拡張状態を監視

while true; do
  LIST=$(peeka-cli reset --list)
  TOTAL=$(echo "$LIST" | jq '.total')

  echo "$(date): アクティブな拡張: $TOTAL"

  if [ "$TOTAL" -gt 0 ]; then
    echo "$LIST" | jq -r '.enhanced[] | "\(.pattern): \(.count) 回観測"'
  fi

  sleep 60
done
```

### テクニック 3：選択的バッチリセット

```bash
# 複数の特定モジュールをリセット
for module in service handler api; do
  echo "myapp.$module をリセットしています"
  peeka-cli reset "myapp.$module.*"
done
```

### テクニック 4：条件付きクリーンアップ

```bash
# 観測回数が 1000 を超える拡張のみをリセット
peeka-cli reset --list | \
  jq -r '.enhanced[] | select(.count > 1000) | .pattern' | \
  while read pattern; do
    peeka-cli reset "$pattern"
  done
```

### テクニック 5：拡張状態の出力

```bash
# 現在の拡張状態をファイルに出力（復元用）
peeka-cli reset --list > enhancements_backup.json

# 履歴データを分析
jq '.enhanced[] | {pattern, count}' enhancements_backup.json
```

## ベストプラクティス

### ✅ 推奨

1. **診断前に状態を記録**
   ```bash
   peeka-cli reset --list > before.json
   ```

2. **パターンマッチングでモジュールレベルのクリーンアップを使用**
   ```bash
   peeka-cli reset "myapp.service.*"  # モジュール全体をクリーンアップ
   ```

3. **診断終了後は直ちにクリーンアップ**
   ```bash
   peeka-cli watch "func" -n 100  # 100 回観測
   peeka-cli reset             # 直ちにクリーンアップ
   ```

4. **定期的に拡張状態を確認**
   ```bash
   peeka-cli reset --list | jq '.total'
   ```

5. **jq で出力を処理**
   ```bash
   peeka-cli reset | jq -r '.affected[].pattern'
   ```

### ❌ 避けるべきこと

1. **長期的に拡張を保持してクリーンアップしない**
    - 性能オーバーヘッドが持続する
    - メモリ占有が増加する
    - ビジネスに影響を与える可能性がある

2. **monitor のリセットを忘れる**
   ```bash
   # ❌ reset は monitor を停止しない
   peeka-cli reset

   # ✅ monitor も個別に停止する必要がある
   peeka-cli reset "myapp.service.*"
   ```

3. **過度に正確なパターンを使用**
   ```bash
   # ❌ 一つずつリセット（効率が悪い）
   peeka-cli reset "myapp.service.func1"
   peeka-cli reset "myapp.service.func2"

   # ✅ ワイルドカードを使用（効率が良い）
   peeka-cli reset "myapp.service.*"
   ```

4. **リセット結果を確認しない**
   ```bash
   # ❌ リセットが成功したと仮定する
   peeka-cli reset "pattern"

   # ✅ 結果を検証
   RESULT=$(peeka-cli reset "pattern")
   echo "$RESULT" | jq '.count'
   ```

## 関連コマンド

- [`watch`](watch.md) - 関数呼び出しの観測
- [`stack`](stack.md) - 関数呼び出しスタックの追跡
- [`monitor`](monitor.md) - 性能統計監視

## 更新履歴

| バージョン    | 日付         | 更新内容                    |
|-------|------------|-------------------------|
| 0.1.0 | 2025-01-31 | 初期バージョン、reset と list 機能をサポート |
