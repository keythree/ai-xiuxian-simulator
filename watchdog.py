# -*- coding: utf-8 -*-
"""AI修仙模拟器 护法模块（自动任务总监督）
每小时随数据源轮询运行。跨工具核对：所有 AI 工具的会话行为数据 + Windows 计划任务。
逻辑：对每个受监督任务，比对「今天到目前为止应执行的班次数」vs「行为数据里实际匹配到的会话数」，
实到少于应到即为阵法停转 → 红色弹窗示警 + 写护法日志。幂等去重，不重复报警。
配置在 watchdog-tasks.json（没有此文件则整个模块静默关闭——分发版群友默认无此功能）。
"""
import json, subprocess, sys
from pathlib import Path
from datetime import datetime
import core

WD_CONF = core.OUT_DIR / "watchdog-tasks.json"
WD_STATE = core.OUT_DIR / "watchdog-state.json"


def load_conf():
    if not WD_CONF.exists():
        return None
    with open(WD_CONF, encoding="utf-8") as f:
        return json.load(f)


def load_state():
    try:
        with open(WD_STATE, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {"reported": {}, "catches": 0}


def expected_runs(task, now):
    """今天到 now 为止，宽限已过的应执行班次数。"""
    wd = task.get("weekdays")
    if wd and now.isoweekday() not in wd:
        return 0
    grace = task.get("grace", None)
    n = 0
    for h in task["hours"]:
        due = now.replace(hour=h, minute=task.get("minute", 0), second=0, microsecond=0)
        g = grace if grace is not None else GRACE_MIN
        if (now - due).total_seconds() / 60 >= g:
            n += 1
    return n


def matched_today(task, ledger, today):
    """任务今天是否有任何活跃（定时任务会复用会话跨天追加，按活跃日判定，零误报优先）。"""
    kws = [k.lower() for k in task["match"]]
    for r in ledger:
        days = r.get("days") or [r.get("day")]
        if today not in days:
            continue
        fm = r.get("first_msg", "").lower()
        if any(k in fm for k in kws):
            return True
    return False


def check_schtask(entry):
    """Windows 计划任务探针：存在性 + 最近结果码。返回问题描述或 None。"""
    if not core.IS_WIN:
        return None
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", entry["task"], "/FO", "LIST", "/V"],
                           capture_output=True, timeout=30)
        if r.returncode != 0:
            return f"计划任务『{entry['task']}』不存在"
        out = r.stdout.decode("gbk", errors="replace")
        for line in out.splitlines():
            if "Last Result" in line or "上次结果" in line:
                code = line.split(":")[-1].strip()
                if code not in ("0", "267011"):  # 267011=尚未运行
                    return f"计划任务『{entry['task']}』上次结果码 {code}"
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def run(ledger):
    conf = load_conf()
    if not conf:
        return []
    global GRACE_MIN
    GRACE_MIN = conf.get("grace_minutes", 90)
    now = datetime.now(core.LOCAL_TZ)
    today = now.strftime("%Y-%m-%d")
    state = load_state()
    alerts = []

    for task in conf.get("tasks", []):
        exp = expected_runs(task, now)
        if exp == 0:
            continue
        if matched_today(task, ledger, today):
            continue
        key = f"{task['name']}@{today}"
        if state["reported"].get(key):
            continue
        state["reported"][key] = True
        state["catches"] = state.get("catches", 0) + 1
        alerts.append(f"⚠ 护法示警：阵法『{task['name']}』今日应运转 {exp} 次，全天未见踪影")

    for entry in conf.get("schtasks", []):
        prob = check_schtask(entry)
        if prob:
            key = f"schtask:{entry['task']}@{today}"
            if not state["reported"].get(key):
                state["reported"][key] = True
                state["catches"] = state.get("catches", 0) + 1
                alerts.append(f"⚠ 护法示警：{prob}")

    # 只保留今天的去重记录，防止无限膨胀
    state["reported"] = {k: v for k, v in state["reported"].items() if today in k}
    core.save_json(WD_STATE, state)

    if alerts:
        log_dir = Path(conf.get("log_dir", str(core.OUT_DIR)))
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / f"护法-{today}.md", "a", encoding="utf-8") as f:
                for a in alerts:
                    f.write(f"- {now.strftime('%H:%M')} {a}\n")
        except OSError:
            pass
    return alerts


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = run(core.load_ledger())
    print("\n".join(res) if res else "护法巡视完毕，诸阵运转如常。")
