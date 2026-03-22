---
layout: default
title: memory コマンド
parent: コマンドリファレンス
nav_order: 7
---

# memory コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`memory` コマンドは、実行中の Python プロセスの**メモリ使用状況**を分析するために使用されます。メモリ概要、トレース制御、割り当て分析、スナップショット管理、スナップショット比較、参照連鎖クエリ、スナップショット出力、GC 統計など、計 10 種類の診断操作を提供します。Peeka のコアメモリ診断ツールで、本番環境のメモリリーク調査やパフォーマンス最適化に適しています。


## 使用場面

- **メモリリーク診断**: どのコード位置が最も多くのメモリを割り当てているかを確認
- **パフォーマンス最適化**: メモリ割り当てのホットスポットを特定し、メモリ使用を最適化
- **GC 分析**: オブジェクト型の数を統計し、オブジェクト数の異常を発見
- **スナップショット比較**: 複数のスナップショットを出力し、オフラインでメモリ増加を比較分析
- **RSS 監視**: プロセスの物理メモリ（RSS）使用状況を確認

## TUI での使用法

TUI モードでは、**`6`** キーを押して **Memory ビュー**に切り替えると、4 つの Tab ページと豊富なインタラクティブ機能が利用できます：

#### Overview Tab（メモリ概要）

- プロセス RSS（物理メモリ）表示、単位は MB
- RSS トレンド Sparkline グラフ（最新 100 サンプリングポイント）
- tracemalloc 現在のトレースメモリ / ピークメモリ
- GC 三代カウント（gen0, gen1, gen2）
- **Top Objects by Size** テーブル：型、数、Δ数、サイズ、Δサイズ
  - リフレッシュごとに自動的に増分を計算（赤 = 増加、緑 = 減少）
  - ヘッダークリックでソート可能

#### Allocations Tab（割り当てホットスポット）

- 追跡の開始が必要
- Top N メモリ割り当てを表示：Rank、Size、Count、Location（ファイル:行番号）
- 自動リフレッシュで同期更新

#### Diff Tab（スナップショット比較）

- **Snap ボタン**：tracemalloc スナップショットを撮影（最大 2 個、FIFO）
- **Diff ボタン**：2 つのスナップショットを比較し、テーブルで Location、Size Δ、New、Old、Count Δ を表示
- 増分データに色分け（赤は増加、緑は減少）

#### References Tab（参照連鎖分析）

- 型名を入力（例：`dict`、`MyClass`）
- **Referrers ボタン**：ツリー表示でその型のオブジェクトを誰が参照しているか表示（リークの根本原因調査）
- **Referents ボタン**：ツリー表示でその型のオブジェクトが何を参照しているか表示（オブジェクト構造分析）

#### コントロールバーとショートカット

| コントロール | ショートカット | 機能 |
|------|:------:|------|
| Refresh | `r` | 概要と割り当てを手動でリフレッシュ |
| Track | `T` | tracemalloc 追跡を開始/停止 |
| GC | `g` | GC をトリガし統計をリフレッシュ |
| Dump | — | スナップショットファイルをディスクに出力 |
| Auto | `a` | 自動リフレッシュ（5 秒間隔） |
| nframe 入力ボックス | — | tracemalloc スタック深度を設定（1-50） |
| limit 入力ボックス | — | GC/割り当て表示件数を設定（1-100） |

**CLI との同等性**：以下の例はデモンストレーションのために CLI コマンドを使用しています。TUI はグラフィカルインターフェースで同じ機能を提供します。
## コマンドフォーマット

```bash
# 最初にターゲットプロセスにアタッチ
peeka-cli attach <pid>

# 次に memory コマンドを実行
peeka-cli memory [options]
```

### パラメータ説明

