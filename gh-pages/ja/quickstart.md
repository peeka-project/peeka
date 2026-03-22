---
layout: default
title: クイックスタート
nav_order: 3
permalink: /quickstart
---

# クイックスタート
{: .no_toc }

簡単なステップで Peeka の基本機能をすぐに使い始めることができます。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 最初の例

### 1. ターゲットプログラムを準備

簡単な Python プログラム `demo.py` を作成します：

```python
# demo.py
import time
import os

class Calculator:
    def add(self, a, b):
        time.sleep(0.1)  # 計算時間をシミュレート
        return a + b

    def multiply(self, a, b):
        time.sleep(0.05)
        return a * b

def main():
    calc = Calculator()
    while True:
        result1 = calc.add(1, 2)
        print(f"add(1, 2) = {result1}")

        result2 = calc.multiply(3, 4)
        print(f"multiply(3, 4) = {result2}")

        time.sleep(1)

if __name__ == "__main__":
    print(f"プロセス PID: {os.getpid()}")
    main()
```

### 2. ターゲットプログラムを実行

```bash
python demo.py
# 出力: プロセス PID: 12345
```

### 3. プロセスにアタッチ

別のターミナルウィンドウで：

```bash
peeka-cli attach 12345
```

出力：
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_xxx.sock"}}
```

### 4. 関数呼び出しをオブザーブ

`add` メソッドの呼び出しをオブザーブ：

```bash
peeka-cli watch "demo.Calculator.add" --times 3
```

出力：
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"demo.Calculator.add"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.123,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586201.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.087,"count":2}
{"type":"observation","watch_id":"watch_001","timestamp":1705586202.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.091,"count":3}
{"type":"event","event":"watch_stopped","data":{"watch_id":"watch_001","reason":"max_count_reached"}}
```

---

## コア機能のデモ

### 関数呼び出しのオブザーブ (watch)

#### 基本的なオブザベーション

```bash
# 5回の呼び出しをオブザーブ
peeka-cli watch "demo.Calculator.add" --times 5

# 無制限にオブザーブ（Ctrl+C で停止）
peeka-cli watch "demo.Calculator.add"
```

#### 条件付きフィルタリング

特定の条件を満たす呼び出しだけをオブザーブ：

```bash
# 最初の引数が 100 より大きい呼び出しだけをオブザーブ
peeka-cli watch "demo.Calculator.multiply" --condition "params[0] > 100"

# 実行時間が 10ms を超える呼び出しだけをオブザーブ
peeka-cli watch "demo.Calculator.add" --condition "cost > 10"

# 複数条件の組み合わせ
peeka-cli watch "demo.func" --condition "len(params) > 2 and cost > 5"
```

#### オブザベーションポイントの制御

```bash
# 関数エントリ時にオブザーブ（入力パラメータを確認）
peeka-cli watch "demo.Calculator.add" --before

# 成功時のみオブザーブ
peeka-cli watch "demo.Calculator.add" --success

# 例外発生時のみオブザーブ
peeka-cli watch "demo.Calculator.add" --exception
```

### 呼び出しチェーンのトレース (trace)

関数の完全な呼び出しチェーンと各呼び出しの実行時間を確認：

```bash
peeka-cli trace "demo.Calculator.add" --depth 3 --times 1
```

出力（ツリー構造）：
```
`---[125.3ms] demo.Calculator.add()
    +---[2.1ms] time.sleep()
    `---[1.2ms] builtins.print()
```

### 呼び出しスタックのトレース (stack)

関数が誰に呼び出されたかを確認：

```bash
peeka-cli stack "demo.Calculator.add" --times 1
```

出力：
```
Thread: MainThread
  File "demo.py", line 15, in main
    result1 = calc.add(1, 2)
  File "demo.py", line 6, in add
    return a + b
```

### パフォーマンスモニタリング (monitor)

リアルタイムで関数のパフォーマンス指標を統計：

```bash
peeka-cli monitor "demo.Calculator.add" --interval 5 -c 3
```

出力：
```json
{"type":"observation","timestamp":1705586200.123,"func_name":"demo.Calculator.add","total":10,"success":10,"fail":0,"avg_rt":100.5,"min_rt":98.2,"max_rt":105.3}
```

---

## データ処理

### jq を使った出力処理

Peeka は標準の JSONL フォーマットを出力するので、jq などのツールと簡単に連携できます。

#### オブザベーションデータの抽出

```bash
# オブザベーションデータだけを表示（他のメッセージをフィルタ）
peeka-cli watch "demo.func" | jq 'select(.type == "observation")'

# 関数の戻り値だけを表示
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | .result'

# パラメータと戻り値を表示
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | {args, result}'
```

#### フィルタリングと統計

```bash
# 遅い呼び出しをフィルタ（実行時間 > 10ms）
peeka-cli watch "demo.func" | jq 'select(.type == "observation" and .duration_ms > 10)'

# 成功率を統計
peeka-cli watch "demo.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  uniq -c

# 平均実行時間を計算
peeka-cli watch "demo.func" --times 100 | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'
```

#### ファイルへの保存

```bash
# オブザベーションデータを保存
peeka-cli watch "demo.func" --times 1000 > observations.jsonl

# 後で分析
cat observations.jsonl | jq 'select(.type == "observation" and .success == false)'
```

---

## TUI インターフェースの使用

Peeka は Textual ベースのインタラクティブな TUI インターフェースを提供しています。

### TUI の起動

