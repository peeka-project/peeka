#!/usr/bin/env python3
"""
诊断 Peeka attach 失败的问题
用法: python diagnose_attach.py <PID>
"""
import sys
import os
import subprocess
from pathlib import Path


def get_process_info(pid):
    """获取进程信息"""
    info = {}

    try:
        # 获取可执行文件路径
        exe_link = f"/proc/{pid}/exe"
        if os.path.exists(exe_link):
            info['exe'] = os.readlink(exe_link)

        # 获取命令行
        cmdline_file = f"/proc/{pid}/cmdline"
        if os.path.exists(cmdline_file):
            with open(cmdline_file, 'rb') as f:
                cmdline = f.read().decode('utf-8', errors='replace')
                info['cmdline'] = cmdline.replace('\0', ' ').strip()

        # 获取环境变量
        environ_file = f"/proc/{pid}/environ"
        if os.path.exists(environ_file):
            with open(environ_file, 'rb') as f:
                environ = f.read().decode('utf-8', errors='replace')
                env_dict = {}
                for line in environ.split('\0'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if 'PYTHON' in key or 'PATH' in key or 'VIRTUAL' in key:
                            env_dict[key] = value
                info['environ'] = env_dict

        # 获取内存映射
        maps_file = f"/proc/{pid}/maps"
        if os.path.exists(maps_file):
            with open(maps_file, 'r') as f:
                maps = f.read()
                # 查找 Python 相关的库
                python_maps = [line for line in maps.split('\n')
                              if 'python' in line.lower() or 'libpython' in line.lower()]
                info['python_maps'] = python_maps[:10]  # 只保留前10个

        # 检查进程状态
        status_file = f"/proc/{pid}/status"
        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                status = {}
                for line in f:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        status[key.strip()] = value.strip()
                info['status'] = {
                    'Name': status.get('Name', ''),
                    'State': status.get('State', ''),
                    'PPid': status.get('PPid', ''),
                    'Uid': status.get('Uid', ''),
                }

    except Exception as e:
        info['error'] = str(e)

    return info


def compare_python_versions(target_exe, current_exe):
    """比较两个 Python 版本"""
    print("\n=== Python 版本比较 ===")

    # 当前 Python
    print(f"\n当前 Python (Peeka):")
    print(f"  路径: {current_exe}")
    print(f"  版本: {sys.version}")
    print(f"  实际路径: {os.path.realpath(current_exe)}")

    # 目标 Python
    print(f"\n目标 Python (进程):")
    print(f"  路径: {target_exe}")

    # 检查是否是符号链接
    if os.path.islink(target_exe):
        real_path = os.path.realpath(target_exe)
        print(f"  实际路径: {real_path}")
    else:
        real_path = target_exe
        print(f"  实际路径: (same)")

    # 尝试获取目标 Python 的版本
    try:
        result = subprocess.run(
            [target_exe, '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"  版本: {result.stdout.strip() or result.stderr.strip()}")
    except Exception as e:
        print(f"  版本: (无法获取: {e})")

    # 比较
    current_real = os.path.realpath(current_exe)
    if current_real == real_path:
        print("\n✅ 两者使用相同的 Python 解释器")
        return True
    else:
        print("\n❌ 两者使用不同的 Python 解释器！")
        print(f"   当前: {current_real}")
        print(f"   目标: {real_path}")
        return False


def check_binary_compatibility(exe_path):
    """检查 Python 二进制的兼容性（用于 PEP 768）"""
    print("\n=== 二进制兼容性检查（PEP 768）===")

    try:
        # 检查是否有调试信息段
        result = subprocess.run(
            ['readelf', '-S', exe_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # 查找 .pyruntime 段
            has_pyruntime = '.pyruntime' in result.stdout
            has_debug_info = '.debug_info' in result.stdout
            has_symtab = '.symtab' in result.stdout

            print(f"  .pyruntime 段: {'✅ 存在' if has_pyruntime else '❌ 不存在'}")
            print(f"  .debug_info 段: {'✅ 存在' if has_debug_info else '⚠️  不存在'}")
            print(f"  .symtab 段: {'✅ 存在' if has_symtab else '⚠️  不存在（stripped）'}")

            if not has_pyruntime:
                print("\n  ⚠️  警告：没有找到 .pyruntime 段！")
                print("     这可能导致 PyRuntime 地址查找失败。")
                print("     可能原因：")
                print("     - Python 编译时未启用 PEP 768 支持")
                print("     - 二进制被 strip 移除了关键段")
        else:
            print("  ⚠️  无法读取 ELF 段信息（readelf 失败）")

    except FileNotFoundError:
        print("  ⚠️  readelf 未安装，无法检查二进制段")
        print("     安装: sudo apt-get install binutils")
    except Exception as e:
        print(f"  ⚠️  检查失败: {e}")

    # 检查 ASLR 状态
    try:
        with open('/proc/sys/kernel/randomize_va_space', 'r') as f:
            aslr = f.read().strip()
            print(f"\n  ASLR 状态: {aslr}")
            if aslr == '0':
                print("     ✅ ASLR 已禁用")
            elif aslr == '1':
                print("     ⚠️  ASLR 部分启用（保守模式）")
            elif aslr == '2':
                print("     ⚠️  ASLR 完全启用（完全随机化）")
                print("     这可能影响 PyRuntime 地址查找")
    except Exception as e:
        print(f"  ⚠️  无法检查 ASLR: {e}")


def check_permissions(pid):
    """检查权限"""
    print("\n=== 权限检查 ===")

    proc_dir = f"/proc/{pid}"

    # 检查是否可以读取
    readable = os.access(proc_dir, os.R_OK)
    print(f"可读取 /proc/{pid}: {readable}")

    # 检查 ptrace_scope
    ptrace_scope_file = "/proc/sys/kernel/yama/ptrace_scope"
    if os.path.exists(ptrace_scope_file):
        with open(ptrace_scope_file, 'r') as f:
            scope = f.read().strip()
            print(f"ptrace_scope: {scope}")
            if scope == '0':
                print("  ✅ 允许 ptrace (scope=0)")
            elif scope == '1':
                print("  ⚠️  受限的 ptrace (scope=1, 仅子进程)")
            else:
                print(f"  ❌ 严格限制 (scope={scope})")

    # 检查当前用户和目标进程用户
    current_uid = os.getuid()
    try:
        stat_info = os.stat(proc_dir)
        target_uid = stat_info.st_uid
        print(f"当前用户 UID: {current_uid}")
        print(f"目标进程 UID: {target_uid}")
        if current_uid == target_uid:
            print("  ✅ 用户相同")
        else:
            print("  ❌ 用户不同")
    except Exception as e:
        print(f"无法获取进程 UID: {e}")


def main():
    if len(sys.argv) < 2:
        print("用法: python diagnose_attach.py <PID>")
        sys.exit(1)

    pid = int(sys.argv[1])

    print(f"诊断进程 {pid} 的 attach 问题...")
    print("=" * 60)

    # 获取进程信息
    print("\n=== 进程信息 ===")
    info = get_process_info(pid)

    if 'error' in info:
        print(f"❌ 无法获取进程信息: {info['error']}")
        print("   进程可能不存在或无权限访问")
        sys.exit(1)

    print(f"可执行文件: {info.get('exe', 'N/A')}")
    print(f"命令行: {info.get('cmdline', 'N/A')}")

    if 'status' in info:
        print(f"进程名: {info['status'].get('Name', 'N/A')}")
        print(f"状态: {info['status'].get('State', 'N/A')}")

    if 'environ' in info and info['environ']:
        print("\nPython 相关环境变量:")
        for key, value in sorted(info['environ'].items()):
            print(f"  {key}={value}")

    if 'python_maps' in info and info['python_maps']:
        print(f"\nPython 库映射 (前10个):")
        for line in info['python_maps'][:5]:
            print(f"  {line}")
        if len(info['python_maps']) > 5:
            print(f"  ... 还有 {len(info['python_maps']) - 5} 个")

    # 比较 Python 版本
    target_exe = info.get('exe')
    if target_exe:
        same = compare_python_versions(target_exe, sys.executable)
        if not same:
            print("\n💡 建议: 使用目标进程相同的 Python 运行 Peeka:")
            print(f"   {target_exe} -m peeka.tui")

    # 检查权限
    check_permissions(pid)

    # 检查 PEP 768 支持
    print("\n=== PEP 768 支持 ===")
    has_remote_exec = hasattr(sys, 'remote_exec')
    print(f"当前 Python 支持 remote_exec: {has_remote_exec}")
    if not has_remote_exec:
        print("  ℹ️  将使用 GDB fallback 方法")

        # 检查 GDB
        import shutil
        gdb_path = shutil.which('gdb')
        if gdb_path:
            print(f"  ✅ GDB 可用: {gdb_path}")
        else:
            print("  ❌ GDB 不可用！请安装 GDB")
    else:
        # PEP 768 可用 - 检查二进制信息
        check_binary_compatibility(target_exe)

    print("\n" + "=" * 60)
    print("诊断完成")


if __name__ == '__main__':
    main()
