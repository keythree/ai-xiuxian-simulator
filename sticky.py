# -*- coding: utf-8 -*-
"""AI修仙模拟器 桌面贴纸 —— 主界面。
常驻桌面的无边框小窗：修仙状态栏 + 四页（阵法/历练/机缘/战报）。
- 历练页：今天亲手派的 AI 会话实时状态（⏸等你确认 / ◐运行中 / ✓已停）
- 阵法页：你自己的定时任务时点表（可选，配 watchdog-tasks.json 才有）
- 机缘页：已悟图鉴 + 未悟剪影
- 战报页：今日修行小结 + 看面板/出周报/重新结算按钮
拖顶栏移动，位置会记住。✕关闭后当天不再自动弹出。
"""
import json, os, sys, subprocess
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
import core

POS_FILE = core.OUT_DIR / ".sticky_pos.json"
DISMISS_FILE = core.OUT_DIR / ".sticky_dismissed.json"
CLOSED_MARK = core.OUT_DIR / ".sticky_closed"
SRC_DIR = Path(__file__).resolve().parent
WIN_TITLE = "AI修仙模拟器·贴纸"

FONT = "Microsoft YaHei UI" if core.IS_WIN else ("PingFang SC" if core.IS_MAC else "Noto Sans CJK SC")
MONO = "Consolas" if core.IS_WIN else "Menlo"
KAI = "KaiTi" if core.IS_WIN else "Kaiti SC"
EMOJI = "Segoe UI Emoji" if core.IS_WIN else "Apple Color Emoji"

C = dict(bg="#0e1116", card="#171b22", card2="#1d232c", line="#2a323d",
         txt="#e6edf3", dim="#8b949e", dimmer="#525b66",
         green="#3fb950", blue="#58a6ff", amber="#e3b341", done="#556070")
SPIN_FRAMES = "◐◓◑◒"

# 分享按钮图标：20px 曲线箭头（Segoe MDL2 EE35，系统分享/转发造型）
SHARE_ICON_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAYAAAAfSC3RAAAB4klEQVR4nHWSTWhTQRDHZ3Ze0pYKflLBUPygXjwIXhRFqJtaKQGrIpFCT3pW8CIePMSevHirp14EBQ9P8JCGWLzESC0UUSIeBAUPfc/vj5cENcHn7sisJrEhndPu/vnNzM5/ANYIBkBmwJW8vhTeG9vs3jinWrrqCTEg+FkFVwERYRck7KPKrfFBxBnLuQ7cAfws9RKCgp4NC/rFR390XSsxdqrklGR058r4YDX6laj/MOhZoqj5ub5+YOg2KdxhkyqTWjwc4f/Q+2J6ihScjw1vtAaQRUTJzooBg+Gt/WPhh8aN4cmHF7AFBQV9vT+pThtrrzQadgkS0BSOmKjeMLUNAzSnFOwhNhNDT8qfXMUwnz5u0d78+oVH9p0tV7v/GM6nrwHyyW+1+NDe6cVI/ugGYdFeBAuXBXpVnOgToVQa9aSbIK9nAXgqju3Bv5B0KL27KeImj7wlAXYvL8QiHNFlAzDDCLBCSe/AzlPlqu9nqTVAZ3Iwr58pa86lTujn7vGfCF3eSsL2AsiFgV8ahdMCvL6/nBA/V3nbBbUrhoWjIwy/Kx5hdlumVOy9hKujbcfbvD6W7FNzRPi4/tMsbG9uuYNn7pq1QAcJnJosPah9V/st8zsCyDyN3riJu73tEX8AA7PtY8c2pXIAAAAASUVORK5CYII=")


