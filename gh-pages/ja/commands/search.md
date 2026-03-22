---
layout: default
title: search コマンド（sc / sm）
parent: コマンドリファレンス
nav_order: 9
---

# search コマンド（sc / sm）
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## コマンドの概要

`sc` (Search Class) と `sm` (Search Method) コマンドは、実行中の Python プロセス内でクラスとメソッドを検索するために使用されます。開発者がコード構造を迅速に理解し、利用可能な API を発見し、目標関数を特定するのを支援します。

**コア機能**：
- **sc**：ロード済みモジュール内のクラスを検索
- **sm**：クラス内のメソッドを検索
- ワイルドカードパターンマッチングをサポート（`*`, `?`）
- クラス/メソッドの詳細情報を表示（ファイルパス、ドキュメント文字列など）
- 結果数制限（出力過多を回避）
- コード探索と動的分析に適している

**典型的な使用場面**：
- 未知のコードベースの探索（どのようなクラスとメソッドがあるかを発見）
- 特定の機能の実装の検索（例：すべての `*Handler` クラスを検索）
- 関数シグネチャの取得（`watch`、`stack` などのコマンドで使用するため）
- モジュールがロードされているか検証
- サードパーティライブラリ API の学習

## TUI での使用法

**注意**：search コマンド（sc/sm）は TUI で**独立したビューがありません**が、コマンド入力ボックスから実行できます：

- TUI メイン画面で `:` を押してコマンドモードに入る
- `sc <pattern>` または `sm <class_pattern>` を入力して検索を実行
- 結果はコマンド出力領域に表示される

**ショートカット操作**：
- sc コマンド：`: sc "myapp.*" -d --limit 20`
- sm コマンド：`: sm "myapp.User" --method-pattern "get*"`

**CLI の使用を推奨**：search コマンドは主にコード探索に使用されるため、パイプ操作と結果フィルタリングのために CLI モードの使用を推奨します。

**CLI との同等性**：以下の例はデモンストレーションのために CLI コマンドを使用しています。

---

## 使用場面

### 1. 未知のコードベースの探索

**シナリオ**：新しいプロジェクトを引き継ぎ、コード構造を迅速に理解する必要がある。

```bash
# アプリケーションのすべてのクラスを表示（モジュール名が myapp と仮定）
peeka-cli sc "myapp.*"

# 出力：
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.models.User
# myapp.models.Order
# myapp.utils.Helper
```

**用途**：プロジェクトにどのようなモジュールとクラスがあるかを迅速に把握できます。

### 2. 特定の機能の検索

**シナリオ**：すべてのハンドラクラス（Handler）を見つける必要がある。

```bash
# Handler で終わるすべてのクラスを検索
peeka-cli sc "*Handler"

# 出力：
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.api.PaymentHandler
```

### 3. メソッドシグネチャの取得

**シナリオ**：`watch` コマンドでメソッドを監視したいが、完全なシグネチャがわからない。

```bash
# ステップ 1：クラスを検索
peeka-cli sc "myapp.api.UserHandler"

# ステップ 2：クラスのすべてのメソッドを検索
peeka-cli sm "myapp.api.UserHandler.*"

# 出力：
# get (self, user_id: int) -> dict
# create (self, **data) -> dict
# update (self, user_id: int, **data) -> bool
# delete (self, user_id: int) -> bool

# ステップ 3：watch で監視
peeka-cli watch "myapp.api.UserHandler.get"
```

### 4. モジュールがロードされているか検証

**シナリオ**：特定のモジュールがロードされていないために機能が利用できないのではと疑っている。

```bash
# 目標モジュールのクラスを検索
peeka-cli sc "myapp.plugins.payment.*"

# 出力が空なら、モジュールはロードされていない
# 出力があれば、モジュールはロードされている
```

### 5. サードパーティライブラリ API の学習

**シナリオ**：`requests` ライブラリにどのようなクラスとメソッドがあるかを知りたい。

```bash
# requests モジュールのすべてのクラスを表示
peeka-cli sc "requests.*" -d

# Session クラスのすべてのメソッドを表示
peeka-cli sm "requests.Session.*"

# 出力：
# get (self, url, **kwargs) -> Response
# post (self, url, data=None, json=None, **kwargs) -> Response
# put (self, url, data=None, **kwargs) -> Response
# ...
```

---

## コマンドフォーマット

### sc - クラスの検索

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach <pid>