| パラメータ | 説明 | デフォルト | 例 |
|------|------|--------|------|
| `--action` | メモリ操作タイプ | `overview` | `--action start` |
| `--nframe` | tracemalloc 呼び出しスタック深度 | `25` | `--nframe 50` |
| `--group-by` | 割り当てグループ化方法 | `lineno` | `--group-by filename` |
| `--limit` | 結果数制限 | `20` | `--limit 50` |
| `--filename` | スナップショットファイル名 | 自動生成 | `--filename snapshot1` |
| `--type-name` | 型名（referrers/referents 用） | - | `--type-name dict` |
| `--max-depth` | 参照連鎖再帰深度 | `2` | `--max-depth 3` |
| `--max-per-level` | 階層ごとの最大項目数 | `10` | `--max-per-level 20` |

### action 操作タイプ

| Action | 説明 | 事前に start が必要 | 主な用途 |
|--------|------|-------------|----------|
| **overview** | メモリ概要 | ❌ 否 | RSS、GC 状態、tracemalloc 状態の確認 |
| **start** | 追跡開始 | - | tracemalloc メモリ追跡の有効化 |
| **stop** | 追跡停止 | ❌ 否 | tracemalloc を閉じて追跡オーバーヘッドを解放 |
| **top** | Top N 割り当て | ✅ は | コード位置別のメモリ割り当てホットスポット表示 |
| **dump** | スナップショット出力 | ✅ は | オフライン分析用にスナップショットを保存 |
| **gc** | GC 統計 | ❌ 否 | オブジェクト型の数とサイズを統計 |
| **snapshot** | メモリスナップショット | ✅ は | メモリ内にスナップショットを保存（FIFO、最大 2 個） |
| **diff** | スナップショット比較 | ✅ は | 最新の 2 つの snapshot を比較し、メモリ増分変化を確認 |
| **referrers** | 参照者クエリ | ❌ 否 | 指定された型のオブジェクトを誰が保持しているか検索（リーク調査） |
| **referents** | 被参照者クエリ | ❌ 否 | 指定された型のオブジェクトが何を参照しているか検索（構造分析） |

## 基本的な使い方

### 1. メモリ概要（overview）

プロセスの現在のメモリ状態を表示します。**追跡の開始は不要**です。

```bash
# メモリ概要を表示（デフォルト action）
peeka-cli memory --action overview

# または他の action を使用
peeka-cli memory --action start
```

**出力例**：

```json
{
  "status": "success",
  "action": "overview",
  "timestamp": 1738328400.0,
  "pid": 12345,
  "rss_bytes": 524288000,
  "rss_source": "procfs",
  "tracemalloc": {
    "enabled": false,
    "current_bytes": null,
    "peak_bytes": null
  },
  "gc": {
    "enabled": true,
    "counts": [150, 10, 2],
    "stats": [
      {"collections": 45, "collected": 1234, "uncollectable": 0},
      {"collections": 4, "collected": 89, "uncollectable": 0},
      {"collections": 0, "collected": 0, "uncollectable": 0}
    ]
  }
}
```

**フィールド説明**：

| フィールド | 説明 | 例値 |
|------|------|--------|
| `rss_bytes` | プロセス物理メモリ（バイト） | `524288000` (500 MB) |
| `rss_source` | RSS のソース | `"procfs"` または `"resource_maxrss"` |
| `tracemalloc.enabled` | tracemalloc が実行中か | `true` / `false` |
| `tracemalloc.current_bytes` | 現在追跡中のメモリ（追跡中のみ） | `123456789` |
| `tracemalloc.peak_bytes` | ピークメモリ（追跡中のみ） | `234567890` |
| `gc.enabled` | GC が有効か | `true` / `false` |
| `gc.counts` | GC カウンタ（gen0, gen1, gen2） | `[150, 10, 2]` |
| `gc.stats` | 各世代 GC 統計 | 下表を参照 |

**GC stats フィールド**：

| フィールド | 説明 |
|------|------|
| `collections` | 該当世代の GC 回数 |
| `collected` | 回収されたオブジェクト数 |
| `uncollectable` | 回収不能なオブジェクト数（警告：メモリリークの可能性あり） |

### 2. メモリ追跡の開始（start）

Python の `tracemalloc` モジュールを有効にし、メモリ割り当ての追跡を開始します。

