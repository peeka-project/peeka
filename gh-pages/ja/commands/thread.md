---
layout: default
title: thread コマンド
parent: コマンドリファレンス
nav_order: 11
---

# thread コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`thread` コマンドは、ターゲットプロセス内のすべてのスレッドをリストアップし、特定のスレッドの呼び出しスタック情報を確認するために使用されます。このコマンドは開発者がスレッド状態を迅速に特定し、デッドロック問題を診断し、スレッドのブロック原因を分析するのを支援します。


## 使用場面

- **スレッドの列挙**：プロセス内のすべてのスレッドとその状態を迅速にリストアップ
- **状態フィルタリング**：スレッド状態（RUNNABLE/WAITING/TIMED_WAITING）でスレッドをフィルタリング
- **スタック検査**：特定のスレッドの完全な呼び出しスタックを確認し、コード実行位置を特定
- **デッドロック診断**：スレッド状態を分析し、潜在的なデッドロックやブロッキング問題を発見
- **並行処理デバッグ**：マルチスレッドプログラムの実行状態とスレッド分布を理解

## コマンドフォーマット

```bash
peeka-cli attach <pid>    # 最初にターゲットプロセスにアタッチ
peeka-cli thread [options]
```

### パラメータ説明

| パラメータ           | 説明                                          | デフォルト   | 例                  |
|--------------|---------------------------------------------|-------|---------------------|
| `--tid`      | スレッド ID、特定のスレッドのスタック詳細を表示                        | なし     | `--tid 123456`      |
| `--state`    | 状態でスレッドをフィルタリング（RUNNABLE / WAITING / TIMED_WAITING） | なし     | `--state WAITING`   |
| `--sort-by`  | ソートフィールド（tid / name / state）                   | `tid` | `--sort-by name`    |
| `--depth`    | スタック深度制限（詳細ビューでのみ使用）                       | `50`  | `--depth 30`        |

### スレッド状態の説明

Peeka はスレッドの現在の呼び出しスタックを分析し、自動的にスレッド状態を推論します：

| 状態             | 説明                                     | 典型的なシナリオ                    |
|----------------|----------------------------------------|-------------------------|
| `RUNNABLE`     | スレッドが実行中または実行可能状態                           | 通常のコード実行                  |
| `WAITING`      | スレッドが無限期間の待機中                          | `wait()`, `join()`, `lock` など |
| `TIMED_WAITING` | スレッドが時間指定の待機中                               | `sleep()`, `poll()` など     |

**状態推論アルゴリズム**：スレッドスタックの最上位 3 つのフレームをチェックし、関数名とモジュール名に基づいてブロッキングパターン（`select`、`poll`、`wait`、`sleep` など）にマッチングします。

## 基本的な使い方

### 1. すべてのスレッドをリストアップ

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach 12345

# すべてのスレッドをリストアップ
peeka-cli thread
```

**出力例**：

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    },
    {
      "tid": 140234567891,
      "native_id": 12346,
      "name": "WorkerThread-1",
      "daemon": true,
      "alive": true,
      "state": "WAITING",
      "stack_depth": 8,
      "top_frame": {
        "filename": "/usr/lib/python3.12/threading.py",
        "lineno": 629,
        "funcname": "wait"
      }
    }
  ]
}
```

**フィールド説明**：

| フィールド            | 説明                                  | 例示値                    |
|---------------|-------------------------------------|------------------------|
| `tid`         | スレッド ID（Python ident）                | `140234567890`         |
| `native_id`   | ネイティブスレッド ID（Python 3.8+ で利用可能、None の場合もあり）     | `12345`                |
| `name`        | スレッド名                                | `"MainThread"`         |
| `daemon`      | デーモンスレッドかどうか                             | `false`                |
| `alive`       | スレッドが生存しているか                              | `true`                 |
| `state`       | 推論されたスレッド状態                             | `"RUNNABLE"`           |
| `stack_depth` | 呼び出しスタックの深度                               | `15`                   |
| `top_frame`   | スタックトップフレーム情報（filename / lineno / funcname） | `{"filename": "...", ...}` |

### 2. 特定の状態のスレッドをフィルタリング

```bash
# 待機中のスレッドだけを表示
peeka-cli thread --state WAITING

# スリープ中のスレッドだけを表示
peeka-cli thread --state TIMED_WAITING

# 実行中のスレッドだけを表示
peeka-cli thread --state RUNNABLE
```

### 3. 特定のスレッドのスタック詳細を表示

```bash
# スレッド 140234567890 の完全なスタックを表示
peeka-cli thread --tid 140234567890

# スタック深度を 30 層に制限
peeka-cli thread --tid 140234567890 --depth 30
```

**出力例**（詳細ビュー）：

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      },
      {
        "filename": "/app/worker.py",
        "lineno": 25,
        "funcname": "worker_loop",
        "locals_keys": ["queue", "item", "result"]
      },
      {
        "filename": "/app/main.py",
        "lineno": 100,
        "funcname": "run",
        "locals_keys": ["self", "config"]
      }
    ]
  }
}
```

**stack フィールド説明**：

| フィールド           | 説明              | 例示値                            |
|--------------|-----------------|--------------------------------|
| `filename`   | ソースファイルのパス           | `"/app/worker.py"`             |
| `lineno`     | 行号              | `25`                           |
| `funcname`   | 関数名             | `"worker_loop"`                |
| `locals_keys` | ローカル変数名のリスト（最大 20 個に制限） | `["queue", "item", "result"]`  |

### 4. フィールドでソート

```bash
# スレッド名でソート
peeka-cli thread --sort-by name

# スレッド状態でソート
peeka-cli thread --sort-by state

# スレッド ID でソート（デフォルト）
peeka-cli thread --sort-by tid
```

## 出力フォーマット

### list 出力（リストモード）

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    }
  ]
}
```

### detail 出力（詳細モード）

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      }
    ]
  }
}
```

## TUI での使用法

TUI モードでは、インタラクティブなインターフェースでスレッド情報を表示できます：

1. TUI を起動：
   ```bash
   peeka  # または python -m peeka.tui
   ```

2. ターゲットプロセスに接続（PID を入力するかプロセスを選択）

3. **`9`** キーを押して **Threads ビュー**に切り替え

4. 機能：
   - すべてのスレッドリストをリアルタイム表示
   - 状態によるスレッドフィルタリング
   - スレッドを選択してスタック詳細を表示
   - 名前、状態、ID によるソートをサポート

## 注意点

1. **状態推論の正確性**：
   - スレッド状態は呼び出しスタックの分析によって推論されるため、誤判定が発生する可能性があります
   - スタックトップの 3 層だけをチェックするため、深部のブロッキングは認識できない可能性があります
   - RUNNABLE 状態には実行中と実行可能の両方が含まれます

2. **native_id の利用可能性**：
   - `native_id` フィールドは Python 3.8+ でのみ利用可能です
   - 古いバージョンの Python ではこのフィールドは `null` になります

3. **ローカル変数の制限**：
   - 詳細ビューの `locals_keys` フィールドは最大 20 個のローカル変数名しか表示しません
   - 副作用を避けるため、変数の値は取得されません

4. **性能影響**：
   - スレッド情報の取得には `sys._current_frames()` と `threading.enumerate()` を使用します
   - 性能オーバーヘッドは非常に低いですが、スレッド数が非常に多い（>1000）場合には遅延が発生する可能性があります

5. **権限要件**：
   - 事前に `attach` コマンドでターゲットプロセスにアタッチする必要があります
   - アタッチ権限要件は [attach コマンドドキュメント](attach.md) を参照してください
