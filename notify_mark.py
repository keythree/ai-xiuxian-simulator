# -*- coding: utf-8 -*-
"""Notification hook：会话弹出权限确认/需要人工时，把 session 标记进 pending.json。
贴纸「历练动态」读它显示「⏸ 等你确认」。settle.py 在会话恢复结算时清除标记。"""
import json, sys
from pathlib import Path

PENDING = Path(__file__).resolve().parent / "pending.json"

def main():
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace").strip()
    hook = json.loads(raw) if raw else {}
    sid = hook.get("session_id")
    if not sid:
        return
    try:
        with open(PENDING, encoding="utf-8") as f:
            pending = json.load(f)
    except Exception:
        pending = {}
    from datetime import datetime
    pending[sid] = {"ts": datetime.now().strftime("%H:%M"),
                    "msg": str(hook.get("message", ""))[:80]}
    tmp = Path(str(PENDING) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False)
    tmp.replace(PENDING)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