```bash
# デフォルト深度（25 層の呼び出しスタック）を使用
peeka-cli memory --action start

# カスタム呼び出しスタック深度（1-50）
peeka-cli memory --action start --nframe 50
```

**出力例**：

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc started successfully",
  "nframe": 25
}
```

**パラメータ説明**：

- `--nframe`：呼び出しスタック深度（1-50）、デフォルト 25
  - 深度が大きいほど追跡は詳細になりますが、オーバーヘッドが高くなります
  - 推奨値：本番環境は 25、開発デバッグは 50

**冪等性**：

tracemalloc が既に実行中の場合、再度 `start` を呼び出してもエラーになりません：

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc is already running",
  "was_already_running": true
}
```

**性能影響**：

- **オーバーヘッド**：約 5-10% の性能とメモリオーバーヘッド
- **推奨**：低負荷時に開始し、必要な期間だけ有効にすることを推奨

### 3. メモリ追跡の停止（stop）

`tracemalloc` を閉じて、追跡オーバーヘッドを解放します。

```bash
peeka-cli memory --action stop
```

**出力例**：

```json
{
  "status": "success",
  "action": "stop",
  "message": "tracemalloc stopped successfully",
  "was_running": true
}
```

**注意点**：

- ⚠️ **停止後にデータが失われる**：stop はすべての追跡データを消去します
- 📝 **先に出力してから停止**：データを保持する必要がある場合は、先に `dump` を実行してください
- ✅ **冪等操作**：実行中でなくても、stop はエラーになりません

```bash
# 正しいフロー：先に出力、次に停止
peeka-cli memory --action dump --filename production_snapshot
peeka-cli memory --action stop
```

### 4. Top N メモリ割り当ての表示（top）

最も多くのメモリを占有しているコード位置を表示します（**start が必要**）。

```bash
# top 20 割り当てを表示（デフォルトは行番号でグループ化）
peeka-cli memory --action top

# top 50 割り当てを表示
peeka-cli memory --action top --limit 50

# ファイル名でグループ化（どのモジュールが占有しているか確認）
peeka-cli memory --action top --group-by filename --limit 30
```

**出力例**（行番号でグループ化）：

```json
{
  "status": "success",
  "action": "top",
  "group_by": "lineno",
  "limit": 20,
  "total_size_bytes": 245760000,
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 24641536,
      "count": 1024,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 145}
      ]
    },
    {
      "rank": 2,
      "size_bytes": 15925248,
      "count": 512,
      "traceback": [
        {"filename": "/app/cache.py", "lineno": 89}
      ]
    }
  ]
}
```

**フィールド説明**：

| フィールド | 説明 |
|------|------|
| `rank` | ランキング（size_bytes 降順） |
| `size_bytes` | 該当割り当てポイントが占有する合計バイト数 |
| `count` | 割り当てブロックの数 |
| `traceback` | 呼び出しスタック（配列、最も古いものが先頭） |

**group-by モード比較**：

| モード | 説明 | 適用場面 |
|------|------|----------|
| `lineno` | コード行でグループ化 | 具体的なコード行の特定 |
| `filename` | ファイルでグループ化 | 問題のあるモジュールの特定 |

**例**（ファイル名でグループ化）：

```bash
peeka-cli memory --action top --group-by filename --limit 10
```

```json
{
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 104857600,
      "count": 5120,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 1}
      ]
    }
  ]
}
```

> 注意：filename でグループ化した場合、`lineno` フィールドは 1 になります（実際の意味はありません）

**エラー処理**：

追跡を開始せずに `top` を呼び出した場合：

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

### 5. メモリスナップショットの出力（dump）

現在のメモリスナップショットをファイルに保存します（**start が必要**）。

```bash
# 自動的にファイル名を生成（タイムスタンプ）
peeka-cli memory --action dump

# ファイル名を指定
peeka-cli memory --action dump --filename my_snapshot

# パス経路の保護あり（自動的に basename を抽出）
peeka-cli memory --action dump --filename "../etc/passwd"
# 実際の保存先：/tmp/passwd.snapshot
```

