---
name: peeka-tui-screenshot
description: 指导智能体在 Omarchy/Hyprland 上使用 tmux 控制的 Peeka 会话和全局 omarchy-headless-screenshot skill 截取 Peeka TUI 截图。用于记录或验证 Peeka TUI 画面、在目标 workspace 打开或复用 Terminal、启动 `peeka`、导航 Peeka TUI 视图、填写输入框和操作按钮，并在不打扰用户当前可见 workspace 的情况下进行视觉验证。
---

# Peeka TUI 截图

使用这个 skill 准备 Peeka TUI 状态，通过全局 `$omarchy-headless-screenshot` skill 截图，并对生成图片做视觉验证。

通过 `tmux` 控制 Peeka，不使用 Wayland 键盘注入。Terminal 只负责显示 tmux 会话；智能体用 `tmux send-keys` 操作 TUI，因此不需要让 Terminal 窗口获得焦点。

## 核心规则

- 不要对非活动 workspace 使用 `grim -g <inactive-window-geometry>`；它会截取当前可见输出中对应几何区域，而不是非活动 workspace。
- 实际截图必须使用位于 `~/.codex/skills/omarchy-headless-screenshot` 的全局截图 skill。
- 除非用户要求生成项目资产，否则截图保存在 `/tmp`。
- 声称截图成功前，必须用可用的视觉工具检查生成图片。
- 如果切换过 Peeka tab，除非用户要求截取其他视图，否则用按键 `1` 恢复到 Dashboard。

## 查找或打开 Peeka TUI

发现已有 Peeka/Terminal 窗口：

```bash
hyprctl clients -j | jq -r '.[] | [.workspace.id,.address,.class,.title,(.at|join(",")),(.size|join("x"))] | @tsv'
```

如果已有窗口标题表明它是 Peeka（`Peeka`、`peeka`，或带 spinner 前缀的 `peeka`），并且位于目标 workspace，则优先复用该窗口。

推荐启动模式：

```bash
WS=3
SESSION=peeka-tui-shot

# 启动或复用一个运行 Peeka 的 detached tmux 会话。
tmux has-session -t "$SESSION" 2>/dev/null || \
  tmux new-session -d -s "$SESSION" "cd '$PWD' && uv run peeka"

# 在目标 workspace 的 Terminal 中显示该 tmux 会话，但不切换用户当前可见 workspace。
hyprctl dispatch exec "[workspace ${WS} silent] kitty --title ${SESSION} --directory '$PWD' bash -lc 'tmux attach -t ${SESSION}'"
```

注意：

- `peeka` 没有直接的 `--pid` 选项。如果出现进程选择器，输入 PID 或过滤词后按 Enter。
- 所有 TUI 交互都优先使用 `tmux send-keys`。不要依赖外部 `kitty @` 远程控制；它可能在非 TTY 智能体上下文中失败。
- Omarchy 自带的 TUI launcher 是 `omarchy-launch-tui <command>`，实现方式是 `setsid uwsm-app -- xdg-terminal-exec --app-id=org.omarchy.<command> -e <command>`。

## 导航 Peeka TUI

主界面 tabs：

| 按键 | 视图 |
|-----|------|
| `1` | Dashboard |
| `2` | Watch |
| `3` | Trace |
| `4` | Stack |
| `5` | Monitor |
| `6` | Memory |
| `7` | Logger |
| `8` | Inspect |
| `9` | Threads |
| `0` | Top |

常用视图快捷键：

| 视图 | 按键 |
|------|------|
| Dashboard | `r` 刷新，`c` 清空 activity log |
| Watch | `Enter` 开始，`Delete` 停止全部 |
| Trace | `Enter` 开始，`Delete` 停止全部，`c` 清空 tree |
| Stack | `Enter` 开始，`Delete` 停止全部 |
| Monitor | `Enter` 开始，`Delete` 停止全部 |
| Memory | `r` 刷新，`T` 切换 tracking |
| Logger | `r` 刷新 |
| Inspect | `Enter` inspect |
| Threads | `r` 刷新 |
| Top | `r` 重置 stats |

输入框和按钮操作策略：

- 尽量使用数字键切换视图。
- 使用 `tmux send-keys -t "$SESSION" 2` 切换到 Watch，`3` 切换到 Trace，`1` 切换到 Dashboard，依此类推。
- 使用 `tmux send-keys -t "$SESSION" Tab` 和 `tmux send-keys -t "$SESSION" BTab` 在输入框和按钮之间移动焦点。
- 使用 `tmux send-keys -t "$SESSION" 'module.Class.method'` 向输入框输入内容。
- 使用 `tmux send-keys -t "$SESSION" Enter` 点击按钮或提交输入。
- 使用 `tmux send-keys -t "$SESSION" Delete`、`Escape` 或 `C-q` 执行停止、返回或退出流程。

进程选择器 attach 示例：

```bash
tmux send-keys -t "$SESSION" "$PID" Enter
```

Watch 视图示例：

```bash
tmux send-keys -t "$SESSION" 2
tmux send-keys -t "$SESSION" 'demo.Calculator.add' Enter
```

## 截图流程

如果 workspace 已准备好，只需要截取简单截图：

```bash
~/.codex/skills/omarchy-headless-screenshot/scripts/capture-headless-workspace.sh \
  --workspace 3 \
  --output /tmp/peeka-tui-dashboard.png \
  --delay 1
```

然后检查 `/tmp/peeka-tui-dashboard.png`。

如果截图前需要交互式准备，先使用 `tmux send-keys`，等待 UI 稳定后再运行全局截图脚本。除非 tmux 不可用且已在一次性 Terminal 中验证替代方案，否则避免使用 `wtype` 和 Hyprland `sendshortcut`。

以全局截图 skill 的脚本作为安全处理和恢复 idle lock 的参考实现。

## 验证清单

- 项目内不能存在 `omarchy-headless-screenshot` 的副本；全局副本是唯一事实来源。
- 截图必须显示用户请求的 Peeka 视图，而不是用户当前可见的浏览器或视频 workspace。
- 任务结束后的 `hyprctl activeworkspace -j` 必须显示用户可见 workspace 已恢复。
- 如果截图工作开始前 `hypridle` 正在运行，结束后它也必须运行；如果开始前是停止状态，不要启动它。
