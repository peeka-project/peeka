---
name: peeka-tui-screenshot
description: 在 Omarchy/Hyprland（0.56+，Lua 配置）上，用真实 kitty 窗口驱动 Peeka TUI 并截图验证，全程不切换用户焦点、工作区、显示器或光标。用于记录/验证 Peeka TUI 画面、像真实用户一样操作 TUI（按键、输入框、按钮）、在 peeka-test 容器中做视觉验证。
---

# Peeka TUI 截图（真实终端，不打扰用户）

## 原理

- **显示**：在隐藏的 special workspace `special:tui-<name>` 上用 `[workspace … silent; float; size W H]` 打开一个真实的 kitty（使用用户自己的 kitty 配置和 Omarchy 主题）。用户不切换到这个 workspace 就看不到它，焦点也不会变。
- **输入**：通过私有 unix socket 走 kitty 远程控制（`kitty @ send-text` / `send-key`）。按键经过 kitty 自己的编码，和真实用户的按键链路一致，不需要 tmux。
- **读取**：`kitty @ get-text` 拿屏幕文本做断言；`grim -T <stableId>` 截取窗口像素（grim ≥ 1.5 的 toplevel 截图）。隐藏窗口的第一帧可能滞后，脚本会连截两次取最后一张。
- 不需要建 headless 输出，不移动工作区，不碰 idle；显示器被 KVM 切走时也能截。

所有操作都用 `scripts/tui-agent.sh`（本 skill 自带，路径相对 skill 目录）。

## 核心规则

- 默认目标：`peeka-test:3.14` 容器（由 `$docker-build` 管理）里的 `examples/demo.py`。容器不在运行时先 `docker start peeka-test-3.14`。除非用户明确要求，否则不用本机 Python。
- 截图前写明：容器名 / 镜像 tag / Python 版本 / 目标 PID / 要截的视图。
- 前后各跑一次 `tui-agent.sh state`，确认 monitor / workspace / special / window 一致后才能报告完成。
- 不要用旧的 `hyprctl dispatch <name> <args>` 语法（Lua 配置下会报错），改用 `hl.dsp.*`；也不要用 `wtype` 或 `sendshortcut`（会作用到用户当前焦点）。
- 截图默认保存到会话 scratchpad 或 `/tmp`；声称成功前必须用视觉工具检查：视图正确、有主题色（不是灰阶）。
- 结束时 `tui-agent.sh stop <name>`（先发 `ctrl+q` 退出 TUI 再关窗口），除非用户要求保留窗口。只关 kitty 窗口不会结束容器里 `docker exec -it` 启动的进程（容器内收不到 SIGHUP，stdout 写入也照常成功），残留的 TUI 会一直 attach 着目标进程、持续轮询，干扰下一次验证的日志和连接数。收尾时检查：`docker exec peeka-test-3.14 sh -c 'ps -eo pid,args | grep "[p]eeka.tui"'` 应该为空。

## 流程

```bash
T=.agents/skills/peeka-tui-screenshot/scripts/tui-agent.sh
$T state                                  # 记录用户状态
docker start peeka-test-3.14
$T start p314 --size 1600x1000 -- docker exec -it peeka-test-3.14 python3 -m peeka.tui
$T wait p314 'demo\.py' 20                # 进程选择器出现
$T send p314 demo; $T key p314 enter     # 过滤只剩一个可 attach 进程时，Enter 直接 attach
$T wait p314 'Attached to PID' 30
$T shot p314 /tmp/peeka-dashboard.png
$T stop p314; $T state                    # 对比前后状态
```

## 键盘交互要点（2026-11-07 实测，已对应修复）

- **进程选择器**：过滤框里按 Enter，如果只剩一个可 attach 进程就直接 attach；剩多个时焦点移到表格，再按 Enter 选中高亮行。过滤框有内容时按 Esc 会清空过滤框，为空时 Esc 才退出。
- **切 tab**：数字键或字母键（见下方快捷键）只在焦点**不在**输入框时生效。切过去后焦点为空，按一次 `tab` 就进入该视图的第一个输入框（tab 栏不在焦点链里）。
- **输入框里按 Enter** 会启动当前视图的动作（Watch / Trace / Stack / Monitor / Inspect），和点按钮效果一样；同时会关闭自动补全下拉框。
- **输入框里按 Esc**：先关自动补全下拉框，再取消输入框焦点；焦点为空时再按 Esc 才是 Back（会 detach 并停止所有 watch/trace）。所以从输入框切到别的 tab 的方式是：先 `escape`，再按数字键。
- `tab` 之后先 `sleep 0.3` 再 `send`：文字比焦点切换先到时，字母会被当成 tab 快捷键（`t`、`p` 等）。
- 视图自己的绑定（Watch 的 `delete` = Stop All 等）只在焦点位于该视图内时生效；Esc 之后焦点为空，按了没反应。要停止就 Tab 到 Stop 按钮再 Enter。焦点在表格上时按 Esc 是 Back（会 detach），不是取消焦点。
- 输入前用 `text` 确认焦点和当前视图，不要盲目连续发送按键。

## 快捷键

主 tab：`1` Dashboard、`2` Watch、`3` Trace、`4` Stack、`5` Monitor、`6` Memory、`7` Logger、`8` Inspect、`9` Threads、`0` Top、`p` Profile、`t` Timeline；`esc`/`q` Back、`ctrl+q` 退出、`?` 帮助。以 `peeka/tui/screens/main.py` 的 `BINDINGS` 为准。

## 备选方案

- 需要固定分辨率的整屏截图：先 `hyprctl output create headless <n>`，再用 `hyprctl eval 'hl.monitor({output="<n>", mode="1920x1080@60", position="20000x20000", scale=1})'` 把它放到远处，`grim -o <n>` 截图，最后 `hyprctl output remove <n>`。存在期间物理屏的全局坐标会临时被 auto 布局挪开。
- 只要文本、不要像素：`herdr`（Omarchy 仓库已装，有 `pane send-keys / read / wait-output`）或 Textual `run_test()`（见 `$container-test`）。