**出力例**：

```json
{
  "status": "success",
  "action": "dump",
  "file_path": "/tmp/peeka_dump_20260131_165420.snapshot",
  "size_bytes": 1048576
}
```

**ファイル形式**：

- **形式**：Python tracemalloc バイナリスナップショット（`.snapshot`）
- **読み込み**：`tracemalloc.Snapshot.load()` を使用して読み込み
- **位置**：`PEEKA_DUMP_DIR` 環境変数で指定されたディレクトリ、デフォルトは `/tmp`

**スナップショット内容**：

- ✅ 現在生存しているすべてのメモリ割り当て
- ✅ 各割り当てポイントの呼び出しスタック
- ✅ 割り当てサイズと数
- ❌ **増分ではない**：現在の時点の完全なスナップショット

**オフライン分析例**：

```python
import tracemalloc

# スナップショットを読み込み
snapshot = tracemalloc.Snapshot.load('/tmp/peeka_dump_20260131_165420.snapshot')

# 行番号でグループ化し、top 10 を表示
stats = snapshot.statistics('lineno')
for stat in stats[:10]:
  print(f"{stat.size / 1024 / 1024:.1f} MB - {stat.count} blocks")
  print(f"  {stat.traceback[0].filename}:{stat.traceback[0].lineno}")
```

**スナップショット比較**（増分分析）：

```python
# 2 つのスナップショットを読み込み
snapshot1 = tracemalloc.Snapshot.load('before.snapshot')
snapshot2 = tracemalloc.Snapshot.load('after.snapshot')

# 差分を計算
diff = snapshot2.compare_to(snapshot1, 'lineno')

# メモリ増加を表示
for stat in diff[:10]:
  print(f"{stat.size_diff / 1024 / 1024:+.1f} MB - {stat.filename}:{stat.lineno}")
```

**安全保護**：

- ✅ **パス経路走査防御**：自動的に `os.path.basename()` でファイル名を抽出
- ✅ **ディレクトリ制限**：`PEEKA_DUMP_DIR` または `/tmp` にのみ書き込み可能
- ✅ **自動拡張子**：ファイル名に自動的に `.snapshot` 接尾辞を追加

### 6. GC オブジェクト統計（gc）

各型のオブジェクト数を統計します（**start 不要**）。

```bash
# top 20 オブジェクト型を表示（デフォルト）
peeka-cli memory --action gc

# top 50 オブジェクト型を表示
peeka-cli memory --action gc --limit 50
```

**出力例**：

```json
{
  "status": "success",
  "action": "gc",
  "limit": 20,
  "total_objects": 1523891,
  "objects_by_type": [
    {"rank": 1, "type": "dict", "count": 345612},
    {"rank": 2, "type": "list", "count": 198234},
    {"rank": 3, "type": "tuple", "count": 156789},
    {"rank": 4, "type": "str", "count": 123456},
    {"rank": 5, "type": "function", "count": 89012},
    {"rank": 6, "type": "User", "count": 50000}
  ]
}
```

**フィールド説明**：

| フィールド | 説明 |
|------|------|
| `total_objects` | GC が追跡しているオブジェクトの総数 |
| `objects_by_type` | 数でソートされたオブジェクト型のリスト |
| `rank` | ランキング（count 降順、count が同じ場合は type 昇順） |
| `type` | オブジェクト型名（`type(obj).__name__`） |
| `count` | 該当型のオブジェクト数 |

**使用場面**：

- **メモリリーク調査**：オブジェクト数の異常な増加を発見
  ```bash
  # 例：50000 個の User オブジェクトが見つかった（解放されていない可能性）
  ```
- **オブジェクトライフサイクル分析**：オブジェクトの作成と破棄を観察
- **キャッシュ監視**：キャッシュオブジェクトが多すぎないか確認

**性能注意**：