# 次に sc コマンドを実行
peeka-cli sc <pattern> [options]
```

**必須パラメータ**：
- `pattern`：クラスパターン（ワイルドカード対応）

**オプションパラメータ**：
- `-d, --detail`：詳細情報を表示（ファイルパス、ドキュメント文字列）
- `--limit`：結果数制限（デフォルト 50）

### sm - メソッドの検索

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach <pid>

# 次に sm コマンドを実行
peeka-cli sm <class_pattern> [options]
```

**必須パラメータ**：
- `class_pattern`：クラスパターン（ワイルドカード対応）

**オプションパラメータ**：
- `--method-pattern`：メソッドパターン（デフォルト `*`、すべてのメソッドにマッチ）
- `-d, --detail`：詳細情報を表示（モジュール、ドキュメント文字列）

---

## sc コマンド - クラスの検索

### 基本的な使い方

```bash
# 特定のクラスを検索
peeka-cli sc "myapp.User"

# モジュール配下のすべてのクラスを検索
peeka-cli sc "myapp.models.*"

# Handler で終わるすべてのクラスを検索
peeka-cli sc "*Handler"

# 詳細情報を表示
peeka-cli sc "myapp.models.*" -d
```

### 出力フィールド

**基本モード**（`-d` なし）：
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"}
  ],
  "count": 2,
  "limit": 50
}
```

**詳細モード**（`-d` あり）：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model class representing a system user."
    }
  ],
  "count": 1,
  "limit": 50
}
```

### パターン例

| パターン | マッチ例 | 説明 |
|---------|----------|------|
| `json.*` | `json.JSONEncoder`, `json.JSONDecoder` | json モジュール配下のすべてのクラス |
| `myapp.models.*` | `myapp.models.User`, `myapp.models.Order` | myapp.models モジュール配下のすべてのクラス |
| `*Handler` | `UserHandler`, `OrderHandler` | Handler で終わるすべてのクラス |
| `*Command` | `WatchCommand`, `StackCommand` | Command で終わるすべてのクラス |
| `collections.Ordered*` | `collections.OrderedDict` | collections モジュールで Ordered で始まるクラス |

---

## sm コマンド - メソッドの検索

### 基本的な使い方

```bash
# クラスのすべてのメソッドを検索
peeka-cli sm "myapp.User.*"

# 同等の書き方（--method-pattern を使用）
peeka-cli sm "myapp.User" --method-pattern "*"

# 特定のメソッドを検索
peeka-cli sm "myapp.User.get"

# get_ で始まるすべてのメソッドを検索
peeka-cli sm "myapp.User" --method-pattern "get_*"

# 詳細情報を表示
peeka-cli sm "myapp.User.*" -d
```

### 出力フィールド

**基本モード**（`-d` なし）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    }
  ],
  "count": 2,
  "limit": 50
}
```

**詳細モード**（`-d` あり）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### パターン組み合わせ例

| クラスパターン | メソッドパターン | マッチ例 |
|---------------|----------------|----------|
| `myapp.User` | `*` | User クラスのすべてのメソッド |
| `myapp.User` | `get*` | `get`, `get_by_id`, `get_all` |
| `myapp.User` | `*_by_id` | `get_by_id`, `delete_by_id` |
| `myapp.*Handler` | `handle` | すべての Handler クラスの handle メソッド |
| `json.JSONEncoder` | `encode*` | `encode`, `encode_object` |

---

## パターン構文

### サポートされているワイルドカード

| ワイルドカード | 説明 | 例 |
|--------|------|------|
| `*` | 任意の長さの文字にマッチ（空を含む） | `myapp.*` は `myapp.User`, `myapp.Order` にマッチ |
| `?` | 単一文字にマッチ | `User?` は `User1`, `User2` にマッチ |
| `[seq]` | seq 内の任意の文字にマッチ | `User[12]` は `User1`, `User2` にマッチ |
| `[!seq]` | seq に含まれない任意の文字にマッチ | `User[!0]` は `User1`, `User2` にマッチ（`User0` にはマッチしない） |

### パターンの種類

#### 1. 完全限定名

```bash
# 完全一致
peeka-cli sc "myapp.models.User"
peeka-cli sm "myapp.models.User.get"
```

#### 2. モジュールレベルワイルドカード

```bash
# モジュール配下のすべてのクラス
peeka-cli sc "myapp.models.*"

