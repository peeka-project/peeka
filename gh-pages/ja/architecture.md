---
layout: default
title: アーキテクチャ
nav_order: 8
permalink: /architecture
---

# アーキテクチャ
{: .no_toc }

Peeka の設計哲学、アーキテクチャ、実装の詳細を深く掘り下げます。
{: .fs-6 .fw-300 }

## 目次
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 設計目標

Peeka Agent の設計はこれらのコア目標に従っています：

### 低い侵入性

エージェントはターゲットプロセスのパフォーマンスと機能に大きな影響を与えることなく実行されます。業界の経験から、本番環境診断ツールのパフォーマンスオーバーヘッドは**5%以内**に保つ必要があります。Peeka は慎重に設計されたデコレータインジェクションメカニズムとオブザベーションデータバッファリング戦略によって、ターゲットプロセスへの影響を最小限に抑えます。

### 高い信頼性

エージェントはさまざまな例外的な状況下でも安定した状態を維持し、自身のエラーによってターゲットプロセスをクラッシュさせたり異常な動作をさせたりしてはなりません。メモリ使用量、ファイルディスクリプタ、スレッドなどのシステムリソースの適切な解放を含むリソース管理の問題に特別な注意が払われており、リソースリークによる長期的な安定性の問題を回避します。

### リアルタイムパフォーマンス

診断データはクライアントにリアルタイムで送信でき、開発者はターゲットプロセスの動作の変化をすぐにオブザーブできます。これは断続的な問題を特定するために特に重要です。Peeka は Unix ドメインソケットを介したストリームベースの通信プロトコルを使用し、**ミリ秒レベル**のデータ送信レイテンシを実現しています。

### 拡張性

エージェントアーキテクチャは、既存のコードの大規模なリファクタリングを必要とせずに、新しい診断コマンドや機能拡張を簡単にサポートできます。モジュラー設計により、通信、コマンド実行、オブザベーションなどの関心事が分離され、明確に定義されたインターフェースを通じて相互作用します。

---

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│                        User Space                            │
│                                                               │
│  ┌──────────────┐                    ┌──────────────┐       │
│  │  CLI/TUI     │                    │ Target       │       │
│  │              │                    │ Process      │       │
│  │  - peeka-cli │                    │              │       │
│  │  - peeka     │                    │ ┌──────────┐ │       │
│  └──────┬───────┘                    │ │  Agent   │ │       │
│         │                            │ │ (injected)│ │       │
│         │ Unix Domain Socket         │ └────┬─────┘ │       │
│         │ /tmp/peeka_<pid>.sock      │      │       │       │
│         └────────────────────────────┼──────┘       │       │
│                                      │              │       │
│  │ AgentClient     │←────JSON────────┤ │ Commands │ │       │
│  │                 │                 │ │          │ │       │
│  │ - send_command  │                 │ │ - watch  │ │       │
│  │ - recv_response │                 │ │ - trace  │ │       │
│  └─────────────────┘                 │ │ - stack  │ │       │
│                                      │ │ - monitor│ │       │
│                                      │ │ - logger │ │       │
│                                      │ │ - memory │ │       │
│                                      │ │ - inspect│ │       │
│                                      │ │ - thread │ │       │
│                                      │ │ - top    │ │       │
│                                      │ │ - sc/sm  │ │       │
│                                      │ │ - reset  │ │       │
│                                      │ │ - detach │ │       │
│                                      │ └──────────┘ │       │
│                                      │              │       │
│                                      │ ┌──────────┐ │       │
│                                      │ │ Injector │ │       │
│                                      │ │          │ │       │
│                                      │ │ Function │ │       │
│                                      │ │ Wrapping │ │       │
│                                      │ └──────────┘ │       │
│                                      └──────────────┘       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Kernel Space                            │
│                                                               │
│  ┌──────────────────────────────────────────┐               │
│  │  Process Attachment                       │               │
│  │                                           │               │
│  │  Python 3.14+:  sys.remote_exec()        │               │
│  │  Python < 3.14: GDB + ptrace             │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## コアコンポーネント

### 1. プロセスアタッチメント (attach.py)

ターゲットプロセスに Agent コードをインジェクトする責任があります。

#### Python 3.14+

PEP 768 の `sys.remote_exec()` API を使用：

```python
import sys

# Agent コードをインジェクトして実行
sys.remote_exec(pid, agent_script_path)
```

**利点：**
- 公式サポート、安全で信頼性がある
- 外部依存関係なし (GDB)
- クロスプラットフォーム互換性

