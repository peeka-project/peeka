---
layout: default
title: monitor コマンド
parent: コマンドリファレンス
nav_order: 5
---

# monitor コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## コマンドの概要

`monitor` コマンドは、関数の性能統計データを定期的に収集して出力します。呼び出し回数、成功/失敗率、応答時間などの重要な指標を提供する軽量な性能監視ツールで、本番環境での長期実行に適しています。

**コア機能**：
- 定期的に関数性能統計を出力（デフォルトは 60 秒ごと）
- 呼び出し回数、成功/失敗率を統計
- 応答時間（平均、最小、最大）を統計
- 軽量設計（詳細な観測データを記録せず、統計のみ）
- 複数の関数の同時監視をサポート
- 監視周期と持続時間を設定可能

**watch コマンドとの違い**：
- `watch`：**呼び出しごとの詳細情報**を記録（パラメータ、戻り値、呼び出しスタックなど）
- `monitor`：**統計データのみ**を記録（呼び出し回数、応答時間など）、周期ごとの集計を出力

## TUI での使用法

TUI モードでは、**`5`** キーを押して **Monitor ビュー**に切り替えると、以下のインタラクティブ機能が利用できます：

- **モード入力**：関数名の自動補完をサポート（ターゲットプロセスからリアルタイム取得）
- **パラメータ設定**：出力間隔、監視周期数を視覚的に設定可能
- **統計データ表示**：性能統計指標をリアルタイム表示
  - 呼び出し回数（total）、成功回数（success）、失敗回数（fail）
  - 失敗率（fail_rate）、応答時間（avg/min/max）
  - 周期カウンタ（cycle）と間隔（interval）
- **ショートカット操作**：
  - 入力モード後に Enter を押して監視を開始
  - `s` キーで監視を停止
  - `c` キーで統計データをクリア

**CLI との同等性**：以下の例はデモンストレーションのために CLI コマンドを使用しています。TUI はグラフィカルインターフェースで同じ機能を提供します。
---

## 使用場面

### 1. 本番環境性能監視

**シナリオ**：長期的に重要な関数の性能指標を監視し、性能劣化をタイムリーに発見。

```bash
# 60 秒ごとに統計データを出力し、継続的に実行
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**出力例**：
```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

**解説**：
- 1 分間に合計 1234 回の呼び出し
- 成功 1200 回、失敗 34 回（失敗率 2.75%）
- 平均応答時間 45.678 ミリ秒
- 最速 5.123 ミリ秒、最遅 234.567 ミリ秒

### 2. サービスヘルスチェック

**シナリオ**：サービスコア関数の失敗率を監視し、閾値を超えた場合にアラート。

```bash
# 30 秒ごとに出力、10 周期（5 分間）継続
peeka-cli monitor "myapp.payment.process" \
  --interval 30 -c 10 | \
  jq -r 'select(.fail_rate > 0.05) | "ALERT: Fail rate \(.fail_rate*100)%"'
```

**効果**：失敗率が 5% を超えた場合にアラートメッセージを出力。

### 3. 性能ベースラインの確立

**シナリオ**：通常負荷の下で性能ベースラインを確立し、後続の性能比較に使用。

```bash
# 1 時間監視（60 回、毎分 1 回）
peeka-cli monitor "myapp.db.execute_query" \
  --interval 60 -c 60 > baseline.jsonl

# データを分析
jq -s '{
  avg_rt: (map(.rt_avg) | add / length),
  avg_total: (map(.total) | add / length),
  max_fail_rate: (map(.fail_rate) | max)
}' baseline.jsonl
```

**出力**：
```json
{
  "avg_rt": 12.345,
  "avg_total": 567,
  "max_fail_rate": 0.0123
}
```

### 4. 複数関数の並行比較監視

**シナリオ**：複数の関数を同時に監視し、性能差を比較。

