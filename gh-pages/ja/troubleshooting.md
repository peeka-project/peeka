---
layout: default
title: トラブルシューティング
nav_order: 9
permalink: /troubleshooting
---

# トラブルシューティング
{: .no_toc }

よくある問題とその解決策です。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## アタッチの問題

### エラー: Operation not permitted

**症状**:
```
Error: Operation not permitted: ptrace access denied
```

**原因**: 権限が不足していてターゲットプロセスにアタッチできません。

**解決策**:

#### 方法 1: 同じユーザーを使用

```bash
# ターゲットプロセスの所有者を確認
ps -o user= -p <pid>

# 同じユーザーで Peeka を実行
peeka-cli attach <pid>
```

#### 方法 2: sudo を使用

```bash
sudo peeka-cli attach <pid>
```

#### 方法 3: ptrace_scope を調整

```bash
# 現在の設定を確認
cat /proc/sys/kernel/yama/ptrace_scope

# 一時的に変更（テスト用）
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# 永続的に変更
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### 方法 4: SELinux 設定（RHEL/Fedora）

```bash
# SELinux の状態を確認
getenforce

# 一時的に ptrace を許可
sudo setsebool -P deny_ptrace off

# または SELinux ポリシーを作成
```

### エラー: Process not found

**症状**:
```
Error: Process 12345 not found
```

**原因**: PID が存在しないか、プロセスが既に終了しています。

**解決策**:

```bash
# プロセスが存在するか確認
ps -p 12345

# PID を再検索
ps aux | grep "your_app"
pgrep -f "your_app.py"
```

### エラー: Python debugging symbols not found (Python < 3.14)

**症状**:
```
Error: Python debugging symbols not found. Install python3-dbg.
```

**原因**: Python デバッグシンボルがインストールされていません（GDB フォールバック方式で必要）。

**解決策**:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install python3-dbg

# RHEL/CentOS/Fedora
sudo yum install python3-debuginfo

# インストールを確認
python3 -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
# True が出力されるはず
```

### エラー: GDB not found (Python < 3.14)

**症状**:
```
Error: GDB not found. Please install GDB.
```

**原因**: GDB がインストールされていません。

**解決策**:

```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb

# macOS
brew install gdb

# バージョンを確認（7.3+ が必要）
gdb --version
```

### エラー: Timeout attaching to process

**症状**:
```
Error: Timeout attaching to process after 30 seconds
```

**原因**:
1. ターゲットプロセスがハングして応答しない
2. アタッチのタイムアウト設定が短すぎる
3. システム負荷が高すぎる

**解決策**:

```bash
# 方法 1: タイムアウト時間を増やす
peeka-cli attach <pid> --timeout 60

# 方法 2: プロセスの状態を確認
ps -p <pid> -o stat=
# D: 割り込み不可能なスリープ（ハングしている可能性）
# R/S: 正常に実行中

# 方法 3: システム負荷を確認
top
uptime
```

---

## オブザベーションの問題

### オブザベーションデータが取得できない

**症状**: watch コマンドを起動しても、オブザベーションデータが出力されません。

**原因**:
1. 関数名のスペルが間違っている
2. 関数が呼び出されていない
3. 条件式が厳格すぎる
4. オブザベーション回数が上限に達している

**解決策**:

#### 関数名を確認

```bash
# sc/sm を使って正しい関数名を検索
peeka-cli sc "Calculator"
peeka-cli sm "add"

# 完全修飾名を使用
peeka-cli watch "demo.Calculator.add"  # ✅
peeka-cli watch "Calculator.add"        # ❌
```

#### 関数が呼び出されていることを確認

```bash
# ターゲットプロセスが実行中か確認
ps -p <pid>

# プロセスのログを確認
tail -f /var/log/your_app.log
```

#### 条件式を単純化する

```bash
# まず条件なしでオブザーブ
peeka-cli watch "demo.func" --times 5

# データがあることを確認してから条件を追加
peeka-cli watch "demo.func" --condition "cost > 100" --times 5
```

#### オブザベーション回数を増やす

