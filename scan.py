# -*- coding: utf-8 -*-
"""AI修仙模拟器 全量重建：自动发现本机全部 AI 工具数据源，重建台账/状态/面板。
用法:
  python scan.py            全量重建（不弹窗）
  python scan.py --notify   全量重建并对比旧状态，有突破/新机缘弹窗（供定时轮询非实时源）
"""
import sys, json, subprocess
from collections import defaultdict
import core

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    notify = "--notify" in sys.argv

    old_state = None
    if notify and core.STATE.exists():
        with open(core.STATE, encoding="utf-8") as f:
            old_state = json.load(f)

    sessions = []
    for src, files, parser in core.discover_sources():
        print(f"[{src}] 扫描 {len(files)} 个会话文件…")
        for i, fp in enumerate(files):
            try:
                s = parser(fp)
                if s["first_ts"] and s["n_msgs"] >= 2:
                    sessions.append(s)
            except OSError as e:
                print(f"  跳过 {fp.name}: {e}")
            if (i + 1) % 100 == 0:
                print(f"  …{i+1}/{len(files)}")

    tc = defaultdict(int)
    for s in sessions:
        tc[s["first_msg"][:80]] += 1
    ledger = [core.judge(s, tc) for s in sessions]
    state = core.compute_state(ledger)
    core.save_json(core.LEDGER, ledger)
    core.save_json(core.STATE, state)
    core.render_dashboard(state, ledger)

    print(f"\n修为 Lv{state['total_level']}（总灵气 {state['total_xp']}）")
    for j in core.JOBS:
        lv = state["levels"][j]
        print(f"  {j} Lv{lv} {core.realm_of(lv)}·{core.title_of(j, lv)} {round(state['job_xp'][j])} XP")
    src_count = defaultdict(int)
    for r in ledger:
        src_count[r.get("src", "claude-code")] += 1
    print(f"数据源: " + " · ".join(f"{k} ×{v}" for k, v in sorted(src_count.items())))
    extra = core.detect_unsupported()
    if extra:
        print("发现尚未接入的法器: " + "、".join(extra) + "（双击「③帮我接入新工具」自动打包样本，发出来很快接入）")
    print(f"机缘: {[b[0] for b in state['badges']]}")
    print(f"\n面板: {core.DASHBOARD_PATHS[1]}")

    if notify and old_state:
        import subprocess
        from pathlib import Path
        bk_sticky = Path(r"G:\claude code\tools\sticky_launch.py")
        if bk_sticky.exists():  # 作者本机跑私人贴纸，避免双贴纸
            try:
                subprocess.run([sys.executable, str(bk_sticky)], timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:  # 玩家机器：兜底拉起主界面贴纸（尊重当天手动关闭）
            try:
                py = Path(sys.executable)
                pyw = py.with_name("pythonw.exe")
                exe = str(pyw if core.IS_WIN and pyw.exists() else py)
                kw = {"creationflags": 0x00000208, "close_fds": True} if core.IS_WIN \
                    else {"start_new_session": True, "close_fds": True}
                subprocess.Popen([exe, str(Path(__file__).resolve().parent / "sticky.py"),
                                  "--follow"], **kw)
            except Exception:
                pass
        import settle
        events = settle.diff_events(old_state, state)
        try:
            import watchdog
            events += watchdog.run(ledger)
        except Exception:
            pass
        if not core.notify_enabled():
            events = [e for e in events if "⚠" in e]
        if events:
            settle.pop(events)
            print(f"弹窗事件: {events}")

if __name__ == "__main__":
    main()