# 複数レベルのワイルドカード
peeka-cli sc "myapp.*.User"  # myapp 配下の任意のサブモジュールの User クラス
```

#### 3. クラス名ワイルドカード

```bash
# 接頭辞マッチ
peeka-cli sc "*Handler"       # すべての Handler クラス
peeka-cli sc "myapp.*Handler" # myapp 配下のすべての Handler クラス

# 接尾辞マッチ
peeka-cli sc "User*"          # User, UserHandler, UserModel

# 中間マッチ
peeka-cli sc "*User*"         # UserHandler, AdminUser, User
```

#### 4. メソッド名ワイルドカード

```bash
# sm コマンドのメソッドパターン
peeka-cli sm "myapp.User" --method-pattern "get*"
peeka-cli sm "myapp.User" --method-pattern "*_by_id"
peeka-cli sm "myapp.User" --method-pattern "is_*"
```

---

## 出力フォーマット

### sc コマンド出力

**基本モード**：
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"},
    {"name": "myapp.api.UserHandler"}
  ],
  "count": 3,
  "limit": 50
}
```

**詳細モード**（`-d`）：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model representing a system user.\n\nAttributes:\n    id: User ID\n    username: Username"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### sm コマンド出力

**基本モード**：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    },
    {
      "name": "update",
      "signature": "(self, user_id: int, **data) -> bool"
    }
  ],
  "count": 3,
  "limit": 50
}
```

**詳細モード**（`-d`）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None if not found"
    }
  ],
  "count": 1,
  "limit": 50
}
```

---

## 使用例

### 例 1：アプリケーションのすべてのモデルクラスを検索

```bash
peeka-cli sc "myapp.models.*" | jq -r '.classes[].name'
```

**出力**：
```
myapp.models.User
myapp.models.Order
myapp.models.Product
myapp.models.Payment
```

### 例 2：すべての Handler クラスを検索して詳細情報を取得

```bash
peeka-cli sc "*Handler" -d | jq .
```

**出力**：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.api.UserHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles user-related API requests."
    },
    {
      "name": "myapp.api.OrderHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles order-related API requests."
    }
  ],
  "count": 2
}
```

### 例 3：クラスのすべてのメソッドを検索

```bash
peeka-cli sm "myapp.User.*" | jq -r '.methods[] | "\(.name)\(.signature)"'
```

**出力**：
```
get(self, user_id: int) -> dict
create(self, **data) -> dict
update(self, user_id: int, **data) -> bool
delete(self, user_id: int) -> bool
is_active(self) -> bool
```

### 例 4：get_ で始まるすべてのメソッドを検索

```bash
peeka-cli sm "myapp.User" --method-pattern "get_*" | jq -r '.methods[].name'
```

**出力**：
```
get_by_id
get_by_username
get_all
get_active_users
```

### 例 5：サードパーティライブラリ（requests）の探索

```bash
# requests モジュールにどのようなクラスがあるか確認
peeka-cli sc "requests.*" | jq -r '.classes[].name'

# 出力：
# requests.Session
# requests.Response
# requests.Request
# requests.PreparedRequest

# Session クラスのメソッドを確認
peeka-cli sm "requests.Session" --method-pattern "*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# 出力：
# get(self, url, **kwargs) -> Response
# post(self, url, data=None, json=None, **kwargs) -> Response
# ...
```

### 例 6：watch コマンドとの組み合わせ

**シナリオ**：目標メソッドを見つけた後、`watch` で監視する。

```bash
# ステップ 1：order 処理に関係するすべてのメソッドを検索
peeka-cli sm "myapp.Order" --method-pattern "*process*"

# 出力：
# process_payment
# process_refund
# process_shipment

# ステップ 2：目標メソッドを選択して監視
peeka-cli watch "myapp.Order.process_payment" -n 10
```

---

## 完全な探索フロー

### フロー 1：未知のコードベースの探索

**目標**：プロジェクト構造と主要なクラスを迅速に理解。

```bash
# ステップ 1：すべてのアプリケーションモジュールのクラスをリストアップ
peeka-cli sc "myapp.*" > classes.json

# ステップ 2：モジュールごとにグループ化して統計
jq -r '.classes[].name | split(".") | .[0:2] | join(".")' classes.json | \
  sort | uniq -c

# 出力：
#   12 myapp.api
#    8 myapp.models
#    5 myapp.utils
#    3 myapp.services

# ステップ 3：各モジュールの詳細なクラスを確認
peeka-cli sc "myapp.api.*" -d | \
  jq -r '.classes[] | "\(.name)\n  \(.docstring)\n"'