```bash
# ターミナル 1：API v1 を監視
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > api_v1.jsonl &

# ターミナル 2：API v2 を監視
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > api_v2.jsonl &

# ターミナル 3：リアルタイム比較
while true; do
  v1=$(tail -1 api_v1.jsonl | jq -r '.rt_avg')
  v2=$(tail -1 api_v2.jsonl | jq -r '.rt_avg')
  echo "v1: ${v1}ms, v2: ${v2}ms"
  sleep 30
done
```

### 5. 負荷テスト中の監視

**シナリオ**：負荷テスト時にリアルタイムで関数性能を監視し、システムの挙動を観察。

```bash
# コア関数を監視、10 秒ごとに出力
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'
```

**出力**：
```
1: 123 calls, 45.67ms avg, 1.2% fail
2: 234 calls, 67.89ms avg, 2.3% fail
3: 345 calls, 89.01ms avg, 3.4% fail
...
```

---

## コマンドフォーマット

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach <pid>

# 次に monitor コマンドを実行
peeka-cli monitor <pattern> [options]
```

**必須パラメータ**：
- `pattern`：対象関数のパターン（`module.Class.method` の形式）

**オプションパラメータ**：
- `--interval`：出力間隔（秒、デフォルト 60）
- `-c, --cycles`：監視周期数（-1 は無限、デフォルト -1）

---

## パラメータ説明

### pattern - 関数パターン

監視対象の関数を指定します。フォーマットは `watch` コマンドと同じです。

| フォーマット | 説明 | 例 |
|------|------|------|
| `module.function` | モジュールレベル関数 | `myapp.utils.calculate` |
| `module.Class.method` | クラスメソッド | `myapp.models.User.save` |
| `module.Class.static_method` | 静的メソッド | `myapp.utils.Helper.validate` |

**注意点**：
- モジュールルートからの完全限定名を使用する必要があります
- ワイルドカードはサポートされていません
- 対象関数は既にメモリにロードされている必要があります

### --interval - 出力間隔

統計データの出力頻度を制御します（単位：秒）。

| 値 | 説明 | 適用場面 |
|----|------|----------|
| `10` | 10 秒ごとに出力 | 負荷テスト、リアルタイム監視 |
| `30` | 30 秒ごとに出力 | 高頻度監視 |
| `60`（デフォルト）| 60 秒ごとに出力 | 本番環境通常監視 |
| `300` | 5 分ごとに出力 | 長期トレンド分析 |

**例**：
```bash
# 高頻度監視（10 秒ごと）
peeka-cli monitor "myapp.api.handler" --interval 10

# 長期監視（5 分ごと）
peeka-cli monitor "myapp.batch.process" --interval 300
```

**注意**：
- 間隔が短いほど出力頻度が高くなります（関数の呼び出し頻度に応じて設定することを推奨）
- 間隔が短すぎると、単一周期内の呼び出し回数が少なすぎて統計的意義が小さくなります
- 間隔が長すぎると重要な性能変化を見逃す可能性があります

### -c, --cycles - 監視周期数

監視を継続する周期数を制御します。

| 値 | 説明 | 適用場面 |
|----|------|----------|
| `-1`（デフォルト）| 無限監視 | 本番環境継続監視 |
| `1` | 1 周期監視後に停止 | 現在の状態をクイック確認 |
| `10` | 10 周期監視後に停止 | 固定時間監視 |
| `60` | 60 周期監視後に停止 | 1 時間監視（interval=60） |

**例**：
```bash
# 1 回監視後に停止（現在 1 分間の統計を確認）
peeka-cli monitor "myapp.func" --interval 60 -c 1

# 10 分間監視（10 回、毎回 1 分）
peeka-cli monitor "myapp.func" --interval 60 -c 10

