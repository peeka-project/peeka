---
layout: default
title: インストールガイド
nav_order: 2
permalink: /installation
---

# インストールガイド
{: .no_toc }

様々な環境で Peeka をインストールして設定するためのガイドです。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## システム要件

### 基本要件

- **Python バージョン**: Python 3.9 以上
- **OS**: Linux（推奨）、macOS
- **権限**: ターゲットプロセスにアタッチする権限が必要（同じ UID または CAP_SYS_PTRACE）

### Python バージョン比較

| Python バージョン | アタッチメカニズム | 追加要件 |
|----------------|---------------------|---------|
| **3.14+** | PEP 768 `sys.remote_exec` | なし |
| **3.9-3.13** | GDB + ptrace フォールバック | GDB、python3-dbg、CAP_SYS_PTRACE |

---

## インストール方法

### pip でインストール（推奨）

#### ベーシックバージョン（CLI のみ）

```bash
pip install peeka
```

#### フルバージョン（TUI 含む）

```bash
pip install peeka[tui]
```

### uv でインストール

```bash
# ベーシックバージョン
uv pip install peeka

# フルバージョン（TUI 含む）
uv pip install "peeka[tui]"

# 開発環境（ソースコードから）
uv sync --dev
```

### ソースコードからインストール

```bash
# リポジトリをクローン
git clone https://github.com/wwulfric/peeka.git
cd peeka

# インストール（ベーシックバージョン）
uv pip install -e .

# インストール（TUI 含む）
uv pip install -e ".[tui]"

# 開発環境（全依存関係）
uv sync --dev
```

---

## Python < 3.14 の追加設定

Python 3.9-3.13 では、GDB と Python デバッグシンボルのインストールが必要です。

### Debian/Ubuntu

```bash
sudo apt-get update
sudo apt-get install gdb python3-dbg
```

### RHEL/CentOS/Fedora

```bash
sudo yum install gdb python3-debuginfo
```

### macOS

```bash
brew install gdb

# 初回使用時に GDB の権限承認が必要
# 参考: https://sourceware.org/gdb/wiki/PermissionsDarwin
```

---

## 権限設定

### Linux システム

#### 一時的に ptrace 制限を緩和（テスト用）

```bash
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

#### 永続的設定（本番環境推奨）

`/etc/sysctl.d/10-ptrace.conf` を編集：

```
kernel.yama.ptrace_scope = 1
```

設定を適用：

```bash
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### SELinux システム（Fedora/RHEL）

```bash
# SELinux の状態を確認
getenforce

# 一時的に ptrace を許可
sudo setsebool -P deny_ptrace off

# または特定のプロセス用に SELinux ポリシーを作成
```

### Docker コンテナ

Docker コンテナを起動するときに `--cap-add=SYS_PTRACE` パラメータを追加：

```bash
docker run --cap-add=SYS_PTRACE your-image
```

docker-compose.yml で設定する場合：

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

---

## インストールの確認

### バージョン確認

```bash
peeka-cli --version
```

### テスト実行

```bash
# デモアプリケーションを起動
python -m peeka.examples.demo --mode loop

# 別のターミナルでアタッチをテスト
peeka-cli attach <pid>
```

### 依存関係の確認

```bash
# Python バージョンを確認
python --version

# GDB の確認（Python < 3.14）
gdb --version

# Python デバッグシンボルの確認（Python < 3.14）
python -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
```

---

## よくある問題

### アタッチ失敗：権限がない

**エラーメッセージ**:
```
Error: Operation not permitted
```

**解決策**:
1. ターゲットプロセスと同じ UID を使用するか、sudo を使用することを確認
2. ptrace_scope の設定を確認
3. Docker の場合は CAP_SYS_PTRACE が追加されていることを確認

### Python < 3.14：デバッグシンボルが見つからない

**エラーメッセージ**:
```
Error: Python debugging symbols not found
```

**解決策**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### GDB のバージョンが古い

**エラーメッセージ**:
```
Error: GDB version 7.3+ required
```

**解決策**:
```bash
# GDB を更新
sudo apt-get update
sudo apt-get install --only-upgrade gdb

# またはソースから最新バージョンをコンパイル
```

### macOS: GDB の権限承認が必要

**エラーメッセージ**:
```
Error: Unable to find Mach task port for process-id
```

**解決策**:
[GDB on macOS](https://sourceware.org/gdb/wiki/PermissionsDarwin) を参照してコード署名の権限承認を行ってください。

---

## 次のステップ

インストールが完了したら、以下をご覧ください：

- [クイックスタート]({% link ja/quickstart.md %}) - 基本的な使い方を学ぶ
- [コマンドリファレンス]({% link ja/commands/index.md %}) - 使用可能なすべてのコマンドを確認
- [サンプルチュートリアル]({% link ja/examples.md %}) - 実際のユースケース

---

## ヘルプの取得

インストール中に問題が発生した場合：

1. [トラブルシューティング]({% link ja/troubleshooting.md %}) を確認
2. [GitHub Issues](https://github.com/wwulfric/peeka/issues) で質問
