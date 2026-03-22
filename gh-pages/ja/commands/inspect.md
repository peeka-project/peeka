---
layout: default
title: inspect コマンド
parent: コマンドリファレンス
nav_order: 8
permalink: /commands/inspect
---

# inspect コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 概要

`inspect` コマンドは**実行時オブジェクト検査**機能を提供し、コードを変更することなく実行中の Python プロセス内のオブジェクトの状態を表示できます。3つの操作をサポートしています：

| 操作 | 機能 | 一般的な使用法 |
|-----------|----------|-------------|
| **get** | モジュール/クラスの属性値を取得 | 設定、定数、状態変数を表示 |
| **instances** | 型のインスタンスを検索 | メモリリークのトラブルシューティング、オブジェクト追跡 |
| **count** | インスタンス数をカウント | 素早くオブジェクト数を評価 |


---

## TUI での使用法

TUI モードでは、**`8`** キーを押して **Inspect ビュー** に切り替えると、以下のインタラクティブ機能が利用できます：

- **操作選択**: get/instances/count 操作を視覚的に切り替え
- **get 操作**: モジュール/クラスの属性値を取得
  - ターゲットパスを入力（例: `sys.version`、`module.attr`）
  - 出力深度を設定
  - 属性値と型情報を表示
- **instances 操作**: 型のインスタンスを検索
  - クラス名を入力（例: `myapp.User`）
  - 結果数制限とフィルタ式を設定
  - インスタンスリストと属性を表示
  - `--gc-first` をサポート（実行前に GC）
- **count 操作**: インスタンス数をカウント
  - クラス名を入力（例: `list`、`dict`）
  - 素早くインスタンス数をカウント
- **クイック操作**:
  - パラメータ入力後に Enter を押して実行
  - `c` を押して結果をクリア

**CLI との同等性**: 以下の例はデモンストレーションのために CLI コマンドを使用しています。TUI はグラフィカルインターフェースで同じ機能を提供します。

## 使用場面

### 1. 設定の確認

プロセスを再起動することなく、本番環境で実行時の設定値を確認：

```bash
peeka inspect --action get --target "app.config.DEBUG"
```

### 2. メモリリークのトラブルシューティング

解放されていないオブジェクトを確認するために、特定の型のすべてのインスタンスを検索：

```bash
peeka inspect --action instances --type myapp.User --limit 10
```

### 3. オブジェクト統計

メモリ使用量を評価するために、素早く型のオブジェクトをカウント：

```bash
peeka inspect --action count --type list
```

### 4. 状態診断

アプリケーションの動作を診断するために実行時の状態変数を表示：

```bash
peeka inspect --action get --target "sys.path"
```

---

## コマンドフォーマット

```bash
peeka inspect --action <action> [options]
```

### 基本パラメータ

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|-------------|----------|---------|
| `-p, --pid` | ターゲットプロセス PID | はい | - |
| `--action` | 操作タイプ | いいえ | `get` |

### action 操作タイプ

| 操作 | 説明 | 必須パラメータ |
|--------|-------------|---------------------|
| **get** | 属性値を取得 | `--target` |
| **instances** | インスタンスを検索 | `--type` |
| **count** | インスタンスをカウント | `--type` |

---

## パラメータの説明

### get 操作パラメータ

| パラメータ | 説明 | 例 |
|-----------|-------------|---------|
| `--target` | ターゲットパス（ドット区切り） | `sys.version` |
| `--depth` | 出力のネスト深度 | `--depth 3` |

**target 解決ルール**:

- 最初のセグメントは `sys.modules` 内のモジュールでなければなりません
- 後続のセグメントは `getattr()` チェーンで検索されます
- 辞書キールックアップは**サポートされていません**（例: `config["debug"]`）

例：

- `sys.version` → `getattr(sys.modules["sys"], "version")`
- `myapp.Config.DEBUG` → `getattr(getattr(sys.modules["myapp"], "Config"), "DEBUG")`

### instances 操作パラメータ

| パラメータ | 説明 | デフォルト | 範囲 |
|-----------|-------------|---------|-------|
| `--type` | 型名 | - | 必須 |
| `--limit` | 結果数制限 | `10` | 1-1000 |
| `--depth` | 出力のネスト深度 | `2` | 0-10 |
| `--filter-express` | フィルタ式 | None | SimpleEval 構文 |
| `--gc-first` | スキャン前に GC を実行 | `False` | - |

**type 解決ルール**:

- ビルトイン型: `str`、`int`、`list`、`dict`、`set`、`tuple`、`bytes`、`bool`、`float`
- カスタム型: `module.ClassName`（モジュールがロードされている必要があります）
- 動的モジュールインポートは**サポートされていません**

### count 操作パラメータ