# 継続監視（手動で停止するまで）
peeka-cli monitor "myapp.func" --interval 60
```

**合計時間の計算**：
- 合計時間 = `interval` × `cycles`
- 例：`--interval 60 -c 10` = 10 分
- 例：`--interval 30 -c 120` = 1 時間

---

## 統計指標説明

### 基礎指標

| 指標 | 型 | 説明 |
|------|------|------|
| `total` | int | 現在周期までの累積呼び出し回数 |
| `success` | int | 成功呼び出し回数（例外がスローされなかった） |
| `fail` | int | 失敗呼び出し回数（例外がスローされた） |

### 派生指標

| 指標 | 型 | 計算式 | 説明 |
|------|------|----------|------|
| `fail_rate` | float | `fail / total` | 失敗率（0-1 の間、小数点以下 4 桁を保持） |
| `rt_avg` | float | `sum(duration) / total` | 平均応答時間（ミリ秒、小数点以下 3 桁を保持） |
| `rt_min` | float | `min(duration)` | 最小応答時間（ミリ秒、小数点以下 3 桁を保持） |
| `rt_max` | float | `max(duration)` | 最大応答時間（ミリ秒、小数点以下 3 桁を保持） |

### メタデータ

| フィールド | 型 | 説明 |
|------|------|------|
| `watch_id` | string | 監視タスクの一意識別子 |
| `cycle` | int | 現在の周期番号（1 から開始） |

---

## 出力フォーマット

`monitor` コマンドは JSON Lines 形式を出力します（各周期ごとに 1 行）。ストリーミング処理に便利です。

### 完全な出力例

```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

### フィールド説明

| フィールド | 型 | 説明 | 例 |
|------|------|------|------|
| `watch_id` | string | 監視タスクの一意識別子 | `"monitor_a1b2c3d4"` |
| `cycle` | int | 周期番号（1 から開始） | `1`, `2`, `3`... |
| `total` | int | 現在周期までの累積総呼び出し回数 | `1234` |
| `success` | int | 累積成功呼び出し回数 | `1200` |
| `fail` | int | 累積失敗呼び出し回数 | `34` |
| `fail_rate` | float | 失敗率（0-1） | `0.0275`（2.75%） |
| `rt_avg` | float | 平均応答時間（ミリ秒） | `45.678` |
| `rt_min` | float | 最小応答時間（ミリ秒） | `5.123` |
| `rt_max` | float | 最大応答時間（ミリ秒） | `234.567` |

### 統計周期の説明

**重要**：各周期の統計データは**累積**されます（監視開始から現在まで）。

```json
// 周期 1（0-60 秒）
{"cycle": 1, "total": 100, "rt_avg": 50}

// 周期 2（0-120 秒、累積）
{"cycle": 2, "total": 250, "rt_avg": 55}

// 周期 3（0-180 秒、累積）
{"cycle": 3, "total": 400, "rt_avg": 53}
```

**単一周期のデータを計算する必要がある場合**：
```bash
# 周期 2 の増加呼び出し回数を計算
total_cycle2 - total_cycle1 = 250 - 100 = 150
```

---

## 使用例

### 例 1：基本的な監視

**シナリオ**：API エントリ関数を監視し、毎分 1 回統計を出力。