- ⚠️ **オーバーヘッドが大きい**：`gc.get_objects()` はすべてのオブジェクトを返します（数百万になることもある）
- 📊 **本番環境では慎重に使用**：低負荷時または小さなトラフィック時に使用することを推奨
- ✅ **ハードリミットあり**：最大 100 項目までを返します（出力が大きくなりすぎるのを防止）

**top との違い**：

| 観点 | `top` コマンド | `gc` コマンド |
|------|-----------|----------|
| **start が必要** | ✅ は | ❌ 否 |
| **表示内容** | メモリ割り当ての**位置**（コード行） | オブジェクトの**型**の数 |
| **わかること** | どの行のコードがどれだけのメモリを割り当てたか | 特定の型のオブジェクトがいくつあるか |
| **わからないこと** | オブジェクトの型 | 各オブジェクトがどれだけのメモリを占めるか |
| **データソース** | `tracemalloc` | `gc.get_objects()` |


### 7. メモリスナップショット（snapshot）

後続の diff 比較のために、tracemalloc スナップショットをメモリ内に保存します（**start が必要**）。

```bash
# スナップショットを撮影（最大 2 個まで保存、FIFO）
peeka-cli memory --action snapshot
```

**出力例**：

```json
{
  "status": "success",
  "action": "snapshot",
  "snapshot_count": 1,
  "timestamp": 1738328400.0
}
```

**使用説明**：

- スナップショットは Agent のメモリ内に保存され（ディスクに書き込まれず）、最大 2 個まで保存可能
- 2 個を超えると、自動的に最も古いスナップショットが破棄されます（FIFO）
- `diff` と組み合わせて使用し、一定時間後のメモリ変化を分析するために使用
- スナップショットをディスクに永続化する場合は、`dump` を使用してください

### 8. スナップショット比較（diff）

最新の 2 つの snapshot のメモリ変化を比較します（**少なくとも 2 つの snapshot の撮影が必要**）。

```bash
# まず 2 つのスナップショットを撮影
peeka-cli memory --action snapshot
# ... しばらく待つ ...
peeka-cli memory --action snapshot

# 差分を比較
peeka-cli memory --action diff
```

**出力例**：

```json
{
  "status": "success",
  "action": "diff",
  "diffs": [
    {
      "location": "/app/models.py:145",
      "size_diff": 1048576,
      "size_new": 2097152,
      "size_old": 1048576,
      "count_diff": 512,
      "count_new": 1024,
      "count_old": 512
    },
    {
      "location": "/app/cache.py:89",
      "size_diff": -524288,
      "size_new": 524288,
      "size_old": 1048576,
      "count_diff": -256,
      "count_new": 256,
      "count_old": 512
    }
  ]
}
```

**フィールド説明**：

| フィールド | 説明 |
|------|------|
| `location` | コード位置（ファイル名:行番号） |
| `size_diff` | メモリサイズの変化（正 = 増加、負 = 減少） |
| `size_new` | 新しいスナップショットのメモリサイズ |
| `size_old` | 古いスナップショットのメモリサイズ |
| `count_diff` | 割り当てブロック数の変化 |
| `count_new` | 新しいスナップショットの割り当てブロック数 |
| `count_old` | 古いスナップショットの割り当てブロック数 |

**注意点**：

- 結果は `lineno` でグループ化され、最大 50 件まで返されます
- `size_diff > 0` はメモリの増加を示し、リーク調査の重点対象です
- `dump` によるオフライン比較と異なり、`diff` はオンラインで完了し、ファイルの出力は不要です

### 9. 参照者クエリ（referrers）

指定された型のオブジェクトを誰が保持しているか検索します（**start 不要**）。メモリリークを調査する際に、オブジェクトが誰に参照されているか追跡するのに適しています。

```bash
# dict 型のオブジェクトを参照している者を検索
peeka-cli memory --action referrers --type-name dict

# 再帰深度と階層ごとの数を増やす
peeka-cli memory --action referrers --type-name MyClass --max-depth 3 --max-per-level 15
```

**出力例**：

