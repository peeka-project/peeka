---
layout: default
title: サンプルチュートリアル
nav_order: 5
permalink: /examples
---

# サンプルチュートリアル
{: .no_toc }

実際のシナリオを通して、Peeka を使って問題を診断して解決する方法を学びます。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## シナリオ 1: 遅い API の診断

### 問題の説明

API インターフェースがたまに非常に遅くなる（> 1 秒）。遅い呼び出しの原因を見つける必要があります。

### 解決ステップ

#### 1. プロセスにアタッチ

```bash
# API サービスプロセスを見つける
ps aux | grep "api_server.py"
# 出力: user 12345 ...

# アタッチ
peeka-cli attach 12345
```

#### 2. 全体的なパフォーマンスをモニタリング

```bash
# 10秒ごとに統計
peeka-cli monitor "app.api.handle_request" --interval 10
```

出力：
```json
{"type":"observation","func_name":"app.api.handle_request","total":150,"success":148,"fail":2,"avg_rt":250.5,"min_rt":50.2,"max_rt":1850.3}
```

`max_rt` が 1850ms に達していて、遅い呼び出しが存在することがわかりました。

#### 3. 遅い呼び出しをオブザーブ

```bash
# 実行時間 > 1000ms の呼び出しだけをオブザーブ
peeka-cli watch "app.api.handle_request" \
  --condition "cost > 1000" \
  --times 10
```

出力：
```json
{"type":"observation","watch_id":"watch_001","func_name":"app.api.handle_request","args":[{"user_id": 12345}],"result":{"status": "ok"},"duration_ms":1850.3,"count":1}
```

遅い呼び出しのパラメータが `user_id=12345` であることがわかりました。

#### 4. 呼び出しチェーンをトレース

```bash
# 完全な呼び出しチェーンをトレースして、時間のかかっている箇所を見つける
peeka-cli trace "app.api.handle_request" \
  --condition "cost > 1000" \
  --depth 5 \
  --times 1
```

出力：
```
`---[1850.3ms] app.api.handle_request()
    +---[5.2ms] app.auth.validate_token()
    +---[1800.1ms] app.db.query_user_data()  ← 遅い
    |   +---[1795.5ms] sqlalchemy.query.all()
    |   `---[2.1ms] app.db._parse_results()
    `---[15.7ms] app.response.build()
```

**結論**: 遅い呼び出しは `app.db.query_user_data()` によって引き起こされ、SQL クエリに時間がかかりすぎています。

#### 5. 修正の確認

SQL クエリを最適化した後、再度モニタリング：

```bash
peeka-cli monitor "app.api.handle_request" --interval 10
```

出力：
```json
{"type":"observation","total":150,"avg_rt":120.5,"max_rt":450.3}
```

パフォーマンスが大幅に向上しました！

---

## シナリオ 2: 例外の原因特定

### 問題の説明

バックグラウンドタスクがたまに `ValueError` をスローしますが、ログが不完全で原因を特定できません。

### 解決ステップ

#### 1. 例外をオブザーブ

```bash
# 例外をスローした呼び出しだけをオブザーブ
peeka-cli watch "app.tasks.process_data" \
  --exception
```

出力：
```json
{
  "type":"observation",
  "func_name":"app.tasks.process_data",
  "args":[{"data": [1, 2, null]}],
  "success":false,
  "exception":"ValueError: invalid value",
  "duration_ms":5.2
}
```

例外の引数に `null` が含まれていることがわかりました。

#### 2. 呼び出しスタックを確認

```bash
# 例外発生時の呼び出しスタックをキャプチャ
peeka-cli stack "app.tasks.process_data" \
  --condition "throwExp is not None" \
  --times 1
```

出力：
```
Thread: WorkerThread-1
  File "scheduler.py", line 45, in run
    self.execute_task(task)
  File "scheduler.py", line 78, in execute_task
    result = task.process_data(data)
  File "tasks.py", line 120, in process_data
    validated = self._validate(data)  ← ここで例外がスローされた
