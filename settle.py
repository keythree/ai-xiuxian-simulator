# -*- coding: utf-8 -*-
"""老BK AI升职记 实时结算器（由 Claude Code Stop hook 触发）。
stdin 收 hook JSON（session_id / transcript_path），秒级结算该会话，
升级或新勋章时弹游戏式桌面弹窗，并刷新面板。任何异常静默退出，绝不阻塞会话。
"""
import json, sys, subprocess
from pathlib import Path
import core

def main():
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace").strip()
    hook = json.loads(raw) if raw else {}
    tp = hook.get("transcript_path")
    if not tp or not Path(tp).exists():
        return
    fp = Path(tp)
    if fp.name.startswith("agent-"):
        return

    s = core.parse_session(fp)
    clear_pending(s["session"])
    if not s["first_ts"] or s["n_msgs"] < 2:
        return

    ledger = core.load_ledger()
    old_state = None
    if core.STATE.exists():
        with open(core.STATE, encoding="utf-8") as f:
            old_state = json.load(f)

    tc = core.template_counts_of([r for r in ledger if r["session"] != s["session"]])
    tc[s["first_msg"][:80]] += 1
    rec = core.judge(s, tc)
    ledger = [r for r in ledger if r["session"] != rec["session"]]
    ledger.append(rec)

    state = core.compute_state(ledger)
    core.save_json(core.LEDGER, ledger)
    core.save_json(core.STATE, state)
    core.render_dashboard(state, ledger)

    events = done_events(s, rec) + diff_events(old_state, state)
    if not core.notify_enabled():
        events = [e for e in events if "⚠" in e]
    if events:
        pop(events)


def done_events(s, rec):
    """长历练完成提醒：本轮（最后一条人话到最后活动）超过阈值的非自动会话。"""
    if rec["auto"] or not s.get("last_user_ts") or not s.get("last_ts"):
        return []
    min_sec = core._load_config().get("notify_min_seconds", 120)
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(s["last_user_ts"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(s["last_ts"].replace("Z", "+00:00"))
        dur = (t1 - t0).total_seconds()
    except ValueError:
        return []
    if dur < min_sec:
        return []
    mins = max(1, round(dur / 60))
    brief = (s.get("last_user_msg") or s.get("first_msg") or "")[:22]
    return [f"历练完成 · 用时 {mins} 分 · 得灵气 {round(rec['total_xp'])}", f"「{brief}」"]

def clear_pending(sid):
    """会话有了新的完整回复（Stop 触发结算）说明确认已解除，摘掉等待标记。"""
    p = core.OUT_DIR / "pending.json"
    try:
        with open(p, encoding="utf-8") as f:
            pending = json.load(f)
        if sid in pending:
            del pending[sid]
            core.save_json(p, pending)
    except Exception:
        pass


def diff_events(old, new):
    events = []
    if not old:
        return events
    if new["total_level"] > old.get("total_level", 0):
        events.append(f"修为精进 Lv{old.get('total_level')} → Lv{new['total_level']}")
    for j in core.JOBS:
        o, n = old.get("levels", {}).get(j, 1), new["levels"][j]
        if n > o:
            if core.band_index(n) > core.band_index(o):
                events.append(f"{j} 突破{core.REALMS[core.band_index(n)]}期！{core.title_of(j, n)}")
            elif core.realm_of(n) != core.realm_of(o):
                events.append(f"{j} 修至{core.realm_of(n)}！")
            else:
                events.append(f"{j} Lv{o} → Lv{n} · {core.title_of(j, n)}")
    old_badges = {b[0] for b in old.get("badges", [])}
    for b in new["badges"]:
        if b[0] not in old_badges:
            ico = b[3] + " " if len(b) > 3 else ""
            events.append(f"得{b[1]}机缘 · {ico}{b[0]} +{core.badge_reward(b[0], b[1])}灵气")
    return events

def pop(events):
    core.spawn_toast(events)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
