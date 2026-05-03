---
layout: default
title: run コマンド
parent: コマンドリファレンス
nav_order: 14
---

# run コマンド
{: .no_toc }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}


## 概要

`run` コマンドは **Python スクリプトの起動時から Peeka を注入**します。対象プロセスがすでに実行中である必要はありません。**インポート時のコード**、**初期化ロジック**、または **短命なスクリプト** を観測する場合に最適です。

`attach` と異なり、`run` はスクリプトの最初の行から完全な診断能力を提供します。


## ユースケース

- **インポート時のロジック観測**：モジュールのロード、クラスの初期化など、起動時にのみ実行されるコードを捕捉
- **短命なスクリプト**：プロセスが終了するまでの時間が短く、手動 attach が間に合わない場合
- **バッチジョブ**：cronタスク、データパイプライン、ワンショットスクリプトの診断
- **CI/CD デバッグ**：コードを変更せずに自動化パイプラインで関数の動作を捕捉
- **起動時のバグ再現**：起動条件を正確に制御して、起動時にのみ発生する問題を再現

## コマンド形式

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

`--` は必須のセパレーターです。左側はスクリプトとその引数、右側は Peeka コマンドとそのオプションです。

### パラメーター

| パラメーター       | 説明                                         | デフォルト |
|--------------------|----------------------------------------------|-----------|
| `script`           | 実行する Python スクリプトのパス              | —         |
| `script_args`      | スクリプトに渡す引数（任意）                  | —         |
| `--`               | 必須のセパレーター                            | —         |
| `command`          | Peeka コマンド（watch / trace / stack）       | —         |
| `command_options`  | Peeka コマンドのオプション                    | —         |
| `--output-file`    | JSONL 出力をファイルに書き込む（stdout の代わり）| —      |

### サポートされるサブコマンド

| サブコマンド | 用途                                   |
|-------------|----------------------------------------|
| `watch`     | 関数呼び出しを観測（引数・戻り値・時間）|
| `trace`     | タイミング付きコールツリーを追跡        |
| `stack`     | 関数エントリ時にコールスタックを捕捉    |

## 使用例

### 例 1: 最もシンプルな使い方

```bash
peeka-cli run myscript.py -- watch "mymodule.MyClass.init_db"
```

スクリプト起動時から `init_db` メソッドを観測します。

### 例 2: スクリプト引数を渡す

```bash
peeka-cli run myscript.py --env production --config /etc/app.yml -- watch "mymodule.func"
```

`--env` と `--config` はスクリプトへ、`watch "mymodule.func"` は Peeka コマンドです。

### 例 3: コールツリーのトレース

```bash
peeka-cli run myscript.py -- trace "mymodule.func" -d 3
```

最大 3 層の深さで `mymodule.func` のコールツリーを追跡します。

### 例 4: 条件フィルター付き

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --condition "params[0] > 100"
```

最初の引数が 100 より大きい呼び出しのみ捕捉します。

### 例 5: ファイルへ出力

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --output-file observations.jsonl
```

全観測データを `observations.jsonl` に書き込みます。スクリプト自体の stdout には影響しません。

### 例 6: 観測回数の制限

```bash
peeka-cli run myscript.py -- watch "mymodule.func" -n 10
```

10 回捕捉後、自動的に観測を停止します。

### 例 7: コールスタックの捕捉

```bash
peeka-cli run myscript.py -- stack "mymodule.func" -n 3
```

`mymodule.func` のエントリ時にコールスタックを 3 回捕捉します。

## run と attach の違い

| 特徴                 | `run`                           | `attach`                        |
|----------------------|---------------------------------|---------------------------------|
| プロセス状態         | Peeka が起動                    | 実行中のプロセスに接続           |
| 観測範囲             | スクリプトの最初の行から         | attach 時点から                  |
| 最適な用途           | 短命なスクリプト、初期化ロジック | 長期間稼動するサービス           |
| 起動方法             | `peeka-cli run script.py -- …`  | `peeka-cli attach <pid>`        |
| ptrace/PEP768 必要   | 不要（直接注入）                | 必要                            |

## 注意事項

### ⚠️ `--` セパレーターは必須

```bash
# ✅ 正しい: -- でスクリプト引数と Peeka コマンドを分離
peeka-cli run myscript.py arg1 -- watch "mymodule.func"

# ❌ 誤り: -- がないと解析エラー
peeka-cli run myscript.py arg1 watch "mymodule.func"
```

### ⚠️ スクリプト終了時に観測も終了

スクリプトが終了（正常・異常いずれも）すると、観測は自動的に停止します。継続的な観測には、長期稼動プロセスへの `attach` を使用してください。

### ⚠️ --output-file は Peeka の出力のみに影響

`--output-file` は Peeka の JSONL 診断データのみを指定ファイルに書き込みます。スクリプト自身の stdout/stderr は影響を受けません。

## 関連コマンド

- [`attach`](attach.md) - 実行中のプロセスにアタッチ
- [`watch`](watch.md) - 関数呼び出しの観測
- [`trace`](trace.md) - コールツリーの追跡
- [`stack`](stack.md) - コールスタックの捕捉