```

**結論**: 例外は `scheduler.py` から渡された `null` データによって引き起こされました。

#### 3. 修正の確認

入力検証を追加した後、再度テスト：

```bash
peeka-cli watch "app.tasks.process_data" --times 100
```

100回の呼び出しを観測し、例外はありませんでした。

---

## シナリオ 3: コード修正の検証

### 問題の説明

キャッシュロジックを修正したので、キャッシュが実際に効いているか検証する必要があります。

### 解決ステップ

#### 1. キャッシュ関数をオブザーブ

```bash
# キャッシュヒットの状況をオブザーブ
peeka-cli watch "app.cache.get" --times 20
```

出力：
```json
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
{"type":"observation","func_name":"app.cache.get","args":["user_456"],"result":null,"from_cache":false}
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
```

#### 2. ヒット率を統計

```bash
peeka-cli watch "app.cache.get" --times 1000 | \
  jq 'select(.type == "observation") | .from_cache' | \
  awk '{if($1=="true") hit++; total++} END {print "Hit Rate:", (hit/total)*100, "%"}'
```

出力：
```
Hit Rate: 85.3 %
```

**結論**: キャッシュヒット率は 85% で、期待通りです。

---

## シナリオ 4: 関数パフォーマンス回帰のモニタリング

### 問題の説明

新しいバージョンをデプロイした後、パフォーマンス回帰が心配なので、リアルタイムでモニタリングする必要があります。

### 解決ステップ

#### 1. パフォーマンスベースラインを作成

デプロイ前：
```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > baseline.jsonl
```

#### 2. デプロイ後のモニタリング

```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > after_deploy.jsonl
```

#### 3. 比較分析

```python
# compare.py
import json

def load_stats(file):
    stats = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                stats.append(msg["avg_rt"])
    return sum(stats) / len(stats) if stats else 0

baseline = load_stats("baseline.jsonl")
after = load_stats("after_deploy.jsonl")

print(f"Baseline: {baseline:.2f}ms")
print(f"After Deploy: {after:.2f}ms")
print(f"Change: {((after - baseline) / baseline) * 100:.1f}%")
```

出力：
```
Baseline: 125.50ms
After Deploy: 130.20ms
Change: +3.7%
```

**結論**: パフォーマンスは 3.7% わずかに低下しましたが、許容範囲内です。

---

## シナリオ 5: 競合状態のデバッグ

### 問題の説明

マルチスレッドプログラムでたまにデータの不整合が発生します。競合状態が疑われます。

### 解決ステップ

#### 1. 重要な関数の呼び出し順序をオブザーブ

```bash
# 2つの重要な関数をオブザーブ
peeka-cli watch "app.data.read" --times 100 > read.jsonl &
peeka-cli watch "app.data.write" --times 100 > write.jsonl &
```

#### 2. タイムスタンプを分析

```python
# analyze_race.py
import json
from collections import defaultdict

def load_calls(file):
    calls = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                calls.append((msg["timestamp"], msg["func_name"]))
    return calls

reads = load_calls("read.jsonl")
writes = load_calls("write.jsonl")

# マージしてソート
all_calls = sorted(reads + writes, key=lambda x: x[0])

# 疑わしいパターンを検索: read -> read（間に write がない）
for i in range(len(all_calls) - 1):
    curr_func = all_calls[i][1]
    next_func = all_calls[i+1][1]
    if "read" in curr_func and "read" in next_func:
        print(f"Suspicious pattern at {all_calls[i][0]}")
```

#### 3. 修正の確認

ロック保護を追加した後、再度テスト：

```bash
peeka-cli watch "app.data.read" --times 100 | \
  jq 'select(.type == "observation") | .data_version' | \
  uniq -c
