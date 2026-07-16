"""AI修仙模拟器 · 卸载：拆掉安装时放进系统的东西。

跑完之后把整个文件夹删掉，电脑上就不留任何痕迹了（修行数据也在文件夹里）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.ai-xiuxian.poll.plist"
HOOK_KEYS = ("settle.py", "notify_mark", "stickyboot")


def stop_sticky():
    """关掉正在运行的贴纸。"""
    try:
        if IS_WIN:
            import ctypes
            import ctypes.wintypes as w
            u = ctypes.windll.user32
            k = ctypes.windll.kernel32
            pids = []

            @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
            def cb(h, l):
                n = u.GetWindowTextLengthW(h)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(h, buf, n + 1)
                    if "AI修仙模拟器" in buf.value and "贴纸" in buf.value:
                        pid = w.DWORD()
                        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                        pids.append(pid.value)
                return True

            u.EnumWindows(cb, 0)
            for p in set(pids):
                h = k.OpenProcess(0x0001, False, p)
                if h:
                    k.TerminateProcess(h, 0)
                    k.CloseHandle(h)
            return "贴纸已关闭" if pids else "贴纸未在运行"
        subprocess.run(["pkill", "-f", "sticky.py"], capture_output=True)
        return "贴纸已关闭"
    except Exception as e:
        return f"关贴纸失败（{e}），不影响后续，重启电脑后它不会再出现"


def remove_schedule():
    """拆每小时轮询。"""
    try:
        if IS_WIN:
            r = subprocess.run(["schtasks", "/Delete", "/TN", "AI修仙-数据源轮询", "/F"],
                               capture_output=True)
            return "计划任务已删除" if r.returncode == 0 else "计划任务不存在（本来就没挂上）"
        if IS_MAC:
            subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
            if LAUNCHD_PLIST.exists():
                LAUNCHD_PLIST.unlink()
                return "后台轮询已卸载"
            return "后台轮询不存在（本来就没挂上）"
        return "非 Windows/Mac，无轮询可拆"
    except Exception as e:
        return f"拆轮询失败（{e}），可在系统的任务计划程序里手动删「AI修仙-数据源轮询」"


def strip_hooks():
    """从 Claude Code 的 settings.json 里摘掉本软件挂的钩子，别人的配置一律不动。"""
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        return "未装 Claude Code，无挂钩可摘"
    try:
        with open(settings, encoding="utf-8") as f:
            cfg = json.load(f)
        hooks = cfg.get("hooks", {})
        removed = 0
        for ev in list(hooks):
            groups = hooks[ev]
            for grp in groups:
                keep = []
                for h in grp.get("hooks", []):
                    sig = str(h.get("args", [])) + str(h.get("command", ""))
                    if any(k in sig for k in HOOK_KEYS) or str(HERE) in sig:
                        removed += 1
                    else:
                        keep.append(h)
                grp["hooks"] = keep
            hooks[ev] = [g for g in groups if g.get("hooks")]
            if not hooks[ev]:
                del hooks[ev]
        if removed:
            with open(settings, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        return f"已摘除 {removed} 条 Claude Code 挂钩" if removed else "未发现本软件的挂钩"
    except Exception as e:
        return f"摘挂钩失败（{e}），可手动编辑 ~/.claude/settings.json 删掉含 settle.py 的条目"


def remove_desktop_files():
    """删桌面面板。等级卡/周报图是你自己生成的分享图，保留不动。"""
    sys.path.insert(0, str(HERE))
    try:
        import core
        p = core.desktop_dir() / "AI修仙模拟器.html"
        if p.exists():
            p.unlink()
            return "桌面面板已删除"
        return "桌面面板不存在"
    except Exception as e:
        return f"删桌面面板失败（{e}），可手动删桌面上的 AI修仙模拟器.html"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 46)
    print("  AI修仙模拟器 · 卸载")
    print("=" * 46)
    print()
    for step in (stop_sticky, remove_schedule, strip_hooks, remove_desktop_files):
        print("· " + step())
    data_dir = Path.home() / ".ai-xiuxian"
    if data_dir.exists():
        ans = input(f"\n检测到修行数据目录 {data_dir}，一起删掉吗？(y=删 / 回车=保留) ").strip().lower()
        if ans == "y":
            import shutil
            shutil.rmtree(data_dir, ignore_errors=True)
            print("· 修行数据已删除")
        else:
            print("· 修行数据已保留（以后重装还能接着修）")
    print("\n卸载完成。最后一步：把这个文件夹整个删掉，就全部干净了。")


if __name__ == "__main__":
    main()