```bash
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**出力**：
```json
{"watch_id":"monitor_a1b2c3d4","cycle":1,"total":1234,"success":1200,"fail":34,"fail_rate":0.0275,"rt_avg":45.678,"rt_min":5.123,"rt_max":234.567}
{"watch_id":"monitor_a1b2c3d4","cycle":2,"total":2456,"success":2400,"fail":56,"fail_rate":0.0228,"rt_avg":48.123,"rt_min":5.123,"rt_max":345.678}
{"watch_id":"monitor_a1b2c3d4","cycle":3,"total":3678,"success":3600,"fail":78,"fail_rate":0.0212,"rt_avg":46.890,"rt_min":5.123,"rt_max":345.678}
...
```

### 例 2：固定時間監視

**シナリオ**：5 分間監視（5 回、毎回 1 分）。

```bash
peeka-cli monitor "myapp.payment.charge" --interval 60 -c 5
```

**動作**：
- 5 回の統計データを出力
- 5 回目の出力後に自動的に停止
- 合計監視時間：5 分

### 例 3：リアルタイム監視（高頻度）

**シナリオ**：負荷テスト中にリアルタイム監視、10 秒ごとに出力。

```bash
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail) fails"'
```

**出力**：
```
1: 123 calls, 45.67ms avg, 2 fails
2: 278 calls, 52.34ms avg, 5 fails
3: 456 calls, 58.90ms avg, 8 fails
...
```

### 例 4：失敗率アラート

**シナリオ**：失敗率を監視し、5% を超えた場合にアラートを出力。

```bash
peeka-cli monitor "myapp.critical_func" --interval 30 | \
  jq -r 'if .fail_rate > 0.05 then
           "⚠️  ALERT: Fail rate \(.fail_rate * 100)% at cycle \(.cycle)"
         else
           "✅  Healthy: \(.fail_rate * 100)% fail rate"
         end'
```

**出力**：
```
✅  Healthy: 1.2% fail rate
✅  Healthy: 2.3% fail rate
⚠️  ALERT: Fail rate 6.7% at cycle 3
```

### 例 5：応答時間トレンド

**シナリオ**：応答時間の変化を監視し、トレンドグラフを描画。

```bash
# 30 分間監視（30 回、毎回 1 分）
peeka-cli monitor "myapp.db.query" --interval 60 -c 30 | \
  jq -r '"\(.cycle) \(.rt_avg)"' > rt_trend.dat

# gnuplot を使用してトレンドグラフを描画（gnuplot のインストールが必要）
gnuplot <<EOF
set terminal png size 800,600
set output 'rt_trend.png'
set xlabel 'Cycle'
set ylabel 'Response Time (ms)'
set title 'Response Time Trend'
plot 'rt_trend.dat' with lines
EOF
```

### 例 6：watch コマンドとの併用

**シナリオ**：最初に `monitor` で性能問題を発見し、次に `watch` で詳細調査。

```bash
# ステップ 1：監視を開始し、応答時間の異常を発見
peeka-cli monitor "myapp.process" --interval 60 | \
  jq -r 'select(.rt_avg > 100)'
# 出力：{"cycle": 5, "rt_avg": 234.567, ...}

# ステップ 2：watch を使用して詳細な呼び出し情報を確認
peeka-cli watch "myapp.process" -n 10
# パラメータ、戻り値、実行時間を分析

# ステップ 3：問題を特定したら監視を停止
# （Ctrl+C または cycles パラメータを使用）
```

---

## 完全な監視フロー

### フロー 1：本番環境性能ベースライン構築

**目標**：通常負荷の下で性能ベースラインを構築し、後続の性能比較に使用。

```bash
# ステップ 1：コア関数を 1 時間監視
peeka-cli monitor "myapp.api.handle_request" \
  --interval 60 -c 60 > baseline_$(date +%Y%m%d).jsonl

# ステップ 2：ベースライン統計を計算
jq -s '{
  avg_total: (map(.total) | add / length),
  avg_rt: (map(.rt_avg) | add / length),
  p50_rt: (map(.rt_avg) | sort)[30],
  p95_rt: (map(.rt_avg) | sort)[57],
  max_fail_rate: (map(.fail_rate) | max)
}' baseline_$(date +%Y%m%d).jsonl > baseline_summary.json

# ステップ 3：ベースラインを確認
cat baseline_summary.json
```

**出力**：
```json
{
  "avg_total": 567.8,
  "avg_rt": 45.678,
  "p50_rt": 44.123,
  "p95_rt": 67.890,
  "max_fail_rate": 0.0123
}
```

### フロー 2：性能劣化検出

**目標**：現在の性能とベースラインを比較し、性能劣化を検出。

```bash
# ステップ 1：ベースラインデータを読み込み
baseline_rt=$(jq -r '.avg_rt' baseline_summary.json)
echo "Baseline avg RT: ${baseline_rt}ms"