# ── 今日隐藏 ──
def load_dismissed():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(DISMISS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == today:
            return d
    except Exception:
        pass
    return {"date": today, "tasks": [], "sessions": []}


def save_dismissed(kind, key):
    d = load_dismissed()
    if key not in d[kind]:
        d[kind].append(key)
    try:
        with open(DISMISS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


# ── 台账缓存（一次渲染只读一遍磁盘，mtime 变了才重读）──
_LEDGER_CACHE = {"mtime": None, "data": []}


def read_ledger():
    try:
        mt = os.path.getmtime(core.LEDGER)
        if _LEDGER_CACHE["mtime"] != mt:
            with open(core.LEDGER, encoding="utf-8") as f:
                _LEDGER_CACHE["data"] = json.load(f)
            _LEDGER_CACHE["mtime"] = mt
        return _LEDGER_CACHE["data"]
    except Exception:
        return []


# ── 阵法时刻表（可选：读 watchdog-tasks.json，没有则阵法页显示引导）──
def load_tasks():
    try:
        with open(core.OUT_DIR / "watchdog-tasks.json", encoding="utf-8") as f:
            conf = json.load(f)
        out = []
        for t in conf.get("tasks", []):
            k = {"n": t["name"], "m": t.get("minute", 0), "h": t.get("hours", []),
                 "t": t.get("note", "阵法"), "s": "main"}
            if t.get("weekdays"):
                k["d"] = t["weekdays"]
            out.append(k)
        return out
    except Exception:
        return []


TASKS = load_tasks()


def load_cult():
    """修仙状态栏数据：(state, 今日灵气文本, 主修称号, (境界名,主色,深色))。"""
    try:
        with open(core.STATE, encoding="utf-8") as f:
            st = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        gain = 0.0
        for r in read_ledger():
            if r.get("day") == today:
                gain += r.get("total_xp", 0)
        levels = st["levels"]
        main_job = max(levels, key=lambda j: (levels[j], st["job_xp"].get(j, 0)))
        lv = levels[main_job]
        title = f"{core.realm_of(lv)}·{core.title_of(main_job, lv)}"
        rname, c1, c2, _glow, _fx = core.REALM_STYLE[core.band_index(lv)]
        streak = st.get("streak", 0)
        gain_txt = f"连修{streak}天 · 今日+{round(gain)}" if streak >= 2 else f"今日灵气 +{round(gain)}"
        if st.get("buff_days"):
            gain_txt = "✨" + gain_txt
        return st, gain_txt, title, (rname, c1, c2)
    except Exception:
        return None, None, None, None


def load_task_activity():
    try:
        with open(core.OUT_DIR / "watchdog-tasks.json", encoding="utf-8") as f:
            conf = json.load(f)
        ledger = read_ledger()
        act = {}
        for t in conf.get("tasks", []):
            kws = [k.lower() for k in t["match"]]
            slots = set()
            for r in ledger:
                fm = r.get("first_msg", "").lower()
                if any(k in fm for k in kws):
                    slots.update(r.get("dh", []))
            act[t["name"]] = slots
        return act
    except Exception:
        return None


def alive_session_ids():
    """Claude Code 会话注册表里进程仍存活的 sessionId 集合；探测不了返回 None 退回旧逻辑。"""
    if not core.IS_WIN:
        return None
    try:
        import glob as _g, ctypes
        ids = set()
        k32 = ctypes.windll.kernel32
        for f in _g.glob(str(Path.home() / ".claude" / "sessions" / "*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    d = json.load(fp)
                pid, sid = int(d.get("pid", 0)), d.get("sessionId")
                if not pid or not sid:
                    continue
                h = k32.OpenProcess(0x1000, False, pid)
                if h:
                    code = ctypes.c_ulong()
                    k32.GetExitCodeProcess(h, ctypes.byref(code))
                    k32.CloseHandle(h)
                    if code.value == 259:  # STILL_ACTIVE
                        ids.add(sid)
            except Exception:
                continue
        return ids
    except Exception:
        return None


def load_live_sessions(limit=10):
    """历练动态：今天活跃的亲手会话 + 状态。运行中=文件新鲜且进程真活着。"""
    try:
        import glob, time
        idx = {r["session"]: r for r in read_ledger()}
        try:
            with open(core.OUT_DIR / "pending.json", encoding="utf-8") as f:
                pending = json.load(f)
        except Exception:
            pending = {}
        now_ts = time.time()
        today0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        alive = alive_session_ids()
        rows = []
        for path in glob.glob(str(core.PROJECTS_DIR / "*" / "*.jsonl")):
            name = os.path.basename(path)
            if name.startswith("agent-"):
                continue
            mt = os.path.getmtime(path)
            if mt < today0:
                continue
            sid = name[:-6]
            rec = idx.get(sid)
            if rec and rec.get("auto"):
                continue
            fm = (rec or {}).get("first_msg", "") or "新历练"
            if fm.startswith("[定时任务]"):
                continue
            age = now_ts - mt
            proc_alive = (alive is None) or (sid in alive)
            if sid in pending and proc_alive:
                st, info = "pending", pending[sid].get("ts", "")
            elif age < 120 and proc_alive:
                st, info = "running", ""
            else:
                st, info = "idle", datetime.fromtimestamp(mt).strftime("%H:%M")
            rows.append((mt, fm[:21], st, info, sid))
        # Codex 会话（只扫今天的日期分片目录，Codex-only 用户历练页不空白）
        nowd = datetime.now()
        tdir = core.CODEX_DIR / f"{nowd:%Y}" / f"{nowd:%m}" / f"{nowd:%d}"
        for path in glob.glob(str(tdir / "*.jsonl")):
            mt = os.path.getmtime(path)
            if mt < today0:
                continue
            sid = os.path.basename(path)[:-6]
            rec = idx.get(sid)
            if rec and rec.get("auto"):
                continue
            fm = (rec or {}).get("first_msg", "") or "Codex 历练"
            age = now_ts - mt
            if age < 120:
                st, info = "running", ""
            else:
                st, info = "idle", datetime.fromtimestamp(mt).strftime("%H:%M")
            rows.append((mt, fm[:21], st, info, sid))
        dismissed = set(load_dismissed()["sessions"])
        rows = [r for r in rows if r[4] not in dismissed]
        rows.sort(key=lambda x: -x[0])
        return rows[:limit]
    except Exception:
        return []


def load_report():
    try:
        ledger = read_ledger()
        with open(core.STATE, encoding="utf-8") as f:
            st = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        rows = [r for r in ledger if r.get("day") == today]
        manual = [r for r in rows if not r.get("auto")]
        auto = [r for r in rows if r.get("auto")]
        gain = round(sum(r.get("total_xp", 0) for r in rows))
        job_gain = {}
        for r in manual:
            job_gain[r["job"]] = job_gain.get(r["job"], 0) + r.get("xp", 0)
        top = sorted(job_gain.items(), key=lambda x: -x[1])[:3]
        out = [
            ("今日灵气", f"+{gain}", C["green"]),
            ("亲身历练", f"{len(manual)} 场", C["txt"]),
            ("阵法运转", f"{len(auto)} 次", C["dim"]),
            ("连续修行", f"{st.get('streak', 0)} 天", C["amber"]),
        ]
        if st.get("buff_days"):
            out.append(("紫气东来", f"余 {st['buff_days']} 日", "#c792ea"))
        for j, v in top:
            if v > 0:
                out.append((f"　{j}道精进", f"+{round(v)}", C["blue"]))
        return out
    except Exception:
        return []


def slot_status(task, ft, now, activity):
    if ft > now:
        return "pending"
    if activity is None or task["n"] not in activity:
        return "done"
    day = ft.strftime("%Y-%m-%d")
    nxt = min([h for h in task["h"] if h > ft.hour], default=24)
    for h in range(ft.hour, nxt):
        if f"{day} {h:02d}" in activity[task["n"]]:
            return "done"
    if (now - ft).total_seconds() < 5400:
        return "running"
    return "missed"


def draw_medal(parent, realm, c1, c2, size=40):
    cv = tk.Canvas(parent, width=size, height=size, bg=C["card"], highlightthickness=0)
    k = 0.29 * size
    pts = [k, 1, size - k, 1, size - 1, k, size - 1, size - k,
           size - k, size - 1, k, size - 1, 1, size - k, 1, k]
    cv.create_polygon(pts, fill=c2, outline=c1, width=2)
    inset = 3.5
    ki = 0.29 * (size - 2 * inset)
    a, b = inset, size - inset
    pts_i = [a + ki, a, b - ki, a, b, a + ki, b, b - ki,
             b - ki, b, a + ki, b, a, b - ki, a, a + ki]
    cv.create_polygon(pts_i, fill="#12161d", outline="", width=0)
    cv.create_text(size / 2, size / 2, text=realm[0], fill=c1,
                   font=(KAI, int(size * 0.42), "bold"))
    return cv


def fire_times(task, d):
    if "d" in task and d.isoweekday() not in task["d"]:
        return []
    return [d.replace(hour=h, minute=task.get("m", 0), second=0, microsecond=0) for h in task["h"]]


def next_fire(task, now):
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for off in range(8):
        d = base + timedelta(days=off)
        ts = sorted([t for t in fire_times(task, d) if t >= now])
        if ts:
            return ts[0]
    return None


def fmt_cd(delta):
    s = max(0, int(delta.total_seconds()))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}时{m:02d}分"
    if m > 0:
        return f"{m}分{sec:02d}秒"
    return f"{sec}秒"


def rel_day(off):
    return "今天" if off == 0 else "明天" if off == 1 else f"{off}天后"


def spawn_tool(script, *args):
    """派生独立进程跑同目录工具脚本（出卡/周报/重扫），不阻塞贴纸。"""
    py = Path(sys.executable)
    if core.IS_WIN:
        pyw = py.with_name("pythonw.exe")
        exe = str(pyw if pyw.exists() else py)
        kw = {"creationflags": 0x00000008 | 0x00000200, "close_fds": True}
    else:
        exe = str(py)
        kw = {"start_new_session": True, "close_fds": True}
    try:
        subprocess.Popen([exe, str(SRC_DIR / script), *args], cwd=str(SRC_DIR), **kw)
    except Exception:
        pass


class Sticky:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(WIN_TITLE)
        self.root.overrideredirect(True)
        self.root.configure(bg=C["bg"])
        self.root.attributes("-alpha", 0.97)
        self.topmost = True
        self.root.attributes("-topmost", True)
        self.next_time = None
        self.next_name = None
        self.hero_cd = None
        self.row_cd = None
        self.sec = 0
        self.spin_vars = []
        self.spin_i = 0
        self.folded = False
        self.head_var = tk.StringVar(value="  AI修仙模拟器")
        self.fold_btn = None
        self._drag = (0, 0)
        self._place()
        self._build_frame()
        self.full_render()
        self.fast_tick()
        self.root.mainloop()

    def _place(self):
        W = 316
        try:
            with open(POS_FILE, encoding="utf-8") as f:
                p = json.load(f)
            x, y = p["x"], p["y"]
            self.tab = p.get("tab", "manual")
            if core.IS_WIN:
                # 记忆坐标已不在任何已连接显示器范围内（拔了副屏等）→ 重置回主屏
                import ctypes
                u = ctypes.windll.user32
                vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
                vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
                if not (vx - 60 <= x <= vx + vw - 60 and vy - 60 <= y <= vy + vh - 60):
                    raise ValueError("悬空坐标")
        except Exception:
            x = self.root.winfo_screenwidth() - W - 22
            y = 64
            self.tab = getattr(self, "tab", "manual")
        self.root.geometry(f"{W}x600+{x}+{y}")

    def _save_pos(self):
        try:
            with open(POS_FILE, "w", encoding="utf-8") as f:
                json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y(),
                           "tab": getattr(self, "tab", "manual")}, f)
        except Exception:
            pass

    def _build_frame(self):
        hd = tk.Frame(self.root, bg=C["card2"], height=34)
        hd.pack(fill="x")
        hd.pack_propagate(False)
        tk.Label(hd, textvariable=self.head_var, bg=C["card2"], fg=C["txt"],
                 font=(FONT, 10, "bold")).pack(side="left")
        self.clock_var = tk.StringVar(value="--:--:--")
        self.clock_lbl = tk.Label(hd, textvariable=self.clock_var, bg=C["card2"], fg=C["dim"],
                                  font=(MONO, 10))
        self.clock_lbl.pack(side="left", padx=8)
        try:
            self._share_img = tk.PhotoImage(data=SHARE_ICON_B64)
        except Exception:
            self._share_img = None
        for txt, cmd, fg in [("✕", self.close, "#ff7b72"), ("＿", self.toggle_fold, C["dim"]),
                             ("分享", self.card_menu, C["amber"]),
                             ("⟳", self.full_render, C["green"]), ("铃", self.toggle_notify, None)]:
            if txt == "分享" and self._share_img:
                b = tk.Label(hd, image=self._share_img, bg=C["card2"], cursor="hand2")
            elif txt == "分享":
                b = tk.Label(hd, text=txt, bg=C["card2"], fg=C["amber"],
                             font=(FONT, 9, "bold"), cursor="hand2")
            else:
                if txt == "铃":
                    fg = C["amber"] if self._notify_on() else C["dimmer"]
                b = tk.Label(hd, text=txt, bg=C["card2"], fg=fg, font=(FONT, 11), cursor="hand2")
            b.pack(side="right", padx=5)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            if txt == "＿":
                self.fold_btn = b
            if txt == "分享":
                self.card_btn = b
            if txt == "铃":
                self.bell_btn = b
        for w in (hd,):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        self.hero = tk.Frame(self.root, bg=C["card"])
        self.prog = tk.Frame(self.root, bg=C["bg"])
        if TASKS:
            self.hero.pack(fill="x", padx=10, pady=(10, 6))
            self.prog.pack(fill="x", padx=12)
        self.cult = tk.Frame(self.root, bg=C["card"])
        self.cult.pack(fill="x", padx=10, pady=(6, 0))
        self.tabbar = tk.Frame(self.root, bg=C["bg"])
        self.tabbar.pack(fill="x", padx=10, pady=(8, 0))
        self.tab_btns = {}
        for key, txt in [("manual", "历练"), ("auto", "阵法"), ("badges", "机缘"), ("report", "战报")]:
            b = tk.Label(self.tabbar, text=txt, font=(FONT, 9, "bold"), cursor="hand2",
                         padx=12, pady=4, bg=C["bg"], fg=C["dimmer"])
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self.tab_btns[key] = b
        self.live = tk.Frame(self.root, bg=C["bg"])
        self.body = tk.Frame(self.root, bg=C["bg"])
        self.badges_f = tk.Frame(self.root, bg=C["bg"])
        self.report_f = tk.Frame(self.root, bg=C["bg"])
        self._apply_tab()

    def _frames(self):
        return {"auto": self.body, "manual": self.live,
                "badges": self.badges_f, "report": self.report_f}

    def _apply_tab(self):
        frames = self._frames()
        if self.tab not in frames:
            self.tab = "manual"
        for k, b in self.tab_btns.items():
            b.config(bg=C["card2"] if k == self.tab else C["bg"],
                     fg=C["txt"] if k == self.tab else C["dimmer"])
        for k, f in frames.items():
            if k == self.tab:
                f.pack(fill="both", expand=True, padx=8, pady=(4, 8))
            else:
                f.pack_forget()

    def _switch_tab(self, k):
        if k == self.tab:
            return
        self.tab = k
        self._apply_tab()               # 先立刻换页换高亮（旧数据），手感即时
        self.root.update_idletasks()
        self._save_pos()
        self.full_render()              # 再刷数据

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
        self._save_pos()

    def compute(self, now):
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hidden = set(load_dismissed()["tasks"])
        slots = []
        for k in TASKS:
            if k["s"] != "main" or k["n"] in hidden:
                continue
            for ft in fire_times(k, today):
                slots.append((ft, k))
        slots.sort(key=lambda x: x[0])
        nxt_i = next((i for i, (ft, _) in enumerate(slots) if ft >= now), None)
        if nxt_i is not None:
            hero = slots[nxt_i]
        else:
            best = None
            for k in TASKS:
                if k["s"] != "main":
                    continue
                f = next_fire(k, now)
                if f and (best is None or f < best[0]):
                    best = (f, k)
            hero = best
        return slots, nxt_i, hero

    def full_render(self):
        now = datetime.now()
        for f in (self.hero, self.body, self.cult, self.live, self.badges_f, self.report_f):
            for w in f.winfo_children():
                w.destroy()
        for w in self.prog.winfo_children():
            w.destroy()

        # ── 阵法区（有时刻表才显示）──
        if TASKS:
            slots, nxt_i, hero = self.compute(now)
            total = len(slots)
            activity = load_task_activity()
            statuses = [slot_status(k, ft, now, activity) for ft, k in slots]
            done = sum(1 for st in statuses if st == "done")

            left = tk.Frame(self.hero, bg=C["card"])
            left.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            tk.Label(left, text="下一个任务", bg=C["card"], fg=C["green"],
                     font=(FONT, 8)).pack(anchor="w")
            if hero:
                ft, k = hero
                off = (ft.replace(hour=0, minute=0, second=0, microsecond=0)
                       - now.replace(hour=0, minute=0, second=0, microsecond=0)).days
                self.next_time = ft if nxt_i is not None else None
                self.next_name = k["n"]
                tk.Label(left, text=k["n"], bg=C["card"], fg=C["txt"],
                         font=(FONT, 14, "bold")).pack(anchor="w")
                tk.Label(left, text=f"{rel_day(off)} {ft:%H:%M} · {k['t']}", bg=C["card"], fg=C["dim"],
                         font=(FONT, 8)).pack(anchor="w")
                self.hero_cd = tk.StringVar(value=fmt_cd(ft - now))
                rt = tk.Frame(self.hero, bg=C["card"])
                rt.pack(side="right", padx=12)
                tk.Label(rt, textvariable=self.hero_cd, bg=C["card"], fg=C["green"],
                         font=(FONT, 15, "bold")).pack(anchor="e")
                tk.Label(rt, text="后开始", bg=C["card"], fg=C["dimmer"], font=(FONT, 7)).pack(anchor="e")
            else:
                self.next_time = None
                self.next_name = None
                self.hero_cd = None
                tk.Label(left, text="今日已全部触发 ✓", bg=C["card"], fg=C["txt"],
                         font=(FONT, 13, "bold")).pack(anchor="w")

            pct = round(done / total * 100) if total else 0
            cv = tk.Canvas(self.prog, height=6, bg=C["card"], highlightthickness=0)
            cv.pack(fill="x", pady=(2, 1))
            cv.update_idletasks()
            w = cv.winfo_width() or 292
            cv.create_rectangle(0, 0, w * pct / 100, 6, fill=C["green"], width=0)
            tk.Label(self.prog, text=f"今日进度 {done} / {total}", bg=C["bg"], fg=C["dim"],
                     font=(FONT, 8)).pack(side="left")
            tk.Label(self.prog, text=f"{pct}%", bg=C["bg"], fg=C["dim"],
                     font=(FONT, 8)).pack(side="right")
        else:
            slots, nxt_i, statuses = [], None, []
            self.next_time = self.next_name = self.hero_cd = None

        # ── 修仙状态栏 ──
        st, gain_txt, title, medal = load_cult()
        if st:
            wrap = tk.Frame(self.cult, bg=C["card"])
            wrap.pack(fill="x", padx=12, pady=8)
            if medal:
                mc = draw_medal(wrap, *medal)
                mc.pack(side="left", padx=(0, 10))
                mc.configure(cursor="hand2")
                mc.bind("<Button-1>", lambda e: self.make_card())
            right = tk.Frame(wrap, bg=C["card"])
            right.pack(side="left", fill="x", expand=True)
            top = tk.Frame(right, bg=C["card"])
            top.pack(fill="x", pady=(0, 2))
            tk.Label(top, text=f"修为 Lv {st['total_level']}", bg=C["card"], fg=C["amber"],
                     font=(FONT, 11, "bold")).pack(side="left")
            tk.Label(top, text=gain_txt, bg=C["card"], fg=C["green"],
                     font=(FONT, 8)).pack(side="right")
            mid_row = tk.Frame(right, bg=C["card"])
            mid_row.pack(fill="x")
            t_pct = min(st["total_in"] / max(st["total_need"], 1), 1.0)
            cv2 = tk.Canvas(mid_row, height=4, width=110, bg=C["card2"], highlightthickness=0)
            cv2.pack(side="left", pady=4)
            cv2.create_rectangle(0, 0, 110 * t_pct, 4, fill=C["amber"], width=0)
            tk.Label(mid_row, text=title, bg=C["card"], fg=C["blue"],
                     font=(FONT, 8)).pack(side="right")

        # ── 历练页 ──
        self.spin_vars = []
        live_rows = load_live_sessions(limit=10)
        tk.Label(self.live, text="今日历练", bg=C["bg"], fg=C["dimmer"],
                 font=(FONT, 7)).pack(anchor="w", padx=4, pady=(4, 2))
        if not live_rows:
            tk.Label(self.live, text="今日尚无亲身历练", bg=C["bg"], fg=C["dimmer"],
                     font=(FONT, 9)).pack(anchor="w", padx=8, pady=6)
        else:
            for _mt, fm, stx, info, sid in live_rows:
                row = tk.Frame(self.live, bg=C["bg"])
                row.pack(fill="x", pady=1)
                self._bind_dismiss(row, "sessions", sid, fm)
                if stx == "pending":
                    tk.Label(row, text="⏸", bg=C["bg"], fg="#ff9f43",
                             font=(FONT, 9, "bold"), width=2).pack(side="left")
                    tk.Label(row, text=fm, bg=C["bg"], fg=C["txt"], font=(FONT, 9, "bold"),
                             anchor="w").pack(side="left")
                    tk.Label(row, text=f"等你确认 {info}", bg=C["bg"], fg="#ff9f43",
                             font=(FONT, 8)).pack(side="right", padx=3)
                elif stx == "running":
                    sv = tk.StringVar(value=SPIN_FRAMES[0])
                    self.spin_vars.append(sv)
                    tk.Label(row, textvariable=sv, bg=C["bg"], fg=C["amber"],
                             font=(FONT, 9, "bold"), width=2).pack(side="left")
                    tk.Label(row, text=fm, bg=C["bg"], fg=C["txt"], font=(FONT, 9),
                             anchor="w").pack(side="left")
                    tk.Label(row, text="运行中", bg=C["bg"], fg=C["amber"],
                             font=(FONT, 8)).pack(side="right", padx=3)
                else:
                    tk.Label(row, text="✓", bg=C["bg"], fg=C["done"],
                             font=(FONT, 9), width=2).pack(side="left")
                    tk.Label(row, text=fm, bg=C["bg"], fg=C["dim"], font=(FONT, 9),
                             anchor="w").pack(side="left")
                    tk.Label(row, text=info, bg=C["bg"], fg=C["dimmer"],
                             font=(FONT, 8)).pack(side="right", padx=3)

        # ── 阵法页 ──
        if TASKS:
            tk.Label(self.body, text="今日固定时点", bg=C["bg"], fg=C["dimmer"],
                     font=(FONT, 7)).pack(anchor="w", padx=4, pady=(4, 2))
            self.row_cd = None
            for i, (ft, k) in enumerate(slots):
                row = tk.Frame(self.body, bg=C["bg"])
                row.pack(fill="x", pady=1)
                self._bind_dismiss(row, "tasks", k["n"], k["n"])
                stx = statuses[i]
                is_next = i == nxt_i
                if stx == "done":
                    dot, fg, fnt = C["done"], C["done"], (FONT, 9, "overstrike")
                elif stx == "running":
                    dot, fg, fnt = C["amber"], C["txt"], (FONT, 9, "bold")
                elif stx == "missed":
                    dot, fg, fnt = "#ff7b72", C["dim"], (FONT, 9)
                else:
                    dot = C["green"] if is_next else C["blue"]
                    fg, fnt = C["txt"], (FONT, 9, "bold" if is_next else "normal")
                tk.Label(row, text=f"{ft:%H:%M}", bg=C["bg"],
                         fg=(C["done"] if stx == "done" else C["dim"]),
                         font=(MONO, 9), width=5, anchor="w").pack(side="left")
                tk.Label(row, text="●", bg=C["bg"], fg=dot, font=(FONT, 7)).pack(side="left", padx=(0, 4))
                tk.Label(row, text=k["n"], bg=C["bg"], fg=fg, font=fnt, anchor="w").pack(side="left")
                if stx == "done":
                    tk.Label(row, text="✓", bg=C["bg"], fg=C["green"], font=(FONT, 8)).pack(side="right", padx=3)
                elif stx == "running":
                    sv = tk.StringVar(value=SPIN_FRAMES[0])
                    self.spin_vars.append(sv)
                    tk.Label(row, textvariable=sv, bg=C["bg"], fg=C["amber"],
                             font=(FONT, 10, "bold")).pack(side="right", padx=3)
                elif stx == "missed":
                    tk.Label(row, text="⚠", bg=C["bg"], fg="#ff7b72", font=(FONT, 8)).pack(side="right", padx=3)
                elif is_next:
                    self.row_cd = tk.StringVar(value=fmt_cd(ft - now))
                    tk.Label(row, textvariable=self.row_cd, bg=C["bg"], fg=C["green"],
                             font=(FONT, 8)).pack(side="right", padx=3)
        else:
            self.row_cd = None
            tk.Label(self.body, text="阵法监督（可选）", bg=C["bg"], fg=C["dimmer"],
                     font=(FONT, 7)).pack(anchor="w", padx=4, pady=(4, 2))
            tk.Label(self.body, text="如果你也让 AI 跑定时任务，\n照 watchdog-tasks.example.json\n建一份时刻表，这里就会出现\n实时执役状态和护法警报。",
                     bg=C["bg"], fg=C["dim"], font=(FONT, 9), justify="left",
                     anchor="w").pack(anchor="w", padx=8, pady=6)

        # ── 机缘页 ──
        st_data = st
        blist = (st_data or {}).get("badges", [])
        total_n = core.TOTAL_BADGES
        all_map = dict(core.ALL_BADGES)
        tk.Label(self.badges_f, text=f"已悟机缘 · {len(blist)} / {total_n}（滚动查看）",
                 bg=C["bg"], fg=C["dimmer"], font=(FONT, 7)).pack(anchor="w", padx=4, pady=(4, 2))
        bwrap = tk.Frame(self.badges_f, bg=C["bg"])
        bwrap.pack(fill="x")
        bcv = tk.Canvas(bwrap, bg=C["bg"], highlightthickness=0, height=400, width=284)
        bsb = tk.Scrollbar(bwrap, orient="vertical", command=bcv.yview, width=8)
        binner = tk.Frame(bcv, bg=C["bg"])
        binner.bind("<Configure>", lambda e: bcv.configure(scrollregion=bcv.bbox("all")))
        bcv.create_window((0, 0), window=binner, anchor="nw")
        bcv.configure(yscrollcommand=bsb.set)
        bcv.pack(side="left", fill="both", expand=True)
        bsb.pack(side="right", fill="y")

        def _bwheel(e):
            d = e.delta if core.IS_MAC else e.delta // 120
            bcv.yview_scroll(-1 * d, "units")
            return "break"

        def _badge_row(ico, bname, bdesc, fg, name_fg=None):
            row = tk.Frame(binner, bg=C["bg"])
            row.pack(fill="x", pady=1)
            w1 = tk.Label(row, text=ico, bg=C["bg"], fg=fg, font=(EMOJI, 13),
                          width=2, anchor="w")
            w1.pack(side="left", padx=(4, 2))
            w2 = tk.Label(row, text=bname, bg=C["bg"], fg=name_fg or fg, font=(FONT, 9, "bold"),
                          width=9, anchor="w")
            w2.pack(side="left", padx=(0, 4))
            w3 = tk.Label(row, text=bdesc, bg=C["bg"], fg=C["dim"], font=(FONT, 8), anchor="w")
            w3.pack(side="left")
            for w in (row, w1, w2, w3):
                w.bind("<MouseWheel>", _bwheel)

        unlocked = set()
        for item in blist:
            try:
                bname, bkind, bdesc = item[0], item[1], item[2]
            except (IndexError, TypeError):
                continue
            unlocked.add(bname)
            fg = ("#ff8c5a" if bkind == "仙缘" else
                  "#c792ea" if bkind == "隐藏" else
                  "#7fd8d4" if bkind in ("奇遇", "首次") else C["amber"])
            _badge_row(item[3] if len(item) > 3 else "·", bname, bdesc, fg)
        for bname, bkind in all_map.items():
            if bname in unlocked:
                continue
            _badge_row("？", "？？？", f"未悟 · {bkind}机缘，条件自行参悟", C["dimmer"])
        bcv.bind("<MouseWheel>", _bwheel)
        binner.bind("<MouseWheel>", _bwheel)

        # ── 战报页 ──
        tk.Label(self.report_f, text="今日战报", bg=C["bg"], fg=C["dimmer"],
                 font=(FONT, 7)).pack(anchor="w", padx=4, pady=(4, 2))
        rp = load_report()
        if rp:
            for label, val, fg in rp:
                row = tk.Frame(self.report_f, bg=C["bg"])
                row.pack(fill="x", pady=2)
                tk.Label(row, text=label, bg=C["bg"], fg=C["dim"], font=(FONT, 9),
                         anchor="w").pack(side="left", padx=(4, 0))
                tk.Label(row, text=val, bg=C["bg"], fg=fg, font=(FONT, 9, "bold")).pack(side="right", padx=6)
        else:
            tk.Label(self.report_f, text="今日尚无修行记录", bg=C["bg"], fg=C["dimmer"],
                     font=(FONT, 9)).pack(anchor="w", padx=8, pady=6)
        acts = tk.Frame(self.report_f, bg=C["bg"])
        acts.pack(fill="x", pady=(10, 2))
        for txt, cb in [("看面板", self.open_dash), ("出周报", self.make_weekly), ("重新结算", self.rescan)]:
            b = tk.Label(acts, text=txt, bg=C["card2"], fg=C["txt"], font=(FONT, 9, "bold"),
                         padx=10, pady=5, cursor="hand2")
            b.pack(side="left", padx=4)
            b.bind("<Button-1>", lambda e, c=cb: c())

        if not self.folded:
            self._apply_tab()
            self.root.update_idletasks()
            h = self.root.winfo_reqheight()
            self.root.geometry(f"316x{h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
        self.sec = 0

    def fast_tick(self):
        now = datetime.now()
        self.clock_var.set(now.strftime("%H:%M:%S"))
        if self.spin_vars:
            self.spin_i = (self.spin_i + 1) % len(SPIN_FRAMES)
            for sv in self.spin_vars:
                sv.set(SPIN_FRAMES[self.spin_i])
        if self.next_time and now >= self.next_time:
            self.full_render()
        else:
            if self.hero_cd and self.next_time:
                self.hero_cd.set(fmt_cd(self.next_time - now))
            if self.row_cd and self.next_time:
                self.row_cd.set(fmt_cd(self.next_time - now))
            self.sec += 1
            if self.sec >= 60:
                self.full_render()
        if self.folded:
            if self.next_time and self.next_name:
                self.head_var.set(f"  ▸ {self.next_name} {self.next_time:%H:%M} · {fmt_cd(self.next_time - now)}")
            else:
                self.head_var.set("  ▸ AI修仙模拟器")
        self.root.after(1000, self.fast_tick)

    def toggle_fold(self):
        self.folded = not self.folded
        if self.folded:
            self.hero.pack_forget()
            self.prog.pack_forget()
            self.cult.pack_forget()
            self.tabbar.pack_forget()
            for f in self._frames().values():
                f.pack_forget()
            self.clock_lbl.pack_forget()
            if self.fold_btn:
                self.fold_btn.config(text="▢")
            self.root.geometry(f"316x34+{self.root.winfo_x()}+{self.root.winfo_y()}")
        else:
            self.head_var.set("  AI修仙模拟器")
            self.clock_lbl.pack(side="left", padx=8)
            if TASKS:
                self.hero.pack(fill="x", padx=10, pady=(10, 6))
                self.prog.pack(fill="x", padx=12)
            self.cult.pack(fill="x", padx=10, pady=(6, 0))
            self.tabbar.pack(fill="x", padx=10, pady=(8, 0))
            self._apply_tab()
            if self.fold_btn:
                self.fold_btn.config(text="＿")
            self.full_render()

    # ── 功能按钮 ──
    def card_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=C["card2"], fg=C["txt"],
                    activebackground=C["line"], activeforeground=C["txt"], font=(FONT, 9))
        m.add_command(label="生成等级卡", command=self.make_card)
        m.add_command(label="生成七日统计卡", command=self.make_weekly)
        m.add_command(label="取消", command=m.unpost)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def make_card(self):
        try:
            if self._share_img:
                self.card_btn.config(image="", text="…", fg=C["dim"])
                self.root.after(8000, lambda: self.card_btn.config(image=self._share_img, text=""))
            else:
                self.card_btn.config(text="…")
                self.root.after(8000, lambda: self.card_btn.config(text="分享"))
        except Exception:
            pass
        spawn_tool("card.py", "--open")

    def make_weekly(self):
        spawn_tool("weekly.py", "--open")

    def rescan(self):
        spawn_tool("scan.py")
        self.root.after(20000, self.full_render)

    def open_dash(self):
        core.open_path(core.DASHBOARD_PATHS[1])

    def _bind_dismiss(self, w, kind, key, name):
        self.root.after_idle(lambda: self._rec_bind(w, kind, key, name))

    def _rec_bind(self, w, kind, key, name):
        try:
            w.bind("<Button-1>", lambda e: self._row_menu(kind, key, name))
            for c in w.winfo_children():
                self._rec_bind(c, kind, key, name)
        except tk.TclError:
            pass

    def _row_menu(self, kind, key, name):
        m = tk.Menu(self.root, tearoff=0, bg=C["card2"], fg=C["txt"],
                    activebackground=C["line"], activeforeground=C["txt"],
                    font=(FONT, 9))
        label = f"今日隐藏「{name[:12]}」" if kind == "tasks" else f"移除「{name[:12]}」（今日不再显示）"
        m.add_command(label=label, command=lambda: self._dismiss(kind, key))
        m.add_command(label="取消", command=m.unpost)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def _dismiss(self, kind, key):
        save_dismissed(kind, key)
        self.full_render()

    def _notify_on(self):
        return core.notify_enabled()

    def toggle_notify(self):
        try:
            cfg = core._load_config()
            cfg["notify_enabled"] = not cfg.get("notify_enabled", True)
            core.save_json(core.CONFIG, cfg)
            self.bell_btn.config(fg=C["amber"] if cfg["notify_enabled"] else C["dimmer"])
        except Exception:
            pass

    def toggle_top(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)

    def close(self):
        try:
            CLOSED_MARK.write_text(datetime.now().strftime("%Y-%m-%d"), encoding="utf-8")
        except Exception:
            pass
        self._save_pos()
        self.root.destroy()


def already_running():
    if core.IS_WIN:
        try:
            import ctypes
            return bool(ctypes.windll.user32.FindWindowW(None, WIN_TITLE))
        except Exception:
            return False
    try:
        r = subprocess.run(["pgrep", "-f", "sticky.py"], capture_output=True)
        pids = [p for p in r.stdout.decode().split() if p and int(p) != os.getpid()]
        return len(pids) > 0
    except Exception:
        return False


def closed_today():
    try:
        return CLOSED_MARK.read_text(encoding="utf-8").strip() == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def main():
    # --follow：自动兜底拉起模式（尊重当天手动关闭），手动打开则无条件弹
    if already_running():
        if core.IS_WIN:
            try:
                import ctypes
                h = ctypes.windll.user32.FindWindowW(None, WIN_TITLE)
                ctypes.windll.user32.ShowWindow(h, 9)
                ctypes.windll.user32.SetForegroundWindow(h)
            except Exception:
                pass
        return
    if "--follow" in sys.argv and closed_today():
        return
    if "--follow" not in sys.argv:
        try:
            CLOSED_MARK.unlink()
        except OSError:
            pass
    Sticky()


if __name__ == "__main__":
    main()