```bash
peeka
```

### TUI 機能

1. **プロセス選択** - システムプロセスを自動検出して選択可能
2. **Dashboard ダッシュボード** (`1`) - リアルタイムでプロセス情報を表示
3. **Watch オブザベーションビュー** (`2`) - インタラクティブな関数オブザベーション
4. **Trace トレースビュー** (`3`) - 可視化された呼び出しツリー
5. **Stack 呼び出しスタックビュー** (`4`) - 呼び出しスタックトレース
6. **Monitor モニタリングビュー** (`5`) - パフォーマンスモニタリング
7. **Memory メモリビュー** (`6`) - メモリ分析
8. **Logger ログビュー** (`7`) - ログ管理
9. **Inspect インスペクトビュー** (`8`) - オブジェクト検査
10. **Threads スレッドビュー** (`9`) - スレッド分析
11. **Top ホットスポットビュー** (`0`) - 関数パフォーマンスサンプリング
12. **Agent Log エージェントログ** (`8`) - ターゲットプロセス内の Agent ログを表示

### TUI キーボードショートカット

| ショートカット | 機能 |
|-------------|------|
| `1` | Dashboard ダッシュボードに切り替え |
| `2` | Watch オブザベーションビューに切り替え |
| `3` | Trace トレースビューに切り替え |
| `4` | Stack 呼び出しスタックビューに切り替え |
| `5` | Monitor モニタリングビューに切り替え |
| `6` | Memory メモリビューに切り替え |
| `7` | Logger ログビューに切り替え |
| `8` | Agent Log エージェントログに切り替え |
| `9` | Threads スレッドビューに切り替え |
| `0` | Top ホットスポットビューに切り替え |
| `?` | ヘルプを表示 |
| `q` | 終了 |

TUI の詳細については [TUI 使用ガイド]({% link ja/tui.md %}) を参照してください。

---

## 実際のユースケース

### シナリオ 1：遅い API の診断

```bash
# API 処理関数をオブザーブして遅い呼び出しを見つける
peeka-cli watch "app.api.handle_request" --condition "cost > 1000"

# 遅い呼び出しの完全な呼び出しチェーンをトレース
peeka-cli trace "app.api.handle_request" --condition "cost > 1000" --depth 5
```

### シナリオ 2：例外の原因特定

```bash
# 例外が発生した場合のみオブザーブ
peeka-cli watch "app.service.process" --exception

# 例外発生時の呼び出しスタックを確認
peeka-cli stack "app.service.process" --condition "exception != None"
```

### シナリオ 3：関数パフォーマンスのモニタリング

```bash
# 10秒ごとにパフォーマンス指標を統計
peeka-cli monitor "app.service.critical_func" --interval 10

# jq を組み合わせてリアルタイムアラート
peeka-cli monitor "app.service.critical_func" --interval 5 | \
  jq 'select(.type == "observation" and .avg_rt > 100) | "Alert: avg RT = \(.avg_rt)ms"'
```

### シナリオ 4：パラメータの検証

```bash
# 特定のパラメータ値の呼び出しを確認
peeka-cli watch "app.service.process" --condition "params[0] == 'debug_value'"

# パラメータの分布を確認
peeka-cli watch "app.service.process" --times 100 | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c
```

---

## ベストプラクティス

### 1. 条件フィルタリングでノイズを減らす

本番環境では関数呼び出しが頻繁なので、条件フィルタリングを使って重要な呼び出しだけをオブザーブ：

```bash
# ✅ 推奨：遅い呼び出しだけをオブザーブ
peeka-cli watch "func" --condition "cost > 100"

# ❌ 非推奨：すべての呼び出しをオブザーブ（データ量が多くなる）
peeka-cli watch "func"
```

### 2. オブザベーション回数を制限する

長時間のオブザベーションによる過剰なデータ生成を回避：

```bash
# ✅ 推奨：固定回数をオブザーブ
peeka-cli watch "func" --times 10

# ❌ 非推奨：無制限にオブザーブ
peeka-cli watch "func"  # 大量のデータが生成される可能性がある
```

### 3. JSONL フォーマットで分析しやすくする

オブザベーションデータを JSONL で保存して、後続の分析を容易に：

```bash
# データを収集
peeka-cli watch "func" --times 1000 > data.jsonl

# オフライン分析
cat data.jsonl | jq 'select(.type == "observation") | {duration_ms, success}' | \
  jq -s 'group_by(.success) | map({success: .[0].success, count: length})'
```

### 4. 層別化診断

粗い粒度から細かい粒度へ、段階的に問題を特定：

```bash
# 1. まず monitor で全体的なパフォーマンスを把握
peeka-cli monitor "app.api.*" --interval 10

# 2. 異常が見つかったら watch で詳細をオブザーブ
peeka-cli watch "app.api.slow_func" --condition "cost > 100"

# 3. trace で完全な呼び出しチェーンを追跡
peeka-cli trace "app.api.slow_func" --depth 5
```

---

## 次のステップ

- [コマンドリファレンス]({% link ja/commands/index.md %}) - すべてのコマンドの詳細な使い方を理解
- [サンプルチュートリアル]({% link ja/examples.md %}) - より多くの実際のアプリケーションシナリオ
- [アーキテクチャ設計]({% link ja/architecture.md %}) - Peeka の設計原理を理解
- [トラブルシューティング]({% link ja/troubleshooting.md %}) - 問題が発生した場合の解決策