| パラメータ | 説明 | デフォルト |
|-----------|-------------|---------|
| `--type` | 型名 | - |
| `--filter-express` | フィルタ式 | None |
| `--gc-first` | スキャン前に GC を実行 | `False` |

**特別な注意**: `count` 操作は**すべてのオブジェクトを走査**します（制限なし）。オブジェクトを保存せずにカウントだけを行うので、メモリオーバーヘッドは最小限です。

### フィルタ式

フィルタ式は **SimpleEval** の安全な評価器を使用し、以下の構文をサポートしています：

| 構文 | 説明 | 例 |
|--------|-------------|---------|
| `obj.*` | オブジェクト属性 | `obj.value` |
| 比較 | `>`、`<`、`==`、`!=` | `obj.age > 18` |
| 論理 | `and`、`or`、`not` | `obj.active and obj.age > 18` |
| 算術 | `+`、`-`、`*`、`/` | `obj.score * 2 > 100` |
| 関数 | `len()`、`str()`、`int()`、`bool()` | `len(obj.items) > 0` |

**安全制限**:

- ❌ 禁止: `eval()`、`exec()`、`compile()`
- ❌ 禁止: `__import__`、`open()`、`__class__`
- ❌ 禁止: プライベート属性へのアクセス（`__*__`）

**エラー処理**:

- 構文エラー: **コマンド全体が失敗**します
- 実行時エラー（例: 属性が存在しない）: **そのオブジェクトをスキップ**します

---

## 出力フォーマット

### get レスポンス

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.version",
  "type": "str",
  "value": "3.14.2 (main, Jan  1 2026, 10:00:00) [GCC 11.4.0]"
}
```

| フィールド | 説明 |
|-------|-------------|
| `status` | ステータス: `success` または `error` |
| `action` | 操作タイプ |
| `target` | クエリされたターゲットパス |
| `type` | 値の型名 |
| `value` | 属性値（深度制限付き） |

### instances レスポンス

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "list",
  "count": 5,
  "limit": 10,
  "truncated": false,
  "instances": [
    {
      "type": "list",
      "value": [
        1,
        2,
        3
      ]
    },
    {
      "type": "list",
      "value": [
        "a",
        "b"
      ]
    }
  ]
}
```

| フィールド | 説明 |
|-------|-------------|
| `class_name` | クエリされた型 |
| `count` | 返されたインスタンスの数（`== len(instances)`） |
| `limit` | 要求された制限 |
| `truncated` | さらにインスタンスが存在するか (`true`/`false`) |
| `instances` | インスタンス配列（深度制限付き） |

**truncated 意味**:

- `true`: ヒープ内にさらに一致するインスタンスが存在（数は不明）
- `false`: GC トラッキングされているすべての一致するオブジェクトが返された

### count レスポンス

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

| フィールド | 説明 |
|-------|-------------|
| `class_name` | クエリされた型 |
| `count` | GC トラッキングされている合計インスタンス数 |

### error レスポンス

```json
{
  "status": "error",
  "action": "get",
  "error": "Cannot resolve target: Module 'nonexistent' not loaded in target process"
}
```

---

## 使用例

### 例 1: システム情報を表示

```bash
# Python バージョンを表示
peeka inspect --action get --target "sys.version"

# sys.path を表示
peeka inspect --action get --target "sys.path" --depth 3
```

**出力**:

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.path",
  "type": "list",
  "value": [
    "/usr/lib/python3.14",
    "/home/user/project",
    "... (truncated)"
  ]
}
```

### 例 2: 設定値を表示

```bash
# アプリケーション設定を表示
peeka inspect --action get --target "myapp.config.DEBUG"

# クラス定数を表示
peeka inspect --action get --target "myapp.Database.POOL_SIZE"
```

### 例 3: メモリリークのトラブルシューティング

```bash
# すべての User インスタンスを検索
peeka inspect --action instances --type myapp.User --limit 20

# アクティブなユーザーをフィルタ
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.active == True" --limit 10

# 大きなオブジェクトをフィルタ
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 5
```

**出力**:

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "myapp.User",
  "count": 20,
  "limit": 20,
  "truncated": true,
  "instances": [
    {
      "type": "myapp.User",
      "value": "<User(id=1, name='Alice', active=True)>"
    }
  ]
}
```

### 例 4: オブジェクト統計

```bash
# すべての list インスタンスをカウント
peeka inspect --action count --type list

# dict インスタンスをカウント
peeka inspect --action count --type dict

# 特定の条件でオブジェクトをカウント
peeka inspect --action count --type myapp.Connection \
  --filter-express "obj.closed == False"
```

**出力**:

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

### 例 5: jq との組み合わせ