#### Python 3.9-3.13

GDB + ptrace フォールバックを使用：

```python
# 1. GDB がプロセスにアタッチ
gdb -p <pid>

# 2. GIL を取得
call PyGILState_Ensure()

# 3. Python コードを実行
call PyRun_SimpleString("exec(open('/path/agent.py').read())")

# 4. GIL を解放
call PyGILState_Release(gil_state)

# 5. デタッチ
detach
quit
```

**要件：**
- GDB 7.3+
- Python デバッグシンボル
- CAP_SYS_PTRACE パーミッション

### 2. Agent コア (agent.py)

ターゲットプロセスにインジェクトされるコアコードで、以下の責任があります：

#### ソケットサーバー

```python
import socket
import threading

class PeekaAgent:
    def __init__(self):
        self.socket_path = f"/tmp/peeka_{os.getpid()}.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(1)

    def start(self):
        # バックグラウンドスレッドで実行、メインスレッドをブロックしない
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
```

#### コマンドディスパッチング

```python
def _handle_command(self, command: dict) -> dict:
    cmd_type = command.get("command")
    handler = self.handlers.get(cmd_type)

    if handler:
        return handler.execute(command.get("params", {}))
    else:
        return {"status": "error", "error": f"Unknown command: {cmd_type}"}
```

#### リソース管理

- 固定サイズのオブザベーションデータバッファ（デフォルト 10000 エントリ）
- 期限切れのオブザベーションの自動クリーンアップ
- グレースフルなスレッドシャットダウン

### 3. デコレータインジェクター (injector.py)

ターゲット関数を動的にラップし、オブザベーションロジックを追加します。

#### 関数ラッピング

```python
class DecoratorInjector:
    def inject_function(self, func, observer):
        original_func = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # エントリオブザベーション
            if observer.at_enter:
                observer.on_enter(args, kwargs)

            try:
                # オリジナル関数を実行
                result = original_func(*args, **kwargs)

                # 成功オブザベーション
                if observer.at_exit:
                    observer.on_exit(result)

                return result
            except Exception as e:
                # 例外オブザベーション
                if observer.at_exception:
                    observer.on_exception(e)
                raise

        return wrapper
```

#### 安全な復元

```python
def restore_function(self, target):
    # オリジナル関数を復元
    if hasattr(target, '__wrapped__'):
        original = target.__wrapped__
        # 安全な置換（さまざまなエッジケースを処理）
        ...
```

### 4. クライアント (client.py)

Agent と通信するためのクライアントライブラリ。

#### 同期クライアント

```python
class AgentClient:
    def send_command(self, command: dict) -> dict:
        # コマンドを送信（長さプレフィックス + JSON）
        msg = json.dumps(command).encode()
        self.sock.sendall(len(msg).to_bytes(4, 'big') + msg)

        # レスポンスを受信
        length = int.from_bytes(self.sock.recv(4), 'big')
        response = self.sock.recv(length)
        return json.loads(response)
```

#### ストリーミングクライアント

```python
class StreamingAgentClient(AgentClient):
    def stream_observations(self):
        # ジェネレーター、リアルタイムでオブザベーションデータを受信
        while True:
            msg = self._recv_message()
            if msg.get("type") == "observation":
                yield msg
            elif msg.get("type") == "event":
                if msg["event"] == "watch_stopped":
                    break
```

### 5. コマンドシステム (commands/)

モジュラーコマンド実装。

#### ベースクラス

```python
class BaseCommand(ABC):
    def __init__(self, agent: "PeekaAgent"):
        self.agent = agent

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """コマンドを実行して結果を返す"""
        pass
```

#### コマンド登録

```python
def _register_handlers(self):
    from peeka.commands.watch import WatchCommand
    from peeka.commands.trace import TraceCommand
    # ... 循環依存を避けるために遅延インポート

    self.handlers = {
        "watch": WatchCommand(self),
        "trace": TraceCommand(self),
        # ...
    }
```

---

## 通信プロトコル

### メッセージフォーマット

すべてのメッセージは**長さプレフィックス + JSON** フォーマットを使用：

```
┌─────────────┬─────────────────────────┐
│  Length     │   JSON Payload          │
│  (4 bytes)  │   (variable length)     │
└─────────────┴─────────────────────────┘
```

### リクエストフォーマット

```json
{
  "command": "watch",
  "params": {
    "pattern": "module.func",
    "times": 10,
    "condition": "cost > 100"
  }
}
```

### レスポンスフォーマット

#### 成功レスポンス