```json
{
  "status": "success",
  "action": "referrers",
  "target": {
    "type": "MyClass",
    "repr_short": "<MyClass object at 0x7f...>",
    "count": 500
  },
  "referrers": [
    {
      "type": "dict",
      "repr_short": "{'user': <MyClass object at 0x7f...>, ...}",
      "referrers": [
        {
          "type": "list",
          "repr_short": "[{'user': <MyClass ...>}, ...] (len=500)"
        }
      ]
    }
  ]
}
```

**パラメータ説明**：

| パラメータ | 説明 | 範囲 | デフォルト |
|------|------|------|--------|
| `--type-name` | 対象オブジェクトの型名 | 任意の型名 | **必須** |
| `--max-depth` | 再帰検索深度 | 1-3 | 2 |
| `--max-per-level` | 階層ごとの最大参照者数 | 1-20 | 10 |

**使用場面**：

- ある型のオブジェクト数が異常に増加した後、`referrers` を使用してこれらのオブジェクトを誰が保持しているか追跡
- `gc` コマンドと組み合わせて使用：まず `gc` で異常な型を発見し、次に `referrers` で参照連鎖を追跡

### 10. 被参照者クエリ（referents）

指定された型のオブジェクトが何を参照しているか検索します（**start 不要**）。オブジェクトの内部構造と保持関係を分析するのに適しています。

```bash
# dict 型のオブジェクトが参照しているものを検索
peeka-cli memory --action referents --type-name dict

# カスタム深度
peeka-cli memory --action referents --type-name MyCache --max-depth 3
```

**出力例**：

```json
{
  "status": "success",
  "action": "referents",
  "target": {
    "type": "MyCache",
    "repr_short": "<MyCache object at 0x7f...>",
    "count": 1
  },
  "referents": [
    {
      "type": "dict",
      "repr_short": "{'items': [...], 'max_size': 10000}",
      "referents": [
        {
          "type": "list",
          "repr_short": "[<Item ...>, <Item ...>, ...] (len=9500)"
        }
      ]
    }
  ]
}
```

**referrers との違い**：

| 観点 | `referrers` | `referents` |
|------|------------|------------|
| **方向** | 上向き：誰が私を参照しているか | 下向き：私が何を参照しているか |
| **用途** | リークの根本原因調査 | オブジェクト構造分析 |
| **典型的な問題** | なぜオブジェクトが回収されないのか？ | オブジェクト内部に何が保持されているのか？ |

## 完全な診断フロー

### シナリオ 1：メモリリーク調査

```bash
# 1. 現在のメモリ状態を確認
peeka-cli memory --action overview

# 2. GC 統計でオブジェクト数の異常を確認
peeka-cli memory --action gc --limit 50

# 3. 追跡を開始
peeka-cli memory --action start --nframe 50

# 4. しばらく待つ（問題を再現させる）
sleep 300  # 5 分

# 5. 最初のメモリスナップショットを撮影
peeka-cli memory --action snapshot

# 6. さらに待つ
sleep 300

# 7. 2 番目のメモリスナップショットを撮影
peeka-cli memory --action snapshot

# 8. オンラインで 2 つのスナップショットを比較（ファイル出力不要）
peeka-cli memory --action diff

# 9. top 割り当てホットスポットを表示
peeka-cli memory --action top --limit 30

# 10. 疑わしい型に対して参照連鎖を追跡
peeka-cli memory --action referrers --type-name MyClass --max-depth 3

# 11. スナップショットを出力してオフライン分析（任意）
peeka-cli memory --action dump --filename snapshot_leak

# 12. 追跡を停止
peeka-cli memory --action stop
```

### シナリオ 2：パフォーマンス最適化

```bash
# 1. 追跡を開始
peeka-cli memory --action start

# 2. 性能テストを実行
# ... ビジネス操作をトリガ ...

# 3. メモリホットスポットを表示（ファイルでグループ化）
peeka-cli memory --action top --group-by filename --limit 20

# 4. 具体的なコード行を表示（行番号でグループ化）
peeka-cli memory --action top --group-by lineno --limit 50

# 5. 追跡を停止
peeka-cli memory --action stop
```