```bash
# value フィールドを抽出
peeka inspect --action get --target "sys.version" | jq -r '.value'

# インスタンス数を取得
peeka inspect --action count --type list | jq '.count'

# 整形表示
peeka inspect --action instances --type dict --limit 3 | jq .
```

---

## 完全な診断ワークフロー

### シナリオ: メモリリークのトラブルシューティング

**問題**: 本番環境のメモリが継続的に成長していて、クラスインスタンスが解放されていないことが疑われます。

**ステップ 1: オブジェクトをカウント**

```bash
# 疑わしい型を定期的にカウント
peeka inspect --action count --type myapp.Cache
# 出力: {"count": 1500}

# 5分後に再度カウント
peeka inspect --action count --type myapp.Cache
# 出力: {"count": 1800}  ← 継続的に成長している！
```

**ステップ 2: インスタンスサンプルを表示**

```bash
# 最初の 10 個のインスタンスを取得
peeka inspect --action instances --type myapp.Cache --limit 10 | jq .

# 大きなオブジェクトを表示
peeka inspect --action instances --type myapp.Cache \
  --filter-express "len(obj.data) > 1000" --limit 5
```

**ステップ 3: 設定を確認**

```bash
# キャッシュ設定を表示
peeka inspect --action get --target "myapp.cache_config.MAX_SIZE"
# MAX_SIZE が効いていないことが発覚！
```

**ステップ 4: 修正を確認**

コードを修正して再デプロイした後、再度カウント：

```bash
peeka inspect --action count --type myapp.Cache
# 出力: {"count": 100}  ← 正常に戻った
```

---

## 重要な注意点

### ⚠️ GC トラッキングされるオブジェクトの制限

`gc.get_objects()` **は GC トラッキングされるオブジェクトだけを返します**:

| 型 | トラッキングされる | instances/count 結果 |
|------|---------|------------------------|
| `list`、`dict`、`set`、`tuple` | ✅ はい | 信頼できる |
| カスタムクラスインスタンス | ✅ はい | 信頼できる |
| `str`、`int`、`float`、`bytes` | ❌ いいえ | 0 または不完全になる可能性がある |

**推奨**:

- メモリリークのトラブルシューティング: **コンテナ型** または **カスタムクラス** を優先
- 文字列/整数のカウント: 結果は**信頼できない**ので、参考だけにしてください

### ⚠️ ターゲット解決ルール

`--target` パラメータは `getattr()` チェーンを使用し、**辞書キーはサポートされていません**:

```bash
# ❌ 間違い: 辞書キー構文はサポートされていません
peeka inspect --action get --target 'config["debug"]'

# ✅ 正しい: まず辞書を取得して、手動で表示
peeka inspect --action get --target "config" | jq '.value.debug'
```

### ⚠️ モジュールロードの制限

`--type` パラメータは**動的にモジュールをインポートしません**:

```bash
# ❌ 間違い: myapp がロードされていないとクエリは失敗します
peeka inspect --action instances --type myapp.User

# ✅ 正しい: ターゲットプロセスが myapp モジュールをインポートしていることを確認
# (ターゲットコードに import myapp が必要です)
```

### ⚠️ パフォーマンスへの影響

| 操作 | ヒープ走査 | パフォーマンスへの影響 |
|-----------|----------------|-------------------|
| `get` | ❌ いいえ | 非常に低い (< 1ms) |
| `instances` | ✅ 部分的（制限まで） | 中程度 (10-100ms) |
| `count` | ✅ 全体 | 高い (50-500ms) |

**推奨**:

- `count` 操作はメモリの大きいプロセスでは時間がかかることがあります
- 本番環境では注意して使用し、頻繁な呼び出しを避けてください

### ⚠️ フィルタ式のセキュリティ

フィルタ式は **SimpleEval** を使用してコードインジェクションを防止しています：

```bash
# ✅ 安全: SimpleEval で許可されている操作
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active"

# ❌ 禁止: コードインジェクション攻撃
peeka inspect --action instances --type myapp.User \
  --filter-express "__import__('os').system('rm -rf /')"
# エラー: Invalid filter expression: __import__ not allowed
```

---

## よくある問題

### Q1: instances が count: 0 を返すが、オブジェクトが確実に存在する

**A**: 考えられる理由:

1. **オブジェクトが GC トラッキングされていない**（`str`、`int` のような場合）
   ```bash
   # str/int は信頼できない可能性がある
   peeka inspect --action count --type str  # 0 になる可能性がある

   # 代わりにコンテナ型を使用
   peeka inspect --action count --type list  # 信頼できる
   ```

2. **モジュールがロードされていない**
   ```bash
   # ロードされているモジュールを確認
   peeka inspect --action get --target "sys.modules.keys()" | grep myapp
   ```

