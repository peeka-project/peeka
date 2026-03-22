---
layout: default
title: top コマンド
parent: コマンドリファレンス
nav_order: 12
---

# top コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`top` コマンドは関数レベルのサンプリング性能プロファイラで、Linux の `top` コマンドや `py-spy top` に似ています。定期的にすべてのスレッドの呼び出しスタックをサンプリングし、各関数の CPU 使用状況を統計し、開発者が性能ボトルネックを迅速に特定するのを支援します。

**設計上の特徴**：
- **低オーバーヘッド**：サンプリングモードで、性能影響は 5% 未満
- **リアルタイム統計**：性能データをストリーミング出力し、リアルタイム監視をサポート
- **関数粒度**：正確に関数レベルまで表示し、own time と total time を表示
- **自動フィルタリング**：デフォルトで Peeka 自身のスレッドをフィルタリングし、干渉を回避

## 使用場面

- **性能ボトルネックの特定**：CPU 占有率が最も高い関数を見つけ出す
- **ホットスポット関数分析**：関数の呼び出し頻度と消費時間分布を統計
- **リアルタイム監視**：継続的にサンプリングし、プログラムの性能変化を観察
- **最適化の検証**：最適化前後の性能データを比較

## コマンドフォーマット

```bash
peeka-cli attach <pid>    # 最初にターゲットプロセスにアタッチ
peeka-cli top [options]
```

### パラメータ説明

| パラメータ                | 説明                                    | デフォルト    | 例                        |
|-------------------|---------------------------------------|--------|---------------------------|
| `-i, --interval`  | サンプリング間隔（秒）                               | `0.01` | `-i 0.02`（20ms ごとにサンプリング）       |
| `-c, --cycles`    | 表示周期数（-1 は無限）                        | `-1`   | `-c 10`（10 回表示後に自動停止）      |
| `--sort`          | ソート列（own / total / own-time / total-time） | `own`  | `--sort total`            |
| `--no-filter-peeka` | Peeka スレッドのフィルタリングを無効化（デフォルトは有効）                   | `false` | `--no-filter-peeka`（すべてのスレッドを表示） |

### 性能指標説明

| 指標           | 説明                           | 計算方式                     |
|--------------|------------------------------|--------------------------|
| `own_pct`    | 独占 CPU パーセンテージ（関数自身が消費する割合）       | `own_count / total_samples * 100` |
| `total_pct`  | 総 CPU パーセンテージ（呼び出す子関数を含む）         | `total_count / total_samples * 100` |
| `own_time`   | 独占時間（秒）                      | `own_count * interval`   |
| `total_time` | 総時間（秒、子関数を含む）                 | `total_count * interval` |
| `own_count`  | 独占サンプリング回数（スタックトップがこの関数だった回数）            | 直接統計                     |
| `total_count` | 総サンプリング回数（呼び出しスタックにこの関数が含まれていた回数）          | 重複排除して統計                     |

## 基本的な使い方

### 1. 性能分析を開始

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach 12345

# top コマンドを起動（デフォルト 10ms サンプリング間隔）
peeka-cli top
```

**出力例**（ストリーミング出力、毎秒 1 回更新）：

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    },
    {
      "name": "multiply",
      "filename": "/app/math_utils.py",
      "line": 42,
      "own_pct": 12.8,
      "total_pct": 13.4,
      "own_time": 0.128,
      "total_time": 0.134,
      "own_count": 128,
      "total_count": 134
    },
    {
      "name": "log_result",
      "filename": "/app/logger.py",
      "line": 89,
      "own_pct": 8.2,
      "total_pct": 8.9,
      "own_time": 0.082,
      "total_time": 0.089,
      "own_count": 82,
      "total_count": 89
    }
  ]
}
```

### 2. サンプリング間隔を調整

```bash
# 20ms サンプリング間隔（オーバーヘッドが低くなるが、精度が低下）
peeka-cli top -i 0.02

# 5ms サンプリング間隔（精度が高くなるが、オーバーヘッドが増加）
peeka-cli top -i 0.005
```

**サンプリング間隔の選択推奨**：
- **本番環境**：10-20ms（デフォルト 10ms）、性能影響 5% 未満
- **開発環境**：5-10ms、より高い精度
- **長時間監視**：20-50ms、オーバーヘッドを低減

### 3. 表示周期数を制限

```bash
# 10 回表示後に自動停止
peeka-cli top -c 10

# 60 回表示後に自動停止（約 1 分間）
peeka-cli top -c 60
```

### 4. 異なるフィールドでソート

```bash
# 独占 CPU パーセンテージでソート（デフォルト）
peeka-cli top --sort own

# 総 CPU パーセンテージでソート
peeka-cli top --sort total

# 独占時間でソート
peeka-cli top --sort own-time

# 総時間でソート
peeka-cli top --sort total-time
```

### 5. Peeka スレッドを含める

```bash
# すべてのスレッドを表示、Peeka 自身も含める
peeka-cli top --no-filter-peeka
```

**注意**：`--no-filter-peeka` を有効にすると Peeka Agent とサンプリングスレッド自身が統計に含まれます。通常は Peeka のデバッグやフィルタリングロジックの検証に使用されます。

## 出力フォーマット

