---
layout: default
title: AI エージェントスキル
nav_order: 7
permalink: /ai-skill
---

# AI エージェントスキル
{: .no_toc }

あなたの AI コーディングアシスタントが Peeka を使って Python アプリケーションを診断できるように教えます。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## peeka-diagnostics とは

`peeka-diagnostics` は **AI エージェントスキルファイル** (SKILL.md) です。インストールすると、あなたの AI コーディングアシスタント (OpenCode、Cursor、Cline など) は以下ができるようになります：

- **自動診断**: 観測された症状に基づいて適切な peeka コマンドを選択 (遅いリクエスト、メモリリーク、デッドロックなど)
- **診断の実行**: `peeka-cli` 経由で実行中の Python プロセスにアタッチしてリアルタイムでデータを収集
- **結果の解析**: 構造化された JSONL 出力を `jq` パイプラインで解析
- **プレイブックに従う**: 組み込みの診断ワークフローを適用 (パフォーマンス、例外、メモリ、スレッド)

このスキルは 14 個すべての Peeka CLI コマンドを網羅し、完全なフラグリファレンス、jq レシピ、条件式構文、安全プロトコルを含んでいます。

---

## スキル内容概要

### 診断決定木

スキルには症状からコマンドへのマッピングテーブルが含まれています。AI が自動的に適切な診断パスを選択します：

| 症状 | 推奨コマンド | ゴール |
|---------|---------------------|------|
| 遅いレスポンス / 高レイテンシ | `watch` → `trace` | 遅いサブコールを見つける |
| 間違った戻り値 / ロジックバグ | `watch` で I/O をオブザーブ | 入力を出力に相関付ける |
| 例外 / 予期しないエラー | `watch -e` → `stack` | 例外がどこでなぜ発生したかを見つける |
| メモリが大きい / メモリリーク | `memory` コマンドスイート | 何がメモリを確保して保持しているかを見つける |
| 高 CPU | `top` → `trace` | CPU を集中的に使っているコードパスを見つける |
| デッドロック / ハング | `thread` → `stack` | ロック競合ポイントを見つける |

### 4 つの診断プレイブック

| プレイブック | シナリオ | コアフロー |
|----------|----------|-----------|
| A: パフォーマンス | 遅い API、高レイテンシ | 遅い呼び出しをウォッチ → コールツリーをトレース → ボトルネックを特定 |
| B: 例外 | 本番環境エラー | `watch -e` でキャプチャ → コンテキスト用にスタック → 根本原因分析 |
| C: メモリ | メモリ使用量の増加 | メモリトラッキング開始 → スナップショット → 差分 → リファレンストレース |
| D: スレッド | デッドロック、スタックしたスレッド | スレッドリスト状態 → WAITING をフィルタ → スタック検査 |

### JSONL パーシング

すべての CLI 出力は JSONL です。AI は構造化分析のために `jq` を使用します：

```bash
# 遅い呼び出しをフィルタ
peeka-cli watch "module.func" -n 10 | jq 'select(.type == "observation" and .cost > 100)'

# 例外情報を抽出
peeka-cli watch "module.func" -e -n 5 | jq 'select(.success == false) | {func: .func_name, error: .exception}'

# メモリトップ分析
peeka-cli memory --action top | jq '.data.top_allocations[:5]'
```

---

## インストール

### 前提条件

- Peeka がインストールされていること ([インストールガイド](/installation) を参照)
- SKILL/SKILL.md ファイルをサポートする AI コーディングアシスタント

### 方法 1: プロジェクトレベルインストール (推奨)

スキルファイルをプロジェクトの `.agents/skills/` ディレクトリにコピー：

```bash
# プロジェクトルートから
mkdir -p .agents/skills/peeka-diagnostics

# Peeka リポジトリからスキルファイルをダウンロード
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

結果のディレクトリ構造：

```
your-project/
├── .agents/
│   └── skills/
│       └── peeka-diagnostics/
│           └── SKILL.md
├── src/
│   └── ...
└── ...
```

### 方法 2: グローバルインストール

AI ツールがグローバルスキルディレクトリをサポートしている場合 (例: `~/.config/opencode/skills/`):

```bash
mkdir -p ~/.config/opencode/skills/peeka-diagnostics
curl -o ~/.config/opencode/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