# ステップ 2：リアルタイム監視して比較
peeka-cli monitor "myapp.api.handle_request" --interval 60 | \
  jq -r --arg baseline "$baseline_rt" '
    if .rt_avg > ($baseline | tonumber * 1.5) then
      "⚠️  DEGRADATION: \(.rt_avg)ms (baseline: \($baseline)ms)"
    else
      "✅  Normal: \(.rt_avg)ms"
    end
  '
```

**出力**：
```
✅  Normal: 47.123ms
✅  Normal: 48.567ms
⚠️  DEGRADATION: 89.012ms (baseline: 45.678ms)
```

### フロー 3：複数関数の性能比較

**目標**：異なる実装の性能差を比較（例：API v1 vs v2）。

```bash
# ステップ 1：2 つの関数を同時に監視
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > v1.jsonl &
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > v2.jsonl &

# ステップ 2：データ収集を待機（10 分）
sleep 600

# ステップ 3：監視を停止
kill %1 %2

# ステップ 4：比較分析
echo "API v1:"
jq -s 'map(.rt_avg) | add / length' v1.jsonl
echo "API v2:"
jq -s 'map(.rt_avg) | add / length' v2.jsonl
```

**出力**：
```
API v1:
67.890
API v2:
45.123
```

**結論**：v2 は v1 より性能が優れています（平均 33% 高速）。

### フロー 4：負荷テスト監視

**目標**：負荷テスト中にシステム性能を監視し、性能曲線を観察。

```bash
# ステップ 1：監視を開始（高頻度、10 秒ごと）
peeka-cli monitor "myapp.process" --interval 10 > load_test.jsonl &

# ステップ 2：別のターミナルで負荷テストを開始
# ab -n 10000 -c 100 http://localhost:8000/api/endpoint

# ステップ 3：リアルタイムで性能指標を観察
tail -f load_test.jsonl | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'

# ステップ 4：テスト終了後に監視を停止
kill %1

# ステップ 5：性能曲線を分析
jq -r '"\(.cycle) \(.total) \(.rt_avg) \(.fail_rate)"' load_test.jsonl > metrics.dat
```

---

## 注意点

### 1. 性能影響

**影響度**：
- **統計記録**：呼び出しごとに約 0.1-0.2ms の追加オーバーヘッド
- **統計計算**：各周期で約 0.01ms（無視できる）
- **JSON 出力**：各周期で約 0.1ms（無視できる）

**全体のオーバーヘッド**：約 0.1-0.2ms/回（`watch` コマンドより 10 倍軽量）

**利点**：
- 詳細データを記録しないので、メモリ占有が極めて小さい
- 長期実行に適しており、性能影響は無視できる
- 高頻度関数の監視に適している

### 2. 統計データは累積される

**重要**：`monitor` の統計データは**累積**され、単周期のものではありません。

```json
// 周期 1：0-60 秒を累積
{"cycle": 1, "total": 100}

// 周期 2：0-120 秒を累積（第 2 の 60 秒ではない）
{"cycle": 2, "total": 250}
```

**単周期データの計算方法**：
```bash
# 隣接周期の差分を計算して単周期の呼び出し回数を抽出
jq -s '[.[0].total] + [range(1; length) |
  {cycle: .[.].cycle, calls: .[.].total - .[-1].total}]' monitor.jsonl
```

### 3. 応答時間統計

**rt_avg の計算方式**：
- 累積平均：`sum(すべての呼び出しのduration) / total`
- 加重移動平均ではない
- 単周期平均ではない

**例**：
```json
// 周期 1：100 回呼び出し、平均 50ms
{"cycle": 1, "total": 100, "rt_avg": 50}

