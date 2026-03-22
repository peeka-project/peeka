---
layout: default
title: attach
parent: コマンドリファレンス
nav_order: 1
permalink: /commands/attach
---

# attach - ターゲットプロセスにアタッチ
{: .no_toc }

ターゲットの Python プロセスに Peeka Agent を注入し、診断チャネルを確立します。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 概要

`attach` コマンドは Peeka を使用する最初のステップです。ターゲットプロセスに Peeka Agent コードを注入し、Unix ドメインソケットサーバーを起動して、後続の診断コマンドのための通信チャネルを確立します。

### 仕組み

**Python 3.14+**:
- PEP 768 の `sys.remote_exec()` API を使用
- 安全、効率的、公式サポート

**Python 3.9-3.13**:
- GDB + ptrace メカニズムを使用
- 互換性フォールバックソリューション

---

## TUI での使用法

**起動時の TUI 自動アタッチ**: `peeka` コマンドを直接実行すると TUI が起動し、自動的にプロセスセレクタが表示されます：

1. `peeka` を実行（引数なし）
2. プロセスセレクタでターゲットプロセスを選択
3. Enter を押して自動アタッチしてメインインターフェースに入る

**TUI 機能**:
- リアルタイムプロセスリスト更新
- プロセスの PID、コマンドライン、CPU/メモリ使用量を表示
- 検索/フィルタリングをサポート（キーワードを入力してフィルタ）
- 権限を自動検証（PEP 768 または GDB の利用可能性を表示）

**CLI との同等性**: 以下の例はデモンストレーションのために CLI コマンドを使用しています。TUI はグラフィカルインターフェースで同じ機能を提供します。

## 構文

```bash
peeka-cli attach <pid> [options]
```

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|------|------|------|------|
| `pid` | int | ✅ | ターゲットプロセスの PID |

### オプション

| オプション | 説明 | デフォルト |
|------|------|--------|
| `--timeout` | アタッチタイムアウト（秒） | 30 |
| `--socket-dir` | ソケットファイルのディレクトリ | `/tmp` |

---

## 使用例

### 基本的なアタッチ

```bash
# プロセス 12345 にアタッチ
peeka-cli attach 12345
```

出力：
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"status","level":"info","message":"Using PEP 768 remote_exec"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_12345.sock"}}
```

### プロセス PID の検索

```bash
# ps を使用
ps aux | grep python

# pgrep を使用
pgrep -f "my_app.py"

# pidof を使用
pidof python3
```

### アタッチしてすぐにコマンドを実行

```bash
# アタッチしてすぐにオブザーブ
peeka-cli attach 12345 && peeka-cli watch "app.func"
```

---

## 権限要件

### Linux システム

#### 同じユーザー

最も簡単な方法は、Peeka を同じユーザーで実行することです：

```bash
# ターゲットプロセスも Peeka も user1 として実行
user1$ python my_app.py  # PID: 12345
user1$ peeka-cli attach 12345  # ✅ 成功
```

#### 異なるユーザー（sudo が必要）

```bash
# ターゲットプロセスは user1 で実行されているので sudo が必要
user1$ python my_app.py  # PID: 12345
user2$ sudo peeka-cli attach 12345  # ✅ 成功
```

#### ptrace_scope 設定

現在の設定を確認：
```bash
cat /proc/sys/kernel/yama/ptrace_scope
```

| 値 | 説明 | Peeka 利用可能性 |
|----|------|-------------|
| 0 | 制限なし（推奨されない） | ✅ すべてのユーザーがアタッチ可能 |
| 1 | 親子プロセスまたは CAP_SYS_PTRACE のみ | ✅ 推奨設定 |
| 2 | CAP_SYS_PTRACE のみ | ✅ sudo が必要 |
| 3 | 完全に無効 | ❌ 使用できない |

一時的な変更（テスト用）：
```bash
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

永続的な変更：
```bash
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

### Docker コンテナ

`SYS_PTRACE` ケーパビリティを追加する必要があります：

```bash
# コンテナ起動時に追加
docker run --cap-add=SYS_PTRACE your-image

# docker-compose.yml
services:
  app:
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

### SELinux システム

SELinux の状態を確認：
```bash
getenforce  # Enforcing, Permissive, Disabled
```

一時的に ptrace を許可：
```bash
sudo setsebool -P deny_ptrace off
```

---

## 出力フォーマット

### 成功レスポンス

```json
{
  "type": "success",
  "command": "attach",
  "data": {
    "pid": 12345,
    "socket": "/tmp/peeka_12345.sock",
    "python_version": "3.12.0",
    "attach_method": "remote_exec"
  }
}
```

### エラーレスポンス

```json
{
  "type": "error",
  "command": "attach",
  "error": "Operation not permitted: ptrace access denied"
}
```

---

## トラブルシューティング

### エラー: Operation not permitted

**原因**: 権限が不十分

**解決策**:
1. 同じユーザーまたは sudo を使用
2. ptrace_scope 設定を確認
3. SELinux 設定を確認

```bash
# プロセス所有者を確認
ps -o user= -p 12345

# sudo を使用
sudo peeka-cli attach 12345

# ptrace 制限を緩和（テスト用）
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

### エラー: Process not found

**原因**: PID が存在しないか既に終了している

**解決策**:
```bash
# プロセスが存在するか確認
ps -p 12345

# PID を再検索
pgrep -f "my_app.py"
```

### エラー: Python debugging symbols not found (Python < 3.14)

**原因**: Python デバッグシンボルが不足している

**解決策**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### エラー: GDB not found (Python < 3.14)

**原因**: GDB がインストールされていない

**解決策**:
```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb
```

### エラー: Timeout attaching to process

**原因**: アタッチがタイムアウトした（ターゲットプロセスがハングしている可能性）

**解決策**:
```bash
# タイムアウトを増やす
peeka-cli attach 12345 --timeout 60

# ターゲットプロセスの状態を確認
ps -p 12345 -o stat=
```

---

## セキュリティに関する考慮事項

### プロセス分離

- Peeka はローカルプロセスにのみアタッチ可能
- リモートアタッチはサポートされていない
- Unix ドメインソケットはローカルアクセスのみに制限されている

### 最小権限の原則

- 本番環境では同じユーザーを使用すべき
- root 権限の使用を避ける
- 診断が不要になったら速やかにデタッチする

### コードインジェクションのセキュリティ

- Agent コードは診断機能のみを実行
- ビジネスロジックを変更しない
- すべての注入は reset コマンドで元に戻すことができる

---

## 関連コマンド

- [detach]({% link ja/commands/detach.md %}) - プロセスからデタッチ
- [watch]({% link ja/commands/watch.md %}) - 関数呼び出しをオブザーブ
- [reset]({% link ja/commands/reset.md %}) - 拡張をリセット

---

## 参考文献

- [PEP 768 - Safe External Debugger](https://peps.python.org/pep-0768/)
- [Linux ptrace(2) Manual](https://man7.org/linux/man-pages/man2/ptrace.2.html)
- [Yama LSM Documentation](https://www.kernel.org/doc/html/latest/admin-guide/LSM/Yama.html)
