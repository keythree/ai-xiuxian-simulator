# -*- coding: utf-8 -*-
"""AI修仙模拟器 安装向导（双击 安装.bat 运行）
1. 取道号  2. 自动识别本机 AI 工具并结算历史  3. 挂每小时自动结算
4. 若装了 Claude Code，追加实时结算 hook（秒级突破弹窗）
"""
import json, sys, subprocess, shutil
from pathlib import Path
import core

def _clean(s):
    """清洗 Windows 控制台编码转换产生的非法字符，防止中文道号写入崩溃或存进垃圾名。"""
    s = s.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    s = s.replace("﻿", "").strip()
    if not s or all(c in "?？ \t" for c in s):
        return ""
    return s

def write_config(name):
    """写道号与默认配置（重装不刷新 install_date，防蹭紫气）。"""
    from datetime import datetime
    cfg = core._load_config()
    cfg["name"] = name
    cfg.setdefault("notify_min_seconds", 120)
    cfg.setdefault("notify_enabled", True)
    cfg.setdefault("install_date", datetime.now().strftime("%Y-%m-%d"))
    with open(core.CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg["name"]

def ask_name():
    if core.CONFIG.exists():
        cur = core.player_name()
        print(f"当前道号：{cur}")
        n = _clean(input("回车沿用，或输入新道号："))
        name = n or cur
    else:
        name = _clean(input("给自己取个道号（回车默认「无名道友」）：")) or "无名道友"
    return write_config(name)

def first_scan(log=print):
    sources = core.discover_sources()
    if not sources:
        log("！未发现任何 AI 工具数据（支持 Claude Code / Codex）。")
        log("  请先用一段时间 AI，再重新运行本安装。")
        return False
    log("识别到法器：" + "、".join(core.SRC_NAMES.get(s, s) for s, _f, _p in sources))
    extra = core.detect_unsupported()
    if extra:
        log("另发现尚未接入的法器：" + "、".join(extra) + "（双击「③帮我接入新工具」自动打包样本，发出来很快接入）")
    import scan
    sys.argv = [sys.argv[0]]
    scan.main()
    return True

def pythonw_path():
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else sys.executable)

def poll_cmd():
    """每小时轮询的命令（列表形式）。打包版调自身 exe，源码版调 pythonw。"""
    if core.FROZEN:
        return [sys.executable, "scan", "--notify"]
    return [pythonw_path(), str(Path(__file__).resolve().parent / "scan.py"), "--notify"]

LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.ai-xiuxian.poll.plist"

def install_schedule(log=print):
    cmd = poll_cmd()
    if core.IS_WIN:
        tr = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        r = subprocess.run(["schtasks", "/Create", "/TN", "AI修仙-数据源轮询", "/TR", tr,
                            "/SC", "HOURLY", "/F"], capture_output=True)
        log("每小时自动结算：" + ("已挂载" if r.returncode == 0 else "挂载失败（可跳过，手动重新结算也行）"))
    elif core.IS_MAC:
        args = "\n".join(f"      <string>{c}</string>" for c in cmd)
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.ai-xiuxian.poll</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>StartInterval</key><integer>3600</integer>
    <key>RunAtLoad</key><true/>
  </dict>
</plist>
"""
        try:
            LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
            LAUNCHD_PLIST.write_text(plist, encoding="utf-8")
            subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
            r = subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)], capture_output=True)
            log("每小时自动结算：" + ("已挂载" if r.returncode == 0 else "挂载失败（可跳过，手动重新结算也行）"))
        except Exception as e:
            log(f"每小时自动结算挂载失败（{e}），可跳过。")
    else:
        log("当前系统暂不支持自动挂载，请手动定时运行 scan --notify。")

def _ensure_hook(cfg, event, dedup_keys, entry):
    """往 settings.json 的指定 hook 事件里塞一条，已有同类则跳过。返回是否新增。"""
    groups = cfg.setdefault("hooks", {}).setdefault(event, [])
    for grp in groups:
        for h in grp.get("hooks", []):
            sig = str(h.get("args", [])) + str(h.get("command", ""))
            if any(k in sig for k in dedup_keys):
                return False
    if groups:
        groups[0].setdefault("hooks", []).append(entry)
    else:
        groups.append({"hooks": [entry]})
    return True

def install_claude_hook(log=print):
    """挂三条 Claude Code hook：
    Stop=实时结算 / Notification=「等你确认」标记 / SessionStart=自动拉起贴纸。"""
    settings = Path.home() / ".claude" / "settings.json"
    if not (Path.home() / ".claude").exists():
        log("未装 Claude Code，跳过实时挂钩（每小时结算已覆盖）。")
        return
    try:
        cfg = {}
        if settings.exists():
            shutil.copy2(settings, str(settings) + ".bak")
            with open(settings, encoding="utf-8") as f:
                cfg = json.load(f)
        here = Path(__file__).resolve().parent
        py = sys.executable.replace("pythonw.exe", "python.exe")

        def entry(args, timeout, msg):
            if core.FROZEN:
                return {"type": "command", "command": sys.executable, "args": args[1:] or args,
                        "async": True, "timeout": timeout, "statusMessage": msg}
            return {"type": "command", "command": py, "args": args,
                    "async": True, "timeout": timeout, "statusMessage": msg}

        added = []
        if _ensure_hook(cfg, "Stop", ["settle.py", "'settle'"],
                        entry([str(here / "settle.py")], 60, "修仙结算中")):
            added.append("实时结算")
        if _ensure_hook(cfg, "Notification", ["notify_mark"],
                        entry([str(here / "notify_mark.py")], 30, "标记等待")):
            added.append("等你确认标记")
        if _ensure_hook(cfg, "SessionStart", ["sticky", "stickyboot"],
                        entry([str(here / "app.py"), "stickyboot"], 30, "拉起贴纸")):
            added.append("贴纸自动跟随")
        if added:
            with open(settings, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            log("Claude Code 挂钩完成：" + "、".join(added) + "。")
        else:
            log("Claude Code 挂钩：全部已存在，跳过。")
    except Exception as e:
        log(f"Claude Code hook 挂载失败（{e}），每小时结算仍然有效。")

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 46)
    print("  AI修仙模拟器 · 安装")
    print("=" * 46)
    name = ask_name()
    print(f"\n道友 {name}，开始结算你的修行历史…\n")
    if not first_scan():
        return
    print()
    install_schedule()
    install_claude_hook()
    print("\n安装完成。桌面已生成：")
    print("  AI修仙模拟器.html（面板，随时双击看）")
    print("  出等级卡：python card.py（生成到桌面，直接发群）")
    try:
        import os
        os.startfile(str(core.DASHBOARD_PATHS[1]))
    except OSError:
        pass

if __name__ == "__main__":
    main()