// 周期 2：さらに 100 回呼び出し、平均 60ms
// 累積平均 = (100*50 + 100*60) / 200 = 55ms
{"cycle": 2, "total": 200, "rt_avg": 55}
```

### 4. 失敗の定義

**fail カウントルール**：
- 関数が例外をスロー → `fail` +1
- 関数が正常に戻り → `success` +1
- `None` またはエラーコードを返しても、例外がスローされなければ `success`

**注意**：
- アプリケーションがエラーコードを使用して例外を使用しない場合、`fail` カウントは 0 になります
- ビジネスロジックに応じて `success` の真実性を分析することを推奨

### 5. 監視の停止

**方法 1**：`-c` パラメータで周期数を制限（自動停止）
```bash
peeka-cli monitor "myapp.func" --interval 60 -c 10
```

**方法 2**：手動で Ctrl+C（ターゲットプロセスに影響しない）
```bash
peeka-cli monitor "myapp.func" --interval 60
# Ctrl+C を押して停止
```

**重要**：
- 監視停止後、ターゲット関数は元の状態に戻ります（性能影響なし）
- 統計データは永続化されません（出力を手動で保存する必要があります）
- 複数の監視タスクは互いに独立しています

### 6. 複数の監視タスク

**サポート**：複数の `monitor` タスクを同時に起動して異なる関数を監視できます。

```bash
# ターミナル 1：API を監視
peeka-cli monitor "myapp.api.handler" --interval 60

# ターミナル 2：データベースを監視
peeka-cli monitor "myapp.db.query" --interval 60

# ターミナル 3：キャッシュを監視
peeka-cli monitor "myapp.cache.get" --interval 60
```

**注意**：
- 各タスクは独立して統計を行い、互いに影響しません
- 監視する関数が増えるほど、性能オーバーヘッドは累積します
- 10 個以下の関数の監視を推奨

---

## よくある質問

### Q1: 現在実行中の監視タスクを確認するには？

**方法 1**：`reset` アクションを使用（CLI がサポートしている場合）
```bash
peeka-cli reset -l
```

**方法 2**：プロセス内の対応するクライアント接続を確認
```bash
ps aux | grep "peeka-cli monitor" | grep 12345
```

**方法 3**：ターゲットプロセスのソケット接続を確認
```bash
lsof -p 12345 | grep peeka
```

### Q2: 単一周期の呼び出し回数を計算するには？

**方法**：`jq` を使用して隣接周期の差分を計算。

```bash
jq -s '
  [range(0; length)] | map({
    cycle: .[.].cycle,
    calls: (if . == 0 then .[0].total else .[.].total - .[.-1].total end),
    rt_avg: .[.].rt_avg
  })