### シナリオ 3：定期監視

```bash
#!/bin/bash
# 定期的なメモリスナップショットスクリプト

PID=12345
SNAPSHOT_DIR="/data/memory_snapshots"

# 追跡を開始（初回）
peeka-cli memory --action start

# 毎時間スナップショットを出力
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  peeka-cli memory --action dump --filename "snapshot_$timestamp"
  sleep 3600
done
```

## 出力フォーマット

すべての action は JSON 形式を返し、フィールドには以下が含まれます：

### 共通フィールド

| フィールド | 型 | 説明 |
|------|------|------|
| `status` | string | `"success"` または `"error"` |
| `action` | string | 実行された操作タイプ |
| `error` | string | エラーメッセージ（失敗時のみ） |

### エラーレスポンス例

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

## 性能影響

### tracemalloc オーバーヘッド

| シナリオ | オーバーヘッド | 説明 |
|------|------|------|
| **tracemalloc 未起動** | 0% | overview/gc に追加オーバーヘッドなし |
| **tracemalloc 起動（nframe=25）** | 5-8% | メモリ割り当てと呼び出しスタックを追跡 |
| **tracemalloc 起動（nframe=50）** | 8-12% | 深度のある呼び出しスタックでオーバーヘッドが大きくなる |
| **dump 操作** | < 1% | スナップショット出力の瞬間的なオーバーヘッド |
| **gc 操作** | 2-5% | すべてのオブジェクトを走査、瞬間的なオーバーヘッド |

### ベストプラクティス

1. **必要なときにだけ起動**：
   ```bash
   # ❌ 誤り：長期的に追跡を有効のままにする
   peeka-cli memory --action start
   # ... 永久に実行 ...

   # ✅ 正しい：短時間起動し、診断後にすぐ停止
   peeka-cli memory --action start
   sleep 300  # 5 分
   peeka-cli memory --action dump --filename snapshot
   peeka-cli memory --action stop
   ```

2. **適切な nframe を選択**：
   ```bash
   # 本番環境：デフォルト値 25 を使用
   peeka-cli memory --action start

   # 開発デバッグ：より深い呼び出しスタックを使用
   peeka-cli memory --action start --nframe 50
   ```

3. **低負荷時に gc を使用**：
   ```bash
   # gc 操作はオーバーヘッドが大きいので、低負荷時に実行することを推奨
   peeka-cli memory --action gc --limit 30
   ```

4. **定期的にスナップショットを出力**：
   ```bash
   # 1 時間ごとに出力し、傾向分析に使用
   while true; do
     peeka-cli memory --action dump --filename "snapshot_$(date +%H)"
     sleep 3600
   done
   ```

## 環境変数

| 変数 | デフォルト | 説明 |
|------|--------|------|
| `PEEKA_DUMP_DIR` | `/tmp` | スナップショットファイル保存ディレクトリ |

**例**：

```bash
# カスタムスナップショットディレクトリ
export PEEKA_DUMP_DIR=/data/peeka_dumps
peeka-cli memory --action dump
# ファイル保存先：/data/peeka_dumps/peeka_dump_*.snapshot
```

## よくある質問

### 1. dump が失敗："tracemalloc is not running"

**原因**：tracemalloc を起動せずに dump を実行した。

**解決**：

```bash
# 先に追跡を開始
peeka-cli memory --action start

# 次にスナップショットを出力
peeka-cli memory --action dump
```

### 2. top の結果が空

**考えられる原因**：

- 起動したばかりで、tracemalloc がまだ割り当てをキャプチャしていない
- プロセスのメモリ割り当てが少ない

**解決**：

```bash
# しばらく待ってから再度確認
peeka-cli memory --action start
sleep 60
peeka-cli memory --action top
```

### 3. dump ファイルが大きすぎる

**原因**：追跡時間が長すぎて、割り当て記録が多すぎる。

**解決**：