```bash
# デフォルトは -1（無制限）
peeka-cli watch "demo.func"

# または明示的に指定
peeka-cli watch "demo.func" --times 100
```

### オブザベーションデータが不完全

**症状**: 観測されたパラメータまたは戻り値が `<truncated>` と表示されたり不完全です。

**原因**: 出力深度の制限。

**解決策**:

```bash
# 出力深度を増やす（デフォルトは 2）
peeka-cli watch "demo.func" --depth 5

# 深度の説明:
# 1: 型のみ表示
# 2: 1階層の構造を表示
# 5+: 深いネストを表示
```

### 条件式エラー

**症状**:
```
Error: Invalid condition expression: name 'invalid_var' is not defined
```

**原因**: 条件式に存在しない変数または安全でない関数が使用されています。

**解決策**:

#### 使用可能な変数

```bash
# ✅ 正しい変数
params      # パラメータリスト
kwargs      # キーワードパラメータ
returnObj   # 戻り値
throwExp    # 例外オブジェクト
cost        # 実行時間（ミリ秒）
target      # ターゲットオブジェクト（インスタンスメソッド）
```

#### 安全な関数

```bash
# ✅ 許可されている関数
len(), str(), int(), float(), bool()
type(), isinstance()
min(), max(), sum()

# ❌ 許可されていない関数
eval(), exec(), compile()
open(), read(), write()
__import__()
```

#### 例

```bash
# ✅ 正しい
--condition "len(params) > 2"
--condition "params[0] > 100 and cost > 50"
--condition "returnObj is not None"

# ❌ 間違い
--condition "my_var > 100"           # my_var が存在しない
--condition "eval('1+1')"            # eval は許可されていない
--condition "open('/etc/passwd')"    # open は許可されていない
```

---

## パフォーマンスの問題

### ターゲットプロセスが遅くなる

**症状**: Peeka をアタッチした後、ターゲットプロセスの応答が遅くなります。

**原因**:
1. trace コマンドのオーバーヘッドが大きい（Python < 3.12）
2. オブザベーション頻度が高すぎる
3. 出力深度が大きすぎる

**解決策**:

#### Python 3.12+ を使用

Python 3.12+ の trace コマンドは `sys.monitoring` API を使用し、オーバーヘッド < 5% です。

#### オブザベーション頻度を制限

```bash
# ✅ オブザベーション回数を制限
peeka-cli watch "func" --times 10

# ✅ 条件フィルタリングを使用
peeka-cli watch "func" --condition "cost > 100"

# ❌ 高頻度関数を無制限にオブザーブ
peeka-cli watch "high_frequency_func"
```

#### 出力深度を小さくする

```bash
# ✅ デフォルト深度を使用
peeka-cli watch "func"  # depth=2

# ❌ 大きすぎる深度
peeka-cli watch "func" --depth 10
```

#### 不要なオブザベーションを停止する

```bash
# watch を停止
peeka-cli reset "func"

# またはプロセスをデタッチ
peeka-cli detach <pid>
```

### Peeka クライアントの応答が遅い

**症状**: Peeka コマンドの実行が遅く、データ転送の遅延が大きい。

**原因**:
1. オブザベーションデータ量が大きすぎる
2. Unix Socket バッファがいっぱい
3. CPU 負荷が高すぎる

**解決策**:

```bash
# データ量を減らす
peeka-cli watch "func" --times 10 --condition "cost > 100"

# システムリソースを確認
top
df -h

# 古い socket ファイルをクリーンアップ
rm -f /tmp/peeka_*.sock
```

---

## 出力の問題

### JSON 解析エラー

**症状**:
```
Error: Expecting value: line 1 column 1 (char 0)
```

**原因**: 出力に JSON 以外のコンテンツ（print 文など）が含まれています。

**解決策**:

```bash
# JSON 行だけを抽出
peeka-cli watch "func" | grep '^{' | jq

# または Python でフィルタリング
peeka-cli watch "func" | python -c '
import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
        print(json.dumps(msg))
    except:
        pass
'
```