```

### フロー 2：特定機能の実装の特定

**目標**：支払い機能を実装しているすべてのクラスとメソッドを見つける。

```bash
# ステップ 1：payment に関連するすべてのクラスを検索
peeka-cli sc "*payment*" -d

# ステップ 2：目標クラスを見つけたら、そのメソッドを確認
peeka-cli sm "myapp.payment.PaymentProcessor.*" -d

# ステップ 3：特定のメソッドの詳細情報を確認
peeka-cli sm "myapp.payment.PaymentProcessor.charge" -d | \
  jq -r '.methods[0].docstring'
```

### フロー 3：コードリファクタリングの検証

**目標**：リファクタリング後に、古いクラスが削除され、新しいクラスがロードされていることを検証。

```bash
# ステップ 1：古いクラスを検索（見つからないはず）
peeka-cli sc "myapp.OldUserHandler"
# 出力：{"status":"success","classes":[],"count":0}

# ステップ 2：新しいクラスを検索（見つかるはず）
peeka-cli sc "myapp.NewUserHandler" -d

# ステップ 3：新旧クラスのメソッドを比較
peeka-cli sm "myapp.NewUserHandler.*" > new_methods.json
# old_methods.json と new_methods.json を比較
```

### フロー 4：サードパーティライブラリ API の学習

**目標**：Flask フレームワークのコアクラスとメソッドを学習。

```bash
# ステップ 1：Flask にどのようなクラスがあるか確認
peeka-cli sc "flask.*" | jq -r '.classes[].name'

# 出力：
# flask.Flask
# flask.Blueprint
# flask.Request
# flask.Response

# ステップ 2：Flask クラスのすべてのメソッドを確認
peeka-cli sm "flask.Flask.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# ステップ 3：特定のメソッドのドキュメントを確認
peeka-cli sm "flask.Flask.route" -d | \
  jq -r '.methods[0].docstring'
```

---

## 注意点

### 1. ロード済みのモジュールしか検索できない

**重要**：`sc` と `sm` コマンドは**インポートされたモジュール**しか検索できません。

```bash
# myapp.plugin モジュールがインポートされていなければ検索できない
peeka-cli sc "myapp.plugin.*"
# 出力：{"classes": [], "count": 0}
```

**解決方法**：
- 機能をトリガーしてモジュールをインポートさせる（関連する API にアクセスするなど）
- またはコードを確認し、モジュールが確かにインポートされるか確認

### 2. マジックメソッドはデフォルトで表示されない

**デフォルトの動作**：`sm` コマンドはマジックメソッド（`__init__`, `__str__` など）を表示しません。

```bash
# __init__, __str__, __repr__ などは表示されない
peeka-cli sm "myapp.User.*"
```

**理由**：マジックメソッドは通常ビジネスロジックのエントリポイントではないため、フィルタリングしてノイズを減らしています。

### 3. 結果数制限

**デフォルト制限**：最大 50 個の結果を返します。

```bash
# 50 を超えてマッチしても、最初の 50 個だけが返される
peeka-cli sc "*" --limit 50
```

**制限の調整**：
```bash
# 制限を 200 に増やす
peeka-cli sc "*" --limit 200
```

**注意**：
- 制限を大きくしすぎると出力が多すぎて性能が低下する可能性があります
- 制限を増やすより、より具体的なパターンを使用することを推奨します

### 4. ファイルパスが None になることがある

**原因**：一部のクラス（組み込みクラス、C 拡張など）は対応する Python ファイルがありません。

```bash
peeka-cli sc "builtins.dict" -d

# 出力：
# {"name": "builtins.dict", "file": null, ...}
```

### 5. シグネチャが取得できないことがある

**原因**：一部のメソッド（C 拡張、組み込み関数など）は `inspect.signature()` でシグネチャを取得できません。

```bash
peeka-cli sm "builtins.dict.get"

# 出力：
# {"name": "get", "signature": null}
```

### 6. 性能影響

**影響度**：
- `sc` と `sm` コマンドは `sys.modules` を走査するため、数百ミリ秒必要になることがあります
- 結果の数が多いほど出力時間が長くなります
- 全体的な性能影響は無視できます（一度きりの操作なので）

**推奨**：
- 具体的なパターンを使用して検索範囲を減らす
- 頻繁な呼び出しを避ける（ループ内など）

---

## よくある質問

### Q1: なぜ特定のクラスが検索できないのですか？

**考えられる原因**：
1. **モジュールがインポートされていない**：クラスを含むモジュールがメモリにロードされていない
2. **パターンが間違っている**：パターンがクラスの完全限定名と一致しない
3. **結果が制限を超えている**：結果の数が `--limit` を超えている

**調査方法**：
```bash
# 方法 1：モジュールがインポートされているか確認
python3 -c "import sys; print('myapp.models' in sys.modules)"