- 追跡時間を短くする（及时に stop する）
- nframe 深度を減らす
- 定期的に出力してからクリア（stop + start）

### 4. gc コマンドが遅い

**原因**：`gc.get_objects()` はすべてのオブジェクトを走査する必要がある。

**解決**：

- 低負荷時に実行する
- limit パラメータを減らす
- 頻繁な呼び出しを避ける

### 5. RSS と tracemalloc の数値に大きな差がある

**原因**：

- **RSS**：プロセスが占有する物理メモリ（コード、スタック、共有ライブラリを含む）
- **tracemalloc**：Python ヒープの割り当てのみを追跡

**正常な現象**：

```
RSS: 500 MB
tracemalloc: 200 MB  # Python オブジェクトのメモリだけ
```

**差異の原因**：

- 共有ライブラリ（numpy, torch など）
- C 拡張が直接割り当てたメモリ
- インタプリタ自身のメモリ
- スタックメモリ

### 6. dump ファイルはどこにある？

**デフォルトの位置**：`/tmp/peeka_dump_*.snapshot`

**検索方法**：

```bash
# 最新の dump ファイルを表示
ls -lt /tmp/peeka_dump_*.snapshot | head -1

# カスタムディレクトリ
export PEEKA_DUMP_DIR=/data/dumps
peeka-cli memory --action dump
ls -lt /data/dumps/
```

## 高度なテクニック

### 1. 自動化メモリ監視スクリプト

```bash
#!/bin/bash
# memory_monitor.sh - 自動メモリ監視

PID=$1
ALERT_THRESHOLD=1000000000  # 1GB

peeka-cli memory --action overview | \
  jq -r '.rss_bytes' | \
  while read rss; do
    if [ $rss -gt $ALERT_THRESHOLD ]; then
      echo "Alert: RSS > 1GB, capturing snapshot..."
      peeka-cli memory --action start
      sleep 30
      peeka-cli memory --action dump --filename "alert_$(date +%s)"
      peeka-cli memory --action stop
    fi
  done
```

### 2. メモリ増加率分析

```python
# analyze_growth.py
import json
import sys

snapshots = sys.argv[1:]  # 複数のスナップショットファイルパス

sizes = []
for snapshot in snapshots:
  data = json.load(open(snapshot))
  sizes.append(data['rss_bytes'])

# 増加率を計算
for i in range(1, len(sizes)):
  growth = (sizes[i] - sizes[i-1]) / sizes[i-1] * 100
  print(f"Snapshot {i}: +{growth:.2f}%")
```

### 3. Prometheus との統合

```python
# prometheus_exporter.py
from prometheus_client import Gauge
import subprocess
import json
import time

rss_gauge = Gauge('process_rss_bytes', 'Process RSS memory', ['pid'])
tracemalloc_gauge = Gauge('tracemalloc_bytes', 'Tracemalloc memory', ['pid', 'type'])

def collect_metrics(pid):
  result = subprocess.check_output(['peeka-cli', 'memory', '--action', 'overview'])
  data = json.loads(result)

  rss_gauge.labels(pid=pid).set(data['rss_bytes'])

  if data['tracemalloc']['enabled']:
    tracemalloc_gauge.labels(pid=pid, type='current').set(
      data['tracemalloc']['current_bytes']
    )
    tracemalloc_gauge.labels(pid=pid, type='peak').set(
      data['tracemalloc']['peak_bytes']
    )

while True:
  collect_metrics(12345)
  time.sleep(15)
```

## 参考資料

- [Python tracemalloc ドキュメント](https://docs.python.org/3/library/tracemalloc.html)
- [Python gc モジュールドキュメント](https://docs.python.org/3/library/gc.html)

- [Peeka アーキテクチャ設計](../architecture.md)
- [Peeka 開発ガイド](../ai-skill.md)

## 更新履歴

| バージョン | 日付 | 更新内容 |
|------|------|----------|
| 0.1.0 | 2026-01 | 初期バージョン、10 種類のメモリ操作をサポート |