### ストリーミング出力（毎秒 1 回スナップショット）

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    }
  ]
}
```

**フィールド説明**：

| フィールド               | 説明                | 例示値                      |
|------------------|-------------------|--------------------------|
| `top_id`         | 性能分析セッション ID        | `"top_a1b2c3d4"`         |
| `total_samples`  | 総サンプリング回数             | `1000`                   |
| `sample_interval` | サンプリング間隔（秒）           | `0.01`                   |
| `functions`      | 関数統計リスト（own_pct 降順） | `[...]`                  |

**functions 配列の要素**：

| フィールド           | 説明                 | 例示値                  |
|--------------|--------------------|----------------------|
| `name`       | 関数名                | `"compute_matrix"`   |
| `filename`   | ソースファイルのパス              | `"/app/algorithm.py"` |
| `line`       | 関数定義の行号             | `156`                |
| `own_pct`    | 独占 CPU パーセンテージ        | `45.3`               |
| `total_pct`  | 総 CPU パーセンテージ（子関数を含む）   | `58.7`               |
| `own_time`   | 独占時間（秒）            | `0.453`              |
| `total_time` | 総時間（秒、子関数を含む）        | `0.587`              |
| `own_count`  | 独占サンプリング回数             | `453`                |
| `total_count` | 総サンプリング回数（重複排除）          | `587`                |

## リアルタイム監視の例

### jq を使用してトップ 5 のホットスポット関数をフィルタリング

```bash
peeka-cli top | jq 'select(.type == "top_snapshot") | .functions[:5]'
```

### 特定モジュールの CPU 占有率を統計

```bash
peeka-cli top | jq '
  select(.type == "top_snapshot") |
  .functions[] |
  select(.filename | contains("/app/")) |
  {name, own_pct}
'
```

### 性能データをファイルに出力

```bash
# 100 回のスナップショットを采集してから停止し、ファイルに保存
peeka-cli top -c 100 > performance.jsonl
```

## TUI での使用法

TUI モードでは、`top` コマンドは視覚的な性能分析インターフェースを提供します：

1. TUI を起動：
   ```bash
   peeka  # または python -m peeka.tui
   ```

2. ターゲットプロセスに接続（PID を入力するかプロセスを選択）

3. **`0`** キーを押して **Top ビュー**に切り替え

4. 機能：
   - 関数性能ランキングをリアルタイム表示
   - own_pct / total_pct / own_time / total_time でのソートをサポート
   - 色分け：赤（high CPU）、黄（medium）、緑（low）
   - サンプリング統計を表示（total_samples, interval）
   - 一時停止/再開をサポート

5. ショートカット：
   - `r`：データをリフレッシュ
   - `s`：ソートフィールドを切り替え
   - `Enter`：性能分析を開始
   - `Delete`：性能分析を停止
   - `c`：統計データをクリア（reset）

## 仕組み

### サンプリングフロー

1. **サンプリングスレッドを起動**：指定された間隔（デフォルト 10ms）でバックグラウンドスレッドを実行
2. **スレッドスナップショットを取得**：`sys._current_frames()` を呼び出してすべてのスレッドの現在のスタックフレームを取得
3. **スレッドをフィルタリング**：Peeka 自身のスレッドを除外（`--no-filter-peeka` で無効化可能）
4. **呼び出しスタックを走査**：スタックトップ（リーフフレーム）からスタックボトム（ルートフレーム）までフレームごとに統計
5. **統計を更新**：
   - スタックトップフレーム：`own_count += 1`（関数自身の実行）
   - すべてのフレーム：`total_count += 1`（呼び出し連鎖に含まれるので）
6. **スナップショットを生成**：毎秒 1 回スナップショットを生成し、クライアントにプッシュ

### フィルタリング戦略

デフォルトでは以下のスレッドをフィルタリングします（`--no-filter-peeka` で無効化）：
- スレッド名が `peeka-` で始まるスレッド
- 実行コードパスが Peeka パッケージディレクトリ配下にあるスレッド
- サンプリングスレッド自身

### 統計指標の計算

```python
# 独占パーセンテージ
own_pct = (own_count / total_samples) * 100

# 総パーセンテージ
total_pct = (total_count / total_samples) * 100

# 独占時間
own_time = own_count * sample_interval

# 総時間
total_time = total_count * sample_interval
```

## 注意点

1. **サンプリング精度**：
   - サンプリングモードはすべての関数呼び出しをキャプチャできるわけではなく、サンプリング時点のスタックフレームしか統計しません
   - 短時間しか実行されない関数は見落とされる可能性があります
   - 長時間実行の性能分析に適しており、マイクロベンチマークには適していません

2. **性能オーバーヘッド**：
   - デフォルト 10ms 間隔：性能影響 5% 未満
   - 5ms 間隔：性能影響は約 5-10%
   - 1ms 間隔：性能影響 10-20%（推奨されない）

3. **スレッドフィルタリング**：
   - デフォルトで Peeka スレッドをフィルタリングし、統計データの汚染を回避
   - `--no-filter-peeka` ですべてのスレッドを表示可能（Peeka を含む）

4. **出力頻度**：
   - CLI モード：毎秒 1 回スナップショットを出力（固定）
   - サンプリング間隔と出力頻度は独立しています

5. **停止方法**：
   - Ctrl+C：正常に停止し、最終スナップショットを出力
   - `--cycles` パラメータ：自動的に停止
   - TUI モード：`Delete` キーで停止

6. **trace コマンドとの違い**：
   - `top`：サンプリングモード、低オーバーヘッド、長時間監視に適している
   - `trace`：インストゥルメンテーションモード、高精度、短時間の呼び出し連鎖分析に適している
   - `top` はすべての関数を統計し、`trace` は指定された関数だけを追跡します

7. **権限要件**：
   - 事前に `attach` コマンドでターゲットプロセスにアタッチする必要があります
   - アタッチ権限要件は [attach コマンドドキュメント](attach.md) を参照してください