# 方法 2：より緩いパターンを使用
peeka-cli sc "*User*"

# 方法 3：制限を増やす
peeka-cli sc "myapp.*" --limit 200
```

### Q2: すべてのモジュールのすべてのクラスを検索するには？

**答え**：`*` ワイルドカードを使用します。

```bash
peeka-cli sc "*" --limit 200
```

**警告**：
- 結果の数が非常に多くなる可能性があります（標準ライブラリとサードパーティライブラリを含むため）
- より具体的なパターンの使用を推奨します

### Q3: sm コマンドが __init__ メソッドを表示しないのはなぜですか？

**原因**：マジックメソッドはデフォルトでフィルタリングされています。

**マジックメソッドを表示するには**：
- 現在のバージョンではサポートされていません（将来 `--show-magic` パラメータを追加する予定です）
- Python コードで確認できます：
  ```python
  import inspect
  print([m for m in dir(MyClass) if m.startswith('__')])
  ```

### Q4: メソッド検索でクラス名とメソッド名を同時にマッチングするには？

**方法**：`sm` コマンドの 2 つのパラメータを組み合わせて使用します。

```bash
# すべての Handler クラスの handle メソッドを検索
# 注意：具体的なモジュール名がわかっている必要があります
peeka-cli sm "myapp.api.*Handler" --method-pattern "handle"
```

**制限**：`class_pattern` はモジュール名を含む必要があり、`*Handler` だけでは使用できません。

### Q5: 検索結果をファイルに出力するには？

**方法**：リダイレクトまたは `jq` を使用します。

```bash
# すべてのクラスをファイルに出力
peeka-cli sc "myapp.*" > classes.json

# クラス名のリストをプレーンテキストで出力
peeka-cli sc "myapp.*" | jq -r '.classes[].name' > class_names.txt

# メソッドシグネチャのリストを出力
peeka-cli sm "myapp.User.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"' > user_methods.txt
```

### Q6: 標準ライブラリのクラスを検索できますか？

**答え**：モジュールがインポートされていればできます。

```bash
# json モジュールのクラスを検索
peeka-cli sc "json.*"

# collections モジュールのクラスを検索
peeka-cli sc "collections.*"

# logging モジュールのクラスを検索
peeka-cli sc "logging.*"
```

---

## 高度なテクニック

### 1. プロジェクト API ドキュメントの自動生成

**シナリオ**：プロジェクトのクラスとメソッドの一覧を自動生成。

```bash
#!/bin/bash
# generate_api_doc.sh

PID=12345
OUTPUT="api_documentation.md"

echo "# API Documentation" > $OUTPUT
echo "" >> $OUTPUT

# すべてのクラスを取得
classes=$(peeka-cli sc "myapp.*" | jq -r '.classes[].name')

for class in $classes; do
  echo "## $class" >> $OUTPUT
  echo "" >> $OUTPUT

  # クラスの詳細情報を取得
  peeka-cli sc "$class" -d | \
    jq -r '.classes[0].docstring // "No description"' >> $OUTPUT
  echo "" >> $OUTPUT

  # クラスのすべてのメソッドを取得
  echo "### Methods" >> $OUTPUT
  echo "" >> $OUTPUT
  peeka-cli sm "$class.*" -d | \
    jq -r '.methods[] | "- `\(.name)\(.signature)`\n  \(.docstring // "No description")\n"' >> $OUTPUT
  echo "" >> $OUTPUT
done

echo "Documentation generated: $OUTPUT"
```

### 2. コードリファクタリング検証スクリプト

**シナリオ**：リファクタリング後に新旧クラスのメソッドが一致するか自動検証。

```bash
#!/bin/bash
# verify_refactor.sh

PID=12345
OLD_CLASS="myapp.OldUserHandler"
NEW_CLASS="myapp.NewUserHandler"

# 古いクラスのメソッドを取得
old_methods=$(peeka-cli sm "$OLD_CLASS.*" 2>/dev/null | \
  jq -r '.methods[].name' | sort)