3. **filter-express がすべてのオブジェクトをフィルタアウトした**
   ```bash
   # まずフィルタなしでテスト
   peeka inspect --action instances --type myapp.User --limit 5
   ```

### Q2: target クエリが "Module not loaded" で失敗

**A**: ターゲットモジュールがプロセスにインポートされていません。

**解決策**:

```bash
# ロードされているモジュールを確認
peeka inspect --action get --target "list(sys.modules.keys())" | grep myapp

# モジュールがロードされていない場合、ターゲットコードにインポートを追加してください
```

### Q3: filter-express 構文エラー

**A**: SimpleEval は限られた構文だけをサポートしています。

**よくあるエラー**:

```bash
# ❌ リスト内包表記はサポートされていません
--filter-express "[x for x in obj.items]"

# ✅ len() を代わりに使用
--filter-express "len(obj.items) > 0"

# ❌ 辞書キー構文はサポートされていません
--filter-express "obj['key'] > 0"

# ✅ 属性構文を使用
--filter-express "obj.key > 0"
```

### Q4: count 操作が非常に遅い

**A**: `count` はヒープ全体を走査するので、オブジェクトが多いと遅くなります。

**最適化の提案**:

```bash
# 代わりに instances を使用（制限がある）
peeka inspect --action instances --type list --limit 10

# またはオフピーク時に count を実行
```

### Q5: instances の truncated が常に true

**A**: 一致するオブジェクトが `limit` を超えています。

**解決策**:

```bash
# 制限を増やす（最大 1000）
peeka inspect --action instances --type list --limit 1000

# またはフィルタを使用して範囲を絞る
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 10
```

---

## 高度なヒント

### ヒント 1: 定期的にオブジェクト数をモニタリング

```bash
#!/bin/bash
# monitor_objects.sh - オブジェクト数の変化をモニタリング

PID=12345
TYPE="myapp.Connection"

while true; do
  COUNT=$(peeka inspect --action count --type $TYPE | jq '.count')
  echo "$(date): $TYPE count = $COUNT"
  sleep 60
done
```

### ヒント 2: get と instances を組み合わせる

```bash
# まず設定をクエリ
CONFIG=$(peeka inspect --action get --target "myapp.config.MAX_CONNECTIONS" | jq '.value')

# 次に実際の接続をカウント
ACTUAL=$(peeka inspect --action count --type myapp.Connection | jq '.count')

# 比較
echo "Config: $CONFIG, Actual: $ACTUAL"
```

### ヒント 3: 正確なカウントのために gc-first を使用

```bash
# GC 前
peeka inspect --action count --type myapp.Cache
# 出力: {"count": 1500}

# 強制 GC 後
peeka inspect --action count --type myapp.Cache --gc-first
# 出力: {"count": 1200}  ← 参照されていないオブジェクトがクリーンアップされた
```

### ヒント 4: 複雑なフィルタ式

```bash
# 複数条件フィルタ
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active and len(obj.name) > 0" \
  --limit 10

# 算術演算
peeka inspect --action instances --type myapp.Score \
  --filter-express "obj.math + obj.english > 180" \
  --limit 5
```

### ヒント 5: 分析のためにエクスポート

```bash
# インスタンスをファイルにエクスポート
peeka inspect --action instances --type myapp.User --limit 100 > users.json

# オフライン分析
jq '.instances | map(.value.age) | add / length' users.json  # 平均年齢
jq '.instances | map(select(.value.active == true)) | length' users.json  # アクティブなユーザー
```

---

## まとめ

### コア機能

| 操作 | 目的 | パフォーマンス | ヒープ走査 |
|-----------|---------|-------------|----------------|
| **get** | 属性/設定を表示 | 非常に速い | ❌ |
| **instances** | メモリトラブルシューティング | 中程度 | 部分的 |
| **count** | オブジェクト統計 | より遅い | 全体 |

### 典型的なワークフロー

1. **クイックチェック**: `get` で設定と状態を表示
2. **量の評価**: `count` でオブジェクトをカウント
3. **詳細分析**: `instances` でインスタンスサンプルを取得
4. **フィルタ絞り込み**: `--filter-express` で範囲を絞る

### ベストプラクティス

✅ **推奨**:

- インスタンス/カウントにはコンテナ型（list, dict）を使用
- jq と組み合わせて JSON 出力を処理
- 重要なオブジェクト数を定期的にモニタリング
- フィルタ式を使用して問題を正確に特定

❌ **避けるべきこと**:

- 頻繁な count 実行（パフォーマンスに影響）
- str/int で instances/count を使用（信頼できない）
- フィルタ式で複雑なロジックを使用
- モジュールがロードされているか確認するのを忘れる

### 関連コマンド

- `memory` - メモリ分析とトラッキング
- `sc` - クラスを検索
- `sm` - メソッドを検索