### 出力が文字化けする

**症状**: 出力に文字化けした文字が含まれています。

**原因**: エンコーディングの問題。

**解決策**:

```bash
# 正しい locale を設定
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# または Python で処理
peeka-cli watch "func" | python -c '
import sys
for line in sys.stdin:
    print(line, end="")
' 2>&1 | tee output.log
```

---

## Docker の問題

### Docker コンテナ内でアタッチできない

**症状**:
```
Error: Operation not permitted (Docker)
```

**原因**: コンテナに SYS_PTRACE ケーパビリティがありません。

**解決策**:

#### docker run

```bash
docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined your-image
```

#### docker-compose.yml

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

#### Kubernetes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    securityContext:
      capabilities:
        add: ["SYS_PTRACE"]
```

---

## TUI の問題

### TUI 表示が異常

**症状**: TUI 画面が乱れたり正常にレンダリングされません。

**原因**: ターミナルの互換性問題。

**解決策**:

```bash
# ターミナルが 256 色をサポートしているか確認
echo $TERM

# または CLI モードを使用
peeka-cli watch "func"
```

### Docker コンテナ内で TUI の色が異常

**症状**: `docker exec` でコンテナに入った後、TUI 画面の色が失われたり、Header/Footer と本体の色が区別できません。

**原因**: `docker exec` はホストのターミナル環境変数（`TERM`、`COLORTERM`）を継承しないため、コンテナ内ではデフォルトで `TERM=dumb` になり、Textual が truecolor サポートを検出できません。

**解決策**:

Peeka テストイメージには `TERM=xterm-256color` と `COLORTERM=truecolor` がビルトインされているので、`docker exec` でコンテナに入った後、TUI を追加設定なしで直接使用できます。

### TUI がフリーズする

**症状**: TUI 画面が応答しません。

**原因**:
1. データストリームが速すぎる
2. バックグラウンドスレッドがブロックされている

**解決策**:

```bash
# Ctrl+C で終了

# CLI を代替使用
peeka-cli watch "func" --times 10
```

---

## その他の問題

### Socket ファイルの衝突

**症状**:
```
Error: Address already in use: /tmp/peeka_12345.sock
```

**原因**: 前回の異常終了で socket ファイルがクリーンアップされていません。

**解決策**:

```bash
# 古い socket ファイルを削除
rm -f /tmp/peeka_12345.sock

# または別の socket ディレクトリを使用
peeka-cli attach 12345 --socket-dir /tmp/my_peeka
```

### メモリ使用量が高すぎる

**症状**: Peeka またはターゲットプロセスのメモリ使用量が高すぎる。

**原因**: オブザベーションデータバッファが大きすぎる。

**解決策**:

```bash
# オブザベーション回数を制限
peeka-cli watch "func" --times 100

# 定期的にオブザベーションをリセット
peeka-cli reset "func"

# または接続を切断
peeka-cli detach <pid>
```

### モジュールが見つからない

**症状**:
```
Error: No module named 'peeka'
```

**原因**: インストールの問題。

**解決策**:

```bash
# 再インストール
pip uninstall peeka
pip install peeka

# または uv を使用
uv pip install peeka

# インストールを確認
python -c "import peeka; print(peeka.__version__)"
```

---

## ヘルプの取得

上記の方法で問題が解決しない場合：

1. **ログを確認**:
   ```bash
   peeka-cli --verbose attach <pid>
   ```

2. **GitHub Issues**:
   [https://github.com/wwulfric/peeka/issues](https://github.com/wwulfric/peeka/issues)

3. **情報を提供**:
   - OS とバージョン
   - Python バージョン
   - Peeka バージョン
   - 完全なエラー情報
   - 再現手順

4. **コミュニティディスカッション**:
   - GitHub Discussions
   - Stack Overflow (タグ: `peeka`)

---

## 関連ドキュメント

- [インストールガイド]({% link ja/installation.md %})
- [クイックスタート]({% link ja/quickstart.md %})
- [コマンドリファレンス]({% link ja/commands/index.md %})