# 新しいクラスのメソッドを取得
new_methods=$(peeka-cli sm "$NEW_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# 比較
if [ "$old_methods" == "$new_methods" ]; then
  echo "✅ PASS: Method signatures match"
else
  echo "❌ FAIL: Method signatures differ"
  echo "Old methods:"
  echo "$old_methods"
  echo "New methods:"
  echo "$new_methods"
fi
```

### 3. 未実装の抽象メソッドの検索

**シナリオ**：抽象クラスを継承しているが、すべての抽象メソッドを実装していないクラスを検索。

```bash
#!/bin/bash
# find_abstract_violations.sh

PID=12345
ABSTRACT_CLASS="myapp.BaseHandler"

# 抽象クラスのすべてのメソッドを取得
abstract_methods=$(peeka-cli sm "$ABSTRACT_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# すべてのサブクラスを検索
subclasses=$(peeka-cli sc "*Handler" | \
  jq -r '.classes[].name' | grep -v "$ABSTRACT_CLASS")

for subclass in $subclasses; do
  # サブクラスのメソッドを取得
  impl_methods=$(peeka-cli sm "$subclass.*" | \
    jq -r '.methods[].name' | sort)

  # すべての抽象メソッドが実装されているか確認
  missing=$(comm -23 <(echo "$abstract_methods") <(echo "$impl_methods"))

  if [ -n "$missing" ]; then
    echo "⚠️  $subclass missing methods:"
    echo "$missing"
  fi
done
```

### 4. 動的インポートモジュールの探索

**シナリオ**：目標モジュールがロードされていないので、インポートされるのを待ってから検索。

```bash
#!/bin/bash
# explore_module.sh

PID=12345
MODULE="myapp.plugins.experimental"

# ターゲットモジュールは機能がトリガされたときにインポートされると仮定
# ここではモジュールがロードされるのを待つ

# モジュールロードを待機（ポーリング）
for i in {1..10}; do
  classes=$(peeka-cli sc "$MODULE.*" | jq -r '.count')
  if [ "$classes" -gt 0 ]; then
    echo "Module loaded successfully"
    peeka-cli sc "$MODULE.*" -d
    break
  fi
  echo "Waiting for module to load... ($i/10)"
  sleep 2
done
```

### 5. IDE との統合

**シナリオ**：IDE が使用できる自動補完データを生成。

```bash
#!/bin/bash
# generate_autocomplete.sh

PID=12345

# 自動補完データを JSON 形式で生成
peeka-cli sc "myapp.*" | \
  jq -r '.classes[].name' | \
  while read class; do
    peeka-cli sm "$class.*" | \
      jq -r ".methods[] | {class: \"$class\", method: .name, signature: .signature}"
  done | jq -s . > autocomplete_data.json
```

### 6. モジュールロードの監視

**シナリオ**：アプリケーションがどのような新しいモジュール/クラスをロードするかリアルタイムで監視。

```bash
#!/bin/bash
# monitor_module_loading.sh

PID=12345
INTERVAL=5

# 初期状態を保存
peeka-cli sc "*" | jq -r '.classes[].name' | sort > initial_classes.txt

while true; do
  sleep $INTERVAL

  # 現在のクラスリストを取得
  peeka-cli sc "*" | jq -r '.classes[].name' | sort > current_classes.txt

  # 新しく追加されたクラスを見つける
  new_classes=$(comm -13 initial_classes.txt current_classes.txt)

  if [ -n "$new_classes" ]; then
    echo "[$(date)] New classes loaded:"
    echo "$new_classes"
  fi

  cp current_classes.txt initial_classes.txt
done
```

---

## まとめ

`sc` と `sm` コマンドはコード探索と動的分析の強力なツールで、特に以下の場面に適しています：
- 未知のコードベースの探索
- 特定機能の実装の検索
- 他のコマンドで使用するためのメソッドシグネチャの取得
- モジュールがロードされているか検証
- サードパーティライブラリ API の学習

**ベストプラクティス**：
- 具体的なパターンを使用して検索範囲を減らす
- `-d` パラメータと組み合わせて詳細情報を取得
- `jq` と組み合わせて強力なデータ処理を行う
- `watch`、`stack` などのコマンドと併用する
- 検索結果をファイルに出力して後続の分析に使用

**次のステップ**：
- [`watch`](watch.md) コマンド（関数呼び出しの観測）を理解する
- [`stack`](stack.md) コマンド（呼び出しスタックの追跡）を理解する
- [`monitor`](monitor.md) コマンド（性能監視）を理解する