---

## 使い方

### OpenCode

OpenCode で `load_skills` 経由でスキルをロード：

```typescript
task(
  category="deep",
  load_skills=["peeka-diagnostics"],
  prompt="My API is slow, diagnose PID 12345 with peeka"
)
```

または会話の中で直接参照：

```
@peeka-diagnostics My Python service memory keeps growing, PID 54321, help me investigate
```

### その他の AI ツール

Cursor、Cline、その他カスタムインストラクションサポートのある AI ツールの場合：

1. スキルファイルが `.agents/skills/peeka-diagnostics/SKILL.md` にあることを確認
2. AI ツールが自動的に検出してロードします
3. Python 診断問題を説明すると、AI がスキルの知識を適用します

### トリガーキーワード

これらのキーワードが peeka-diagnostics スキルをアクティベートします：

- `debug python`, `diagnose python`
- `slow app`, `memory leak`, `high CPU`
- `trace function`, `watch expression`
- `thread deadlock`, `runtime debugging`
- `profile python`, `peeka`

---

## 例シナリオ

### シナリオ 1: 遅い API エンドポイント

> "`/api/users` エンドポイントが 50ms から 2s になりました、ターゲットプロセス PID は 12345 です"

AI は自動的に以下を行います：
1. `peeka-cli attach 12345`
2. `peeka-cli sc "*user*"` で関連するクラスを発見
3. `peeka-cli watch "myapp.api.users.get_users" -n 5 --condition "cost > 100"` で遅いリクエストをフィルタ
4. `peeka-cli trace "myapp.api.users.get_users" -n 3 -d 5` でコールツリーを分解
5. JSONL 出力を分析してボトルネックサブ関数を特定
6. `peeka-cli reset && peeka-cli detach` でクリーンアップ

### シナリオ 2: メモリリーク

> "Python サービスのメモリが 200MB から 2GB に数時間で成長しました、PID は 54321 です"

AI は自動的に以下を行います：
1. アタッチして tracemalloc トラッキングを開始
2. 間隔をあけて複数のスナップショットを取得して差分を取る
3. `memory --action top` を使用して最大の割り当てソースを見つける
4. `memory --action referrers` を使用して参照チェーンをトレース
5. 修正推奨とともに出力分析レポートを出力

### シナリオ 3: スレッドデッドロック

> "サービスがスタックしています、すべてのリクエストがタイムアウトしています、PID は 33333 です"

AI は自動的に以下を行います：
1. `peeka-cli thread` ですべてのスレッド状態をリスト
2. `WAITING` 状態のスレッドをフィルタ
3. 疑わしいスレッドの詳細なスタックトレースを取得
4. ロック競合を分析して推奨事項を提供

---

## スキルのメンテナンス

### 更新

Peeka が新しいバージョンをリリースしたら、スキルファイルを更新：

```bash
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

### カスタム拡張

スキルファイルはプレーン Markdown です — あなたのプロジェクトに合うように拡張してください：

- プロジェクト固有の診断パターンを追加
- よくウォッチされる関数パターンのショートカットを追加
- プロジェクト固有のトラブルシューティングステップを追加

---

## FAQ

### AI が診断に peeka を使ってくれません？

- スキルファイルが `.agents/skills/peeka-diagnostics/SKILL.md` に正しくインストールされていることを確認
- プロンプトで Python 診断キーワードを明示的に使用してください
- `peeka-cli --help` で peeka-cli がインストールされてアクセス可能であることを確認してください

### AI 診断コマンドが失敗します？

- Peeka のインストールを確認：`peeka-cli --help`
- ターゲットプロセスがまだ実行されていることを確認：`ps -p <pid>`
- パーミッションを確認 (ptrace_scope、CAP_SYS_PTRACE)

### スキルファイルはどこにありますか？

- **GitHub リポジトリ**: [peeka/.agents/skills/peeka-diagnostics/SKILL.md](https://github.com/wwulfric/peeka/tree/master/.agents/skills/peeka-diagnostics)
- **生のダウンロード URL**: `https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md`