```

出力はデータバージョンが一致していて、競合はありませんでした。

---

## シナリオ 6: パラメータ分布の分析

### 問題の説明

関数パラメータの分布を理解して、キャッシュ戦略を最適化する必要があります。

### 解決ステップ

#### 1. パラメータデータを収集

```bash
peeka-cli watch "app.service.query" --times 1000 > params.jsonl
```

#### 2. 分布を分析

```bash
# 最初のパラメータを抽出
cat params.jsonl | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c | sort -rn | head -10
```

出力：
```
    245 "user_type_A"
    198 "user_type_B"
     87 "user_type_C"
     45 "user_type_D"
     ...
```

#### 3. 可視化

```python
# visualize.py
import json
from collections import Counter
import matplotlib.pyplot as plt

params = []
with open("params.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg.get("type") == "observation":
            params.append(msg["args"][0])

counter = Counter(params)
labels, values = zip(*counter.most_common(10))

plt.bar(labels, values)
plt.xlabel("Parameter Value")
plt.ylabel("Frequency")
plt.title("Parameter Distribution")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("param_dist.png")
```

**結論**: `user_type_A` と `user_type_B` が最も高い割合を占めているので、優先的にキャッシュすべきです。

---

## シナリオ 7: 本番環境のリアルタイムアラート

### 問題の説明

本番環境で重要な関数をリアルタイムでモニタリングし、異常が発生したら自動的にアラートする必要があります。

### 解決ステップ

#### 1. モニタリングスクリプトを作成

```bash
#!/bin/bash
# monitor_and_alert.sh

peeka-cli monitor "app.api.critical" --interval 10 | \
while read -r line; do
    # JSON をパース
    avg_rt=$(echo "$line" | jq -r '.avg_rt // 0')
    fail=$(echo "$line" | jq -r '.fail // 0')

    # アラート条件
    if (( $(echo "$avg_rt > 500" | bc -l) )); then
        echo "ALERT: High latency detected: ${avg_rt}ms" | \
          mail -s "Peeka Alert" ops@example.com
    fi

    if (( fail > 0 )); then
        echo "ALERT: ${fail} failures detected" | \
          mail -s "Peeka Alert" ops@example.com
    fi
done
```

#### 2. バックグラウンドで実行

```bash
nohup ./monitor_and_alert.sh > alert.log 2>&1 &
```

#### 3. モニタリングシステムに統合

```python
# prometheus_exporter.py
from prometheus_client import Gauge, start_http_server
import json
import subprocess

# メトリクスを定義
api_latency = Gauge('api_critical_latency_ms', 'API critical latency')
api_failures = Gauge('api_critical_failures', 'API critical failures')

# HTTP サーバーを起動
start_http_server(8000)

# Peeka の出力を読み込む
proc = subprocess.Popen(
    ['peeka-cli', 'monitor', 'app.api.critical', '--interval', '10'],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    msg = json.loads(line)
    if msg.get("type") == "observation":
        api_latency.set(msg.get("avg_rt", 0))
        api_failures.set(msg.get("fail", 0))
```

---

## ベストプラクティスのまとめ

### 1. 段階的に範囲を絞る

```bash
# 粗い粒度から細かい粒度へ
monitor → watch → trace → stack
```

### 2. 条件フィルタリングを使用

```bash
# データが多すぎることを回避
--condition "cost > 100"
--times 10
```

### 3. オブザベーションデータを保存

```bash
# オフライン分析が容易
peeka-cli watch "func" > data.jsonl
```

### 4. ツールチェーンと組み合わせる

```bash
# Unix ツールを最大限に活用
peeka-cli watch "func" | jq | awk | gnuplot
```

### 5. 自動化に統合

```python
# CI/CD に統合
python -m peeka.analyze --baseline baseline.jsonl --current current.jsonl
```

---

## より多くのリソース

- [コマンドリファレンス]({% link ja/commands/index.md %}) - 詳細なコマンドドキュメント
- [アーキテクチャ設計]({% link ja/architecture.md %}) - 実装原理を理解
- [トラブルシューティング]({% link ja/troubleshooting.md %}) - よくある問題の解決