' monitor.jsonl
```

**出力**：
```json
[
  {"cycle": 1, "calls": 100, "rt_avg": 50},
  {"cycle": 2, "calls": 150, "rt_avg": 55},
  {"cycle": 3, "calls": 200, "rt_avg": 53}
]
```

### Q3: rt_avg が突然低下する原因は？

**考えられる原因**：
1. **新しい呼び出しの応答時間がより速い**：累積平均が低下する
2. **キャッシュがヒット**：後続の呼び出しがキャッシュヒットして速くなる
3. **負荷が低下**：システムリソースが十分になり、応答が速くなる

**調査方法**：
```bash
# rt_min と rt_max の変化を確認
jq -r '"\(.cycle) \(.rt_min) \(.rt_avg) \(.rt_max)"' monitor.jsonl
```

**例**：
```
1  5.123  50.000  234.567
2  5.123  48.000  234.567  ← rt_avg が低下したが rt_min/max は不変
3  2.456  35.000  234.567  ← rt_min が低下し、新しい呼び出しが速いことがわかる
```

### Q4: 非同期関数を監視できる？

**答え**：`monitor` コマンドは非同期関数（async def）をサポートしています。

```bash
peeka-cli monitor "myapp.async_handler" --interval 60
```

**注意**：
- 統計されるのは非同期関数の**実際の実行時間**（待機時間を含まない）
- 関数内部に `await` がある場合、待機時間は `rt_avg` に含まれません

### Q5: total の数値が大きいのに出力が少ないのはなぜ？

**原因**：`monitor` は**周期的な統計のみ**を出力し、呼び出しごとに出力しません。

- `total` は累積呼び出し回数
- 各 `interval` につき 1 回の統計のみを出力
- 呼び出しごとの詳細情報が必要な場合は、`watch` コマンドを使用してください

### Q6: 標準ライブラリ関数を監視できる？

**答え**：できますが、性能影響に注意してください。

```bash
# json.dumps を監視（呼び出し頻度が非常に高い可能性がある）
peeka-cli monitor "json.dumps" --interval 10 -c 6
```

**警告**：
- 標準ライブラリ関数は通常呼び出し頻度が非常に高い
- 軽量な `monitor` であっても、累積オーバーヘッドが明らかになる可能性がある
- まず `--interval 10 -c 1` でテストし、`total` の数を確認することを推奨

---

## 高度なテクニック

### 1. リアルタイム性能ダッシュボード

**シナリオ**：`watch` コマンド（シェルツール）を使用してリアルタイムダッシュボードを作成。

```bash
#!/bin/bash
# dashboard.sh

PID=12345
PATTERN="myapp.api.handler"
LOG="monitor.jsonl"

# 監視をバックグラウンドで開始
peeka-cli monitor "$PATTERN" --interval 10 > $LOG &
MONITOR_PID=$!

# リアルタイムでダッシュボードを表示
while kill -0 $MONITOR_PID 2>/dev/null; do
  clear
  echo "=== Performance Dashboard ==="
  echo ""
  tail -1 $LOG | jq -r '
    "Cycle: \(.cycle)",
    "Total Calls: \(.total)",
    "Success Rate: \((1 - .fail_rate) * 100)%",
    "Fail Rate: \(.fail_rate * 100)%",
    "Avg RT: \(.rt_avg)ms",
    "Min RT: \(.rt_min)ms",
    "Max RT: \(.rt_max)ms"
  '
  sleep 10
done
```

### 2. Prometheus との統合

**シナリオ**：監視データを Prometheus にエクスポート。

```bash
#!/bin/bash
# export_to_prometheus.sh

PID=12345
PATTERN="myapp.api.handler"
METRICS_FILE="/var/lib/node_exporter/textfile_collector/peeka.prom"

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r '
    "peeka_calls_total{pattern=\"\($PATTERN)\"} \(.total)",
    "peeka_success_total{pattern=\"\($PATTERN)\"} \(.success)",
    "peeka_fail_total{pattern=\"\($PATTERN)\"} \(.fail)",
    "peeka_fail_rate{pattern=\"\($PATTERN)\"} \(.fail_rate)",
    "peeka_rt_avg_ms{pattern=\"\($PATTERN)\"} \(.rt_avg)",
    "peeka_rt_min_ms{pattern=\"\($PATTERN)\"} \(.rt_min)",
    "peeka_rt_max_ms{pattern=\"\($PATTERN)\"} \(.rt_max)"
  ' > $METRICS_FILE
```

**Prometheus クエリ例**：
```promql
# 失敗率アラート
rate(peeka_fail_total[5m]) / rate(peeka_calls_total[5m]) > 0.05

# 応答時間トレンド
peeka_rt_avg_ms{pattern="myapp.api.handler"}
```

### 3. 性能回帰検出

**シナリオ**：デプロイごとに自動的に性能劣化がないか検出。

```bash
#!/bin/bash
# regression_test.sh

PID=12345
PATTERN="myapp.api.handler"
BASELINE="baseline_rt.txt"

# ベースラインを読み込み
baseline_rt=$(cat $BASELINE)