```json
{
  "status": "success",
  "data": {
    "watch_id": "watch_001",
    "pattern": "module.func"
  }
}
```

#### エラーレスポンス

```json
{
  "status": "error",
  "error": "Cannot find target: invalid.pattern",
  "traceback": "..."
}
```

#### ストリーミングオブザベーション

```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "module.func",
  "args": [1, 2],
  "result": 3,
  "duration_ms": 0.123
}
```

---

## セキュリティメカニズム

### 1. 式の安全性 (safeeval/)

`simpleeval` ライブラリベースの安全な式評価。

#### AST ホワイトリスト

安全な AST ノードのみ許可：

```python
SAFE_NODES = {
    ast.Expression, ast.Compare, ast.BinOp, ast.UnaryOp,
    ast.Num, ast.Str, ast.NameConstant, ast.Name,
    ast.List, ast.Tuple, ast.Dict, ast.Subscript,
    # ... その他の安全なノード
}
```

#### 属性保護

危険な属性アクセスをブロック：

```python
UNSAFE_ATTRS = {
    '__class__', '__subclasses__', '__bases__',
    '__import__', '__builtins__', '__globals__'
}
```

#### 関数ブラックリスト

危険な関数を無効化：

```python
UNSAFE_FUNCTIONS = {
    'eval', 'exec', 'compile', 'open',
    '__import__', 'input', 'globals', 'locals'
}
```

### 2. リソース制限

#### メモリバッファリング

```python
class ObservationManager:
    def __init__(self, max_size=10000):
        self.buffer = collections.deque(maxlen=max_size)
```

#### タイムアウト制御

```python
@timeout(seconds=30)
def execute_command(command):
    # コマンド実行にはタイムアウト保護があります
    pass
```

### 3. 例外キャッチ

#### 3層保護

1. **コアモジュール**: 例外をスロー、高速に失敗
2. **コマンドレイヤー**: キャッチしてエラーディクショナリを返す
3. **エージェントレイヤー**: 最終保護、トレースバックを追加

```python
try:
    result = command.execute(params)
except Exception as e:
    result = {
        "status": "error",
        "error": str(e),
        "traceback": traceback.format_exc()
    }
```

---

## パフォーマンス最適化

### 1. デコレータインジェクション

- `functools.wraps` を使用してメタデータを保存
- ラッピングオーバーヘッドを最小化 (< 1%)
- 条件付きコンパイル（必要なときだけインジェクト）

### 2. sys.monitoring API (Python 3.12+)

trace コマンドは `sys.monitoring` API を使用：

```python
import sys

def trace_callback(code, instruction_offset, args):
    # 低オーバーヘッドイベントコールバック
    pass

sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "peeka")
sys.monitoring.register_callback(
    sys.monitoring.PROFILER_ID,
    sys.monitoring.events.CALL,
    trace_callback
)
```

**パフォーマンス比較：**
- `sys.monitoring`: < 5% オーバーヘッド
- `sys.settrace`: < 20% オーバーヘッド (Python 3.9-3.11)

### 3. ストリーミング送信

- ジェネレータを使用してメモリ蓄積を回避
- Unix ドメインソケット低レイテンシ送信
- JSON ストリーミングパーシング

---

## 拡張開発

### 新しいコマンドの追加

1. コマンドクラスを作成：

```python
# peeka/commands/mycommand.py
from peeka.commands.base import BaseCommand
from typing import Dict, Any

class MyCommand(BaseCommand):
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # コマンドロジックを実装
            result = self._do_work(params)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

2. Agent に登録：

```python
# peeka/core/agent.py
def _register_handlers(self):
    from peeka.commands.mycommand import MyCommand
    self.handlers["mycommand"] = MyCommand(self)
```

3. CLI インターフェースを追加：

```python
# peeka/cli/main.py
parser.add_subcommand("mycommand", help="My new command")
```

### 新しい TUI ビューの追加

1. ビュークラスを作成：

```python
# peeka/tui/views/myview.py
from textual.widgets import Static

class MyView(Static):
    def compose(self):
        yield Label("My View")
```

2. ショートカットを登録：

```python
# peeka/tui/screens/main.py
BINDINGS = [
    ("5", "show_myview", "My View"),
]
```

---

## 参考文献

- [PEP 768 - Safe External Debugger](https://peps.python.org/pep-0768/)
- [PEP 669 - Low Overhead Monitoring](https://peps.python.org/pep-0669/)
- [simpleeval Documentation](https://github.com/danthedeckie/simpleeval)