# 5 分間監視
current_rt=$(peeka-cli monitor "$PATTERN" --interval 60 -c 5 | \
  jq -s 'map(.rt_avg) | add / length')

# 比較
if (( $(echo "$current_rt > $baseline_rt * 1.2" | bc -l) )); then
  echo "❌ REGRESSION: $current_rt ms (baseline: $baseline_rt ms)"
  exit 1
else
  echo "✅ PASS: $current_rt ms (baseline: $baseline_rt ms)"
  exit 0
fi
```

### 4. 複数関数の集計統計

**シナリオ**：複数の関数を監視し、統計データを集計。

```bash
# 3 つの関数を並行して監視
peeka-cli monitor "myapp.api.v1" --interval 60 -c 10 > v1.jsonl &
peeka-cli monitor "myapp.api.v2" --interval 60 -c 10 > v2.jsonl &
peeka-cli monitor "myapp.api.v3" --interval 60 -c 10 > v3.jsonl &

# 完了を待機
wait

# 集計統計
jq -s '
  reduce .[] as $item ({};
    .total += $item.total |
    .success += $item.success |
    .fail += $item.fail
  ) |
  .fail_rate = .fail / .total
' v1.jsonl v2.jsonl v3.jsonl
```

### 5. 自動アラートスクリプト

**シナリオ**：異常を検出した場合に自動的にアラートを送信（Slack、メールなど）。

```bash
#!/bin/bash
# alert_on_degradation.sh

PID=12345
PATTERN="myapp.critical"
THRESHOLD_RT=100      # 応答時間閾値（ミリ秒）
THRESHOLD_FAIL=0.05   # 失敗率閾値（5%）

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r --arg rt "$THRESHOLD_RT" --arg fail "$THRESHOLD_FAIL" '
    if .rt_avg > ($rt | tonumber) or .fail_rate > ($fail | tonumber) then
      "ALERT: cycle=\(.cycle), rt=\(.rt_avg)ms, fail=\(.fail_rate*100)%
    else
      empty
    end
  ' | \
  while read line; do
    # アラートを送信（例：Slack）
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
      -H 'Content-Type: application/json' \
      -d "{\"text\": \"$line\"}"
  done
```

### 6. 履歴データ分析

**シナリオ**：履歴監視データを分析し、性能の法則を見つける。

```bash
# 1 週間の監視データを収集
for day in {1..7}; do
  peeka-cli monitor "myapp.func" --interval 3600 -c 24 > \
    monitor_day${day}.jsonl
  sleep 86400  # 1 日
done

# 毎日同じ時刻の性能を分析
for hour in {0..23}; do
  echo -n "Hour $hour: "
  jq -s --arg h "$hour" 'map(select(.cycle == ($h | tonumber + 1))) |
    map(.rt_avg) | add / length' monitor_day*.jsonl
done
```

---

## まとめ

`monitor` コマンドは本番環境性能監視の強力なツールで、特に以下の場面に適しています：
- 長期的な性能監視
- 性能ベースラインの構築
- 性能劣化の検出
- 負荷テスト中のリアルタイム監視
- Prometheus などの監視システムとの統合

**ベストプラクティス**：
- 関数の呼び出し頻度に応じて適切な `--interval` を選択（30-60 秒を推奨）
- `-c` で周期数を制限する（忘れて停止することを避ける）
- ファイルに出力（`> monitor.jsonl`）して後続の分析に便利にする
- `jq` と組み合わせて強力なデータ分析を行う
- `watch` コマンドと併用する（先に `monitor` で問題を発見し、次に `watch` で詳細調査）

**次のステップ**：
- [`watch`](watch.md) コマンド（関数呼び出しの詳細観測）を理解する
- [`stack`](stack.md) コマンド（呼び出しスタックの追跡）を理解する
- [`memory`](memory.md) コマンド（メモリ分析）を理解する
