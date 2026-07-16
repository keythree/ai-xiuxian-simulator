# -*- coding: utf-8 -*-
"""AI修仙模拟器 核心库
解析、判定、双轨等级（修为=使用量轨道 / 职业境界=技巧轨道）、机缘、面板渲染。
数值规则见 RULES-内部.md，绝不对外。
"""
import json, re, math, html, os, sys, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
FROZEN = bool(getattr(sys, "frozen", False))
# 打包版资源目录（chime.wav 等随包资源）；源码版即脚本目录
APP_RES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

def desktop_dir():
    if not IS_WIN:
        return Path.home() / "Desktop"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v, _ = winreg.QueryValueEx(k, "Desktop")
        return Path(os.path.expandvars(v))
    except OSError:
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"

def _data_dir():
    """玩家数据目录。打包版固定放用户主目录（挪 exe 不丢档），源码版跟脚本走。"""
    if FROZEN:
        d = Path.home() / ".ai-xiuxian"
        d.mkdir(exist_ok=True)
        return d
    return Path(__file__).resolve().parent

def open_path(p):
    """跨平台打开文件/网页。"""
    try:
        if IS_WIN:
            os.startfile(str(p))
        elif IS_MAC:
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:
        pass

def spawn_toast(events):
    """派生独立进程弹通知（不阻塞调用方）。打包版复用自身 exe，源码版用 pythonw。"""
    payload = json.dumps(events, ensure_ascii=False)
    if FROZEN:
        cmd = [sys.executable, "toast", payload]
    else:
        py = Path(sys.executable).with_name("pythonw.exe")
        exe = str(py if IS_WIN and py.exists() else sys.executable)
        cmd = [exe, str(Path(__file__).resolve().parent / "toast.py"), payload]
    kw = {"close_fds": True}
    if IS_WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kw)
    except Exception:
        pass

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_DIR = Path.home() / ".codex" / "sessions"
GEMINI_DIR = Path.home() / ".gemini" / "tmp"
OUT_DIR = _data_dir()
LEDGER = OUT_DIR / "ledger.json"
STATE = OUT_DIR / "state.json"
CONFIG = OUT_DIR / "config.json"
DASHBOARD_PATHS = [OUT_DIR / "dashboard.html", desktop_dir() / "AI修仙模拟器.html"]
LOCAL_TZ = datetime.now().astimezone().tzinfo

def _load_config():
    """读 config.json；文件缺失或损坏（例如上次安装中断写了半截）一律返回空配置，绝不卡死流程。"""
    try:
        with open(CONFIG, encoding="utf-8", errors="replace") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}

def player_name():
    return _load_config().get("name") or "无名道友"

def notify_enabled():
    """总开关：false 时静掉完成/升级弹窗（护法⚠警报不受此控制，安全通道常开）。"""
    return bool(_load_config().get("notify_enabled", True))

_INSTALL = "unset"

def install_date():
    """安装日（YYYY-MM-DD），用于新手期「紫气东来」buff 与入门机缘。惰性缓存。"""
    global _INSTALL
    if _INSTALL == "unset":
        _INSTALL = _load_config().get("install_date")
    return _INSTALL

BUFF_DAYS = 3
BUFF_MULT = 1.3

def buff_covers(day):
    """该日期是否在入门三日 buff 期内（只作用于安装后产生的修行，历史结算不吃加成）。"""
    inst = install_date()
    if not inst:
        return False
    try:
        d0 = datetime.strptime(inst, "%Y-%m-%d").date()
        dd = datetime.strptime(day, "%Y-%m-%d").date()
        return 0 <= (dd - d0).days < BUFF_DAYS
    except ValueError:
        return False

# ---------- 职业等级曲线（RuneScape，1 到 99） ----------
def _build_level_table():
    # 07-14 BK 定：指数 L/7 → L/20（两次加速），重度玩家约 5 个月可及飞升（原曲线到顶要二十年）
    cum, table = 0, [0, 0]
    for L in range(1, 99):
        cum += math.floor((L + 300 * 2 ** (L / 20)) / 4)
        table.append(cum)
    return table

LEVEL_XP = _build_level_table()

def xp_to_level(xp):
    lv = 1
    for L in range(2, 100):
        if xp >= LEVEL_XP[L]:
            lv = L
        else:
            break
    return lv

# ---------- 总等级曲线（LOL 式，无上限；07-14 BK 定提速一倍：需求减半，境界曲线不动） ----------
def total_xp_to_level(xp):
    lv, need = 1, 300.0
    while xp >= need:
        xp -= need
        lv += 1
        need = 250.0 + 50.0 * lv
    return lv, xp, need  # 等级、当前级内 XP、升下一级所需

# ---------- 职业与修仙称号 ----------
JOBS = ["程序", "策划", "影视", "美术", "文案", "研究", "运营", "杂学"]
TITLE_BANDS = [(1,9),(10,19),(20,29),(30,39),(40,49),(50,59),(60,69),(70,84),(85,98),(99,99)]
REALMS = ["炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫", "飞升"]
RANKS = ["道童", "修士", "真人", "长老", "尊者", "大能", "老祖", "仙君", "大帝", "天尊"]
PREFIX = {
    "程序": "编程", "策划": "谋划", "影视": "光影", "美术": "丹青",
    "文案": "文墨", "研究": "格物", "运营": "流量", "杂学": "杂修",
}

# 境界材质：名、主色、深色、光晕强度、特效类名（布→铁→铜→银→金→琉璃→紫晶→白玉→青玉→虹彩）
REALM_STYLE = [
    ("炼气", "#8a7a5c", "#5c5344", 0.0,  "cloth"),
    ("筑基", "#9aa5b1", "#5f6b7d", 0.08, "iron"),
    ("金丹", "#d08d4e", "#8f5a2b", 0.15, "bronze"),
    ("元婴", "#dde3ec", "#94a0b4", 0.22, "silver"),
    ("化神", "#ffd166", "#c9921b", 0.35, "gold"),
    ("炼虚", "#7fd8d4", "#2f8f8a", 0.45, "glass"),
    ("合体", "#b78aff", "#6f42c1", 0.55, "amethyst"),
    ("大乘", "#efe9d8", "#bfb695", 0.6,  "jade"),
    ("渡劫", "#a9d8ff", "#5a9fe0", 0.75, "stormjade"),
    ("飞升", "#ffffff", "#ffd166", 1.0,  "dao"),
]

def band_index(lv):
    for i, (a, b) in enumerate(TITLE_BANDS):
        if a <= lv <= b:
            return i
    return 0

def title_of(job, lv):
    return PREFIX[job] + RANKS[band_index(lv)]

SUB_STAGES = ["初期", "中期", "后期", "大圆满"]

def realm_of(lv):
    """大境界+小境界（筑基中期/金丹大圆满），把称号变化频率提高约四倍。99 飞升不分。"""
    i = band_index(lv)
    if lv >= 99:
        return REALMS[i]
    a, b = TITLE_BANDS[i]
    frac = (lv - a) / max(b - a, 1)
    sub = SUB_STAGES[0] if frac < 0.3 else SUB_STAGES[1] if frac < 0.55 else (
        SUB_STAGES[2] if frac < 0.85 else SUB_STAGES[3])
    return REALMS[i] + sub

# ---------- 判定规则 ----------
AUTO_PATTERNS = [
    "热点引擎", "跑一次热点", "xhs-doc", "xhs-joe", "幼玩园", "回复引擎", "定时任务",
    "bk-replay", "夜聊", "每日批", "晨报", "社区参与引擎", "scheduled", "cron",
    "自动执行", "例行", "10:19", "21:19", "MediaStudio 排期",
]
KW = {
    "影视": ["剪辑","字幕","转写","切片","调色","ffmpeg","whisper","成片","播客","混音","响度","视频拼","粗剪","精剪","分镜","爆破音","咔哒"],
    "美术": ["生图","genimg","图片生成","修图","封面","海报","画一","形象图","首帧","尾帧","midjourney","立绘","logo","配图"],
    "运营": ["发帖","推文","排期","小红书","抖音","B站","b站","涨粉","复盘数据","阅读量","互动","粉丝","账号","threads","reddit","社区","评论区","流量"],
    "文案": ["文案","翻译","改写","写一篇","写个帖","标题","口播","话术","润色","写作"],
    "程序": ["代码","脚本","py","js","函数","bug","报错","部署","编译","接口","数据库","爬虫","服务器","git","安装","环境","调试"],
    "策划": ["方案","规划","设计文档","策划","评估","决策","计划","路线图","定位","架构设计","玩法"],
    "研究": ["调研","分析一下","查一下","是什么","为什么","了解","研究","对比","行情","资料","搜一下","搜索"],
}
CODE_EXT = (".py",".js",".ts",".html",".css",".ps1",".sh",".bat",".json",".yaml",".yml",".sql",".c",".cpp",".rs",".go")
# 职业境界 XP（2026-07-12 BK 校准：3 天重度使用=筑基初级；数值≈sqrt(旧基础分)，
# 压慢境界成长但保留档间区分度。修为轨道不受影响。）
BASE_XP = {"D": 5, "C": 9, "B": 16, "A": 28, "S": 45}

def classify(first_msg, tools, write_exts):
    t = (first_msg or "").lower()
    for job in ["影视","美术","运营","文案"]:
        if any(k.lower() in t for k in KW[job]):
            return job
    code_writes = sum(1 for e in write_exts if e in CODE_EXT)
    if any(k in t for k in KW["程序"]) or code_writes >= 2:
        return "程序"
    if any(k in t for k in KW["策划"]):
        return "策划"
    web = tools.get("WebSearch", 0) + tools.get("WebFetch", 0) + tools.get("web_search", 0)
    if any(k in t for k in KW["研究"]) or web >= 3:
        return "研究"
    shell = tools.get("Bash", 0) + tools.get("PowerShell", 0) + tools.get("shell_command", 0) + tools.get("shell", 0)
    if code_writes >= 1 or shell >= 5:
        return "程序"
    return "杂学"

def difficulty(n_tools, has_agent):
    if has_agent and n_tools >= 30: return "S"
    if n_tools >= 150: return "S"
    if n_tools >= 50: return "A"
    if n_tools >= 15: return "B"
    if n_tools >= 3: return "C"
    return "D"

# ---------- 会话解析 ----------
RE_TOOLUSE = re.compile(r'"type":"tool_use"(?:(?!"type":"tool_use").){0,400}?"name":"([A-Za-z][\w]*)"')
RE_FILEPATH = re.compile(r'"file_path":"((?:[^"\\]|\\.)*?)"')
RE_TS = re.compile(r'"timestamp":"([^"]+)"')
RE_OUT_TOK = re.compile(r'"output_tokens":(\d+)')
RE_MODEL = re.compile(r'"model":"([\w.:-]+)"')

def parse_session(fp):
    fp = Path(fp)
    first_msg, first_ts, last_ts = None, None, None
    last_user_ts, last_user_msg = None, None
    n_msgs, out_tokens = 0, 0
    tools = defaultdict(int)
    write_exts = set()
    non_human = False
    hours_active = set()
    days_active = set()
    dh_active = set()
    models = {}
    with open(fp, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_TS.search(line)
            if m:
                last_ts = m.group(1)
                if first_ts is None:
                    first_ts = last_ts
                try:
                    dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                    hours_active.add(dt.hour)
                    days_active.add(dt.strftime("%Y-%m-%d"))
                    dh_active.add(dt.strftime("%Y-%m-%d %H"))
                except ValueError:
                    pass
            if '"type":"user"' in line and '"isMeta":true' not in line and '"content":"' in line:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    obj = None
                if obj and obj.get("type") == "user" and not obj.get("isSidechain"):
                    c = obj.get("message", {}).get("content")
                    if isinstance(c, str) and c.strip():
                        cs = c.strip()
                        mm = re.search(r"<command-name>([^<]+)</command-name>", cs)
                        st = re.search(r'<scheduled-task name="([^"]+)"', cs)
                        msg = None
                        if st:
                            msg = f"[定时任务] {st.group(1)}"
                        elif mm:
                            msg = "/" + mm.group(1).strip()
                        elif not cs.startswith("<"):
                            msg = cs[:300]
                        if msg:
                            last_user_ts = obj.get("timestamp") or last_ts
                            last_user_msg = msg
                            if first_msg is None:
                                first_msg = msg
                                if st:
                                    non_human = True
                                else:
                                    org = obj.get("origin", {})
                                    if isinstance(org, dict) and org.get("kind") not in (None, "human"):
                                        non_human = True
            if '"type":"user"' in line or '"type":"assistant"' in line:
                n_msgs += 1
            if '"output_tokens"' in line and '"type":"assistant"' in line:
                mm = RE_MODEL.search(line)
                mkey = mm.group(1) if mm else "unknown"
                for m in RE_OUT_TOK.finditer(line):
                    t = int(m.group(1))
                    out_tokens += t
                    models[mkey] = models.get(mkey, 0) + t
            if '"tool_use"' in line:
                for m in RE_TOOLUSE.finditer(line):
                    tools[m.group(1)] += 1
                if '"file_path"' in line:
                    for m in RE_FILEPATH.finditer(line):
                        p = m.group(1).rsplit(".", 1)
                        if len(p) == 2 and len(p[1]) <= 5:
                            write_exts.add("." + p[1].lower())
    return {
        "session": fp.stem, "src": "claude-code", "models": models,
        "first_msg": first_msg or "", "first_ts": first_ts, "last_ts": last_ts,
        "last_user_ts": last_user_ts, "last_user_msg": last_user_msg or "",
        "n_msgs": n_msgs, "out_tokens": out_tokens, "tools": dict(tools),
        "write_exts": sorted(write_exts), "non_human": non_human, "hours": sorted(hours_active),
        "days": sorted(days_active), "dh": sorted(dh_active),
    }

# ---------- Codex CLI / Desktop 适配器 ----------
RE_CODEX_FC = re.compile(r'"type":"function_call".{0,600}?"name":"([\w-]+)"')
RE_CODEX_OUT = re.compile(r'"total_token_usage":\{[^}]*?"output_tokens":(\d+)')
RE_ANY_EXT = re.compile(r'\.(py|js|ts|html|css|ps1|sh|bat|json|yaml|yml|sql|c|cpp|rs|go|md|txt)\\?"')

def parse_codex_session(fp):
    fp = Path(fp)
    first_msg, first_ts, last_ts = None, None, None
    n_msgs, out_tokens = 0, 0
    tools = defaultdict(int)
    write_exts = set()
    non_human = False
    hours_active = set()
    days_active = set()
    dh_active = set()
    codex_provider = "codex"
    with open(fp, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_TS.search(line)
            if m:
                last_ts = m.group(1)
                if first_ts is None:
                    first_ts = last_ts
                try:
                    dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                    hours_active.add(dt.hour)
                    days_active.add(dt.strftime("%Y-%m-%d"))
                    dh_active.add(dt.strftime("%Y-%m-%d %H"))
                except ValueError:
                    pass
            if '"type":"session_meta"' in line:
                om = re.search(r'"originator":"([^"]*)"', line)
                if om and "exec" in om.group(1).lower():
                    non_human = True
                pm = re.search(r'"model_provider":"(\w+)"', line)
                if pm:
                    codex_provider = pm.group(1)
            if '"type":"user_message"' in line:
                n_msgs += 1
                if first_msg is None:
                    try:
                        obj = json.loads(line)
                        msg = obj.get("payload", {}).get("message", "")
                        if isinstance(msg, str) and msg.strip():
                            first_msg = msg.strip()[:300]
                    except json.JSONDecodeError:
                        pass
            if '"role":"assistant"' in line:
                n_msgs += 1
            if '"type":"function_call"' in line:
                for m in RE_CODEX_FC.finditer(line):
                    tools[m.group(1)] += 1
                if "apply_patch" in line or "write" in line:
                    for m in RE_ANY_EXT.finditer(line[:20000]):
                        write_exts.add("." + m.group(1).lower())
            if '"total_token_usage"' in line:
                m = RE_CODEX_OUT.search(line)
                if m:
                    out_tokens = int(m.group(1))  # 累计值，取最后一次
    return {
        "session": fp.stem, "src": "codex",
        "models": {f"codex:{codex_provider}": out_tokens} if out_tokens else {},
        "first_msg": first_msg or "", "first_ts": first_ts, "last_ts": last_ts,
        "n_msgs": n_msgs, "out_tokens": out_tokens, "tools": dict(tools),
        "write_exts": sorted(write_exts), "non_human": non_human, "hours": sorted(hours_active),
        "days": sorted(days_active), "dh": sorted(dh_active),
    }

COPILOT_DB = Path.home() / ".copilot" / "session-store.db"


def parse_copilot_session(sid):
    """GitHub Copilot CLI（v1.0.7x+，会话存 SQLite session-store.db）。sid=sessions.id。
    表结构 2026-07 实机确认：turns(user_message/assistant_response/timestamp)、
    assistant_usage_events(model/output_tokens/created_at)。任何异常返回空记录被过滤。"""
    rec = {"session": f"copilot-{sid}", "src": "copilot-cli", "models": {},
           "first_msg": "", "first_ts": None, "last_ts": None, "n_msgs": 0,
           "out_tokens": 0, "tools": {}, "write_exts": [], "non_human": False,
           "hours": [], "days": [], "dh": []}
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{COPILOT_DB.as_posix()}?mode=ro", uri=True)
        hours, days, dh = set(), set(), set()

        def note_ts(v):
            if v in (None, ""):
                return None
            try:
                if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace(".", "", 1).isdigit()):
                    x = float(v)
                    if x > 1e12:
                        x /= 1000.0
                    dt = datetime.fromtimestamp(x, tz=timezone.utc).astimezone(LOCAL_TZ)
                else:
                    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(LOCAL_TZ)
            except (ValueError, OSError, OverflowError):
                return None
            hours.add(dt.hour)
            days.add(dt.strftime("%Y-%m-%d"))
            dh.add(dt.strftime("%Y-%m-%d %H"))
            return dt.isoformat()

        for um, ar, ts in con.execute(
                "select user_message, assistant_response, timestamp from turns "
                "where session_id=? order by turn_index", (sid,)):
            iso = note_ts(ts)
            if iso:
                rec["last_ts"] = iso
                if rec["first_ts"] is None:
                    rec["first_ts"] = iso
            if um:
                rec["n_msgs"] += 1
                if not rec["first_msg"]:
                    t = str(um).strip()
                    if t.startswith("{"):
                        try:
                            obj = json.loads(t)
                            t = str(obj.get("text") or obj.get("content") or t)
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    rec["first_msg"] = t[:300]
            if ar:
                rec["n_msgs"] += 1
        for model, out_t, cts in con.execute(
                "select model, output_tokens, created_at from assistant_usage_events "
                "where session_id=?", (sid,)):
            rec["out_tokens"] += int(out_t or 0)
            key = f"copilot:{model or 'unknown'}"
            rec["models"][key] = rec["models"].get(key, 0) + int(out_t or 0)
            note_ts(cts)
        if rec["first_ts"] is None:
            row = con.execute("select created_at, updated_at from sessions where id=?",
                              (sid,)).fetchone()
            if row:
                rec["first_ts"] = note_ts(row[0])
                rec["last_ts"] = note_ts(row[1]) or rec["first_ts"]
        con.close()
        rec["hours"], rec["days"], rec["dh"] = sorted(hours), sorted(days), sorted(dh)
    except Exception:
        pass
    return rec


def _copilot_session_ids():
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{COPILOT_DB.as_posix()}?mode=ro", uri=True)
        sids = [r[0] for r in con.execute("select id from sessions")]
        con.close()
        return sids
    except Exception:
        return []


# ---------- 数据源自动发现 ----------
def discover_sources():
    """返回 [(源名, 会话文件列表, 解析函数)]，自动识别本机装了哪些 AI 工具。"""
    sources = []
    if PROJECTS_DIR.exists():
        files = [f for f in PROJECTS_DIR.rglob("*.jsonl") if not f.name.startswith("agent-")]
        sources.append(("claude-code", files, parse_session))
    if CODEX_DIR.exists():
        sources.append(("codex", list(CODEX_DIR.rglob("rollout-*.jsonl")), parse_codex_session))
    if COPILOT_DB.exists():
        sids = _copilot_session_ids()
        if sids:
            sources.append(("copilot-cli", sids, parse_copilot_session))
    # 新法器扩展：在此追加 detect + parser（拿到真实样本才写解析器，绝不赌格式）
    return sources

# 已探测到、但尚未接入的法器（有目录=用户在用；提示提交样本，拿到当天出适配器）
UNSUPPORTED_TOOLS = [
    ("Gemini CLI", Path.home() / ".gemini"),
    ("Qwen Code", Path.home() / ".qwen"),
    ("iFlow CLI", Path.home() / ".iflow"),
    ("GitHub Copilot CLI", Path.home() / ".copilot"),
    ("Cursor", Path.home() / ".cursor"),
    ("Windsurf", Path.home() / ".windsurf"),
    ("OpenCode", Path.home() / ".opencode"),
    ("Aider", Path.home() / ".aider"),
    ("Kilo CLI", Path.home() / ".kilocode"),
    ("Goose", Path.home() / ".config" / "goose"),
    ("CodeBuddy CLI", Path.home() / ".codebuddy"),
    ("通义灵码 CLI", Path.home() / ".lingma"),
]

# 桌面 IDE 类（VS Code fork，各有独立数据目录）
if IS_WIN:
    _APP_SUPPORT = Path(os.environ.get("APPDATA", ""))
elif IS_MAC:
    _APP_SUPPORT = Path.home() / "Library" / "Application Support"
else:
    _APP_SUPPORT = Path.home() / ".config"
UNSUPPORTED_TOOLS += [
    ("Trae", _APP_SUPPORT / "Trae"),
]

# JetBrains 系（IDEA 等，AI Assistant/Junie/Copilot 走插件）
if IS_WIN:
    _LOCAL_APP = Path(os.environ.get("LOCALAPPDATA", ""))
else:
    _LOCAL_APP = Path.home() / ".config"
UNSUPPORTED_TOOLS += [
    ("JetBrains IDE (AI Assistant/Junie)", _APP_SUPPORT / "JetBrains"),
    ("Junie", Path.home() / ".junie"),
    ("GitHub Copilot (JetBrains)", _LOCAL_APP / "github-copilot"),
]
if IS_WIN:
    _VSC_STORE = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "globalStorage"
else:
    _VSC_STORE = Path.home() / ("Library/Application Support/Code/User/globalStorage" if IS_MAC
                                else ".config/Code/User/globalStorage")
UNSUPPORTED_TOOLS += [
    ("Cline", _VSC_STORE / "saoudrizwan.claude-dev"),
    ("Roo Code", _VSC_STORE / "rooveterinaryinc.roo-cline"),
    ("GitHub Copilot (VS Code)", Path.home() / ".vscode" / "extensions" / "github.copilot-*"),
    ("Kilo Code (VS Code)", _VSC_STORE / "*kilo*"),
    ("通义灵码 (VS Code)", _VSC_STORE / "*lingma*"),
    ("CodeGeeX (VS Code)", _VSC_STORE / "*codegeex*"),
    ("文心快码 Comate (VS Code)", _VSC_STORE / "*comate*"),
    ("CodeBuddy (VS Code)", _VSC_STORE / "*codebuddy*"),
    ("CodeBuddy (VS Code)", _VSC_STORE / "*coding-copilot*"),
]

def detect_unsupported():
    """返回本机在用但尚未接入的 AI 工具名列表（路径含 * 时按通配匹配，重名去重）。"""
    import glob as _glob
    out = []
    for name, p in UNSUPPORTED_TOOLS:
        if name == "GitHub Copilot CLI" and COPILOT_DB.exists():
            continue  # 新版（SQLite 存储）已接入记账，只有旧版才提示交样本
        sp = str(p)
        if name not in out and (("*" in sp and _glob.glob(sp)) or ("*" not in sp and p.exists())):
            out.append(name)
    return out

# ---------- 单会话判定（产出 raw 记录，不含日级反刷） ----------
def judge(s, template_counts):
    n_tools = sum(s["tools"].values())
    has_agent = any(t in s["tools"] for t in ("Task", "Agent", "Workflow"))
    diff = difficulty(n_tools, has_agent)
    job = classify(s["first_msg"], s["tools"], s["write_exts"])
    fm = s["first_msg"]
    is_auto = s["non_human"] or template_counts.get(fm[:80], 0) >= 3 or any(
        p.lower() in fm.lower() for p in AUTO_PATTERNS)
    xp = BASE_XP[diff]
    if diff == "D" and n_tools == 0:
        xp = min(xp, 3)
    n_writes = s["tools"].get("Write", 0) + s["tools"].get("Edit", 0)
    if n_writes >= 1: xp *= 1.3
    if len(s["tools"]) >= 4: xp *= 1.2
    if is_auto: xp *= 0.05
    auto_f = 0.2 if is_auto else 1.0
    total_xp = 30 * auto_f + math.sqrt(max(s["out_tokens"], 0)) / 12 * auto_f
    try:
        day = datetime.fromisoformat(s["first_ts"].replace("Z", "+00:00")).astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        day = "unknown"
    if buff_covers(day):
        total_xp *= BUFF_MULT  # 紫气东来：入门三日灵气加三成
    return {
        "session": s["session"], "src": s.get("src", "claude-code"),
        "day": day, "job": job, "diff": diff, "auto": is_auto,
        "xp_raw": round(xp, 1), "total_xp": round(total_xp, 1),
        "n_tools": n_tools, "tool_kinds": len(s["tools"]),
        "n_msgs": s["n_msgs"], "out_tokens": s["out_tokens"],
        "agent": has_agent, "hours": s["hours"], "days": s.get("days", []),
        "dh": s.get("dh", []), "models": s.get("models", {}), "first_msg": fm[:120],
    }

# ---------- 日级反刷（幂等：每次对全台账重算最终 xp） ----------
def apply_caps(ledger):
    by_day = defaultdict(list)
    for r in ledger:
        r["xp"] = r["xp_raw"]
        by_day[r["day"]].append(r)
    for rows in by_day.values():
        groups = defaultdict(list)
        for r in rows:
            if not r["auto"]:
                groups[(r["job"], r["diff"])].append(r)
        for g in groups.values():
            g.sort(key=lambda r: -r["xp_raw"])
            for n, r in enumerate(g):
                r["xp"] = r["xp_raw"] * max(0.85 ** n, 0.3)
        auto_budget = 15.0
        for r in sorted([r for r in rows if r["auto"]], key=lambda r: -r["xp_raw"]):
            r["xp"] = min(r["xp_raw"], auto_budget)
            auto_budget = max(0.0, auto_budget - r["xp"])
        cum = 0.0
        for r in sorted([r for r in rows if not r["auto"]], key=lambda r: -r["xp"]):
            take = r["xp"]
            within = max(0.0, min(take, 500.0 - cum))
            cum += take
            r["xp"] = within + (take - within) * 0.3
    for r in ledger:
        r["xp"] = round(r["xp"], 1)

# ---------- 汇总与勋章 ----------
def compute_state(ledger):
    apply_caps(ledger)
    job_xp, day_xp, total_xp = defaultdict(float), defaultdict(float), 0.0
    for r in ledger:
        job_xp[r["job"]] += r["xp"]
        day_xp[r["day"]] += r["xp"]
        total_xp += r["total_xp"]
    levels = {j: xp_to_level(job_xp.get(j, 0)) for j in JOBS}
    t_lv, t_in, t_need = total_xp_to_level(total_xp)
    streak = calc_streak(day_xp)
    badges = compute_badges(ledger, levels, day_xp, t_lv, streak)
    update_badge_log(badges)
    # 机缘灵气入账（一次性奖励，随后重算修为）
    total_xp += sum(badge_reward(b[0], b[1]) for b in badges)
    t_lv, t_in, t_need = total_xp_to_level(total_xp)
    buff_left = 0
    inst = install_date()
    if inst:
        try:
            d0 = datetime.strptime(inst, "%Y-%m-%d").date()
            buff_left = max(0, BUFF_DAYS - (datetime.now(LOCAL_TZ).date() - d0).days)
        except ValueError:
            pass
    return {
        "total_level": t_lv, "total_xp": round(total_xp), "total_in": round(t_in), "total_need": round(t_need),
        "levels": levels, "job_xp": {j: round(job_xp.get(j, 0), 1) for j in JOBS},
        "day_xp": {d: round(v, 1) for d, v in day_xp.items()}, "badges": badges, "streak": streak,
        "buff_days": buff_left,
    }

def calc_streak(day_xp):
    """连续修行天数：从今天（今天还没修则从昨天）向前数连续有灵气的日子。"""
    from datetime import timedelta
    d = datetime.now(LOCAL_TZ).date()
    if day_xp.get(d.strftime("%Y-%m-%d"), 0) <= 0:
        d -= timedelta(days=1)
    n = 0
    while day_xp.get(d.strftime("%Y-%m-%d"), 0) > 0:
        n += 1
        d -= timedelta(days=1)
    return n

# 全量机缘注册表（名→类型）：未悟的以灰色剪影示人，只给数量不给条件（黑箱）
ALL_BADGES = {
    "暗夜苦修": "隐藏", "子时炼心": "隐藏", "闻鸡起舞": "隐藏", "一日千里": "隐藏",
    "道心如铁": "隐藏", "双修": "隐藏", "八臂哪吒": "隐藏", "彻夜长谈": "隐藏",
    "一掷千金": "隐藏", "快刀乱麻": "隐藏", "无休道人": "隐藏", "万法皆通": "隐藏",
    "三足鼎立": "隐藏", "一日三省": "隐藏", "开光": "隐藏", "明察秋毫": "隐藏",
    "持之以恒": "里程碑", "风雨无阻": "里程碑", "百战宿将": "里程碑", "百炼成钢": "里程碑",
    "千山踏遍": "里程碑", "元婴初成": "里程碑", "窥见炼虚": "里程碑", "道行小成": "里程碑",
    "闭关一月": "里程碑", "初入道门": "里程碑", "小试牛刀": "里程碑", "轻车熟路": "里程碑",
    "初窥门径": "里程碑", "一专多能": "里程碑", "勤学苦练": "里程碑", "渐入佳境": "里程碑",
    "分身有术": "奇遇", "斩妖除魔": "奇遇", "首战告捷": "奇遇",
    "闻道": "奇遇", "初露锋芒": "奇遇", "紫气盈门": "奇遇", "二日不辍": "里程碑",
    "五方问道": "隐藏", "早晚功课": "隐藏",
    "周天圆满": "仙缘", "岁月成碑": "仙缘", "万象归一": "仙缘",
    "亿字真经": "仙缘", "道行如山": "仙缘",
}
TOTAL_BADGES = len(ALL_BADGES)

# 机缘灵气（一次性入账；前期多而小、后期少而大，数值属黑箱见 RULES-内部.md）
BADGE_REWARD_KIND = {"奇遇": 30, "里程碑": 60, "隐藏": 120, "仙缘": 500}
BADGE_REWARD_OVERRIDE = {
    "初入道门": 20, "首战告捷": 20, "闻道": 20, "二日不辍": 30, "勤学苦练": 40,
    "小试牛刀": 40, "初窥门径": 40, "一日三省": 50, "开光": 50, "紫气盈门": 50,
    "闭关一月": 100, "风雨无阻": 150, "千山踏遍": 300, "道心如铁": 300, "万法皆通": 300,
}

def badge_reward(name, kind):
    return BADGE_REWARD_OVERRIDE.get(name, BADGE_REWARD_KIND.get(kind, 60))

BADGE_LOG = OUT_DIR / "badge-log.json"

def update_badge_log(badges):
    """记录每枚机缘的初次获得日期（周报「本周新悟」的数据源）。"""
    try:
        try:
            with open(BADGE_LOG, encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = {}
        today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        changed = False
        for b in badges:
            if b[0] not in log:
                log[b[0]] = today
                changed = True
        if changed:
            save_json(BADGE_LOG, log)
        return log
    except Exception:
        return {}

# 机缘图符（勋章中心图案，卡片/面板彩色渲染，贴纸单色显示）
BADGE_ICONS = {
    "暗夜苦修": "🌙", "子时炼心": "🕯", "闻鸡起舞": "🐓", "一日千里": "⚡",
    "持之以恒": "🔥", "风雨无阻": "☔", "道心如铁": "💎", "双修": "☯",
    "八臂哪吒": "🔱", "彻夜长谈": "💬", "一掷千金": "💰", "百战宿将": "⚔",
    "快刀乱麻": "🗡", "无休道人": "📿", "分身有术": "👥", "斩妖除魔": "👹",
    "百炼成钢": "🔨", "千山踏遍": "⛰", "闭关一月": "🧘", "元婴初成": "👶",
    "窥见炼虚": "🔮", "道行小成": "🌱", "万法皆通": "📖", "明察秋毫": "👁",
    "初入道门": "🚪", "首战告捷": "🎯", "开光": "✨", "一日三省": "💭",
    "渐入佳境": "📈", "小试牛刀": "🐂", "轻车熟路": "🐎", "初窥门径": "🔑",
    "一专多能": "🎭", "三足鼎立": "🏺", "勤学苦练": "📚",
    "闻道": "🍃", "初露锋芒": "🌟", "紫气盈门": "💜", "二日不辍": "🌿",
    "五方问道": "🧭", "早晚功课": "🕰",
    "周天圆满": "🌈", "岁月成碑": "🗿", "万象归一": "🪐",
    "亿字真经": "📜", "道行如山": "⛩",
}

def compute_badges(ledger, levels, day_xp, total_level, streak=0):
    badges = []
    manual = [r for r in ledger if not r["auto"]]
    raw_day = defaultdict(float)
    for r in manual:
        raw_day[r["day"]] += r["total_xp"]
    if any(set(r["hours"]) & {3, 4} for r in manual):
        badges.append(("暗夜苦修", "隐藏", "寅时仍在修炼"))
    if any(set(r["hours"]) & {0, 1, 2} for r in manual):
        badges.append(("子时炼心", "隐藏", "子夜仍未收功"))
    if any(set(r["hours"]) & {5, 6} for r in manual):
        badges.append(("闻鸡起舞", "隐藏", "卯时即起修行"))
    if any(v >= 10000 for v in raw_day.values()):
        badges.append(("一日千里", "隐藏", "单日修为破万"))
    if streak >= 7:
        badges.append(("持之以恒", "里程碑", "连续修行七日"))
    if streak >= 30:
        badges.append(("风雨无阻", "里程碑", "连续修行三十日"))
    if streak >= 100:
        badges.append(("道心如铁", "隐藏", "连续修行百日"))
    claude_days = set()
    codex_days = set()
    for r in ledger:
        (claude_days if r.get("src") == "claude-code" else codex_days).update(r.get("days", []))
    if claude_days & codex_days:
        badges.append(("双修", "隐藏", "一日之内双法器同运"))
    if any(r.get("tool_kinds", 0) >= 8 for r in manual):
        badges.append(("八臂哪吒", "隐藏", "一场历练动用八般法术"))
    if any(r.get("n_msgs", 0) >= 200 for r in manual):
        badges.append(("彻夜长谈", "隐藏", "一场历练往来二百回合"))
    if any(r.get("out_tokens", 0) >= 2_000_000 for r in manual):
        badges.append(("一掷千金", "隐藏", "一场历练挥霍灵石二百万"))
    if sum(1 for r in manual if r["diff"] in ("S", "A")) >= 50:
        badges.append(("百战宿将", "里程碑", "高阶历练五十次"))
    day_count = defaultdict(int)
    for r in manual:
        for d in r.get("days", []) or [r["day"]]:
            day_count[d] += 1
    if any(v >= 15 for v in
           ({d: sum(1 for r in manual if r["day"] == d) for d in {r["day"] for r in manual}}).values()):
        badges.append(("快刀乱麻", "隐藏", "单日亲身历练十五场"))
    try:
        from datetime import timedelta
        active = {d for d, v in day_xp.items() if v > 0}
        for d in list(active):
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            if dt.isoweekday() == 6 and (dt + timedelta(days=1)).strftime("%Y-%m-%d") in active:
                badges.append(("无休道人", "隐藏", "周末双日皆在修行"))
                break
    except ValueError:
        pass
    if any(r["agent"] for r in manual):
        badges.append(("分身有术", "奇遇", "初次施展分身之术"))
    if any(r["diff"] == "S" for r in manual):
        badges.append(("斩妖除魔", "奇遇", "初次完成 S 级历练"))
    if len(manual) >= 100:
        badges.append(("百炼成钢", "里程碑", "亲身历练百次"))
    if len(manual) >= 1000:
        badges.append(("千山踏遍", "里程碑", "亲身历练千次"))
    if max(levels.values()) >= 30:
        badges.append(("元婴初成", "里程碑", "首个职业踏入元婴期"))
    if max(levels.values()) >= 50:
        badges.append(("窥见炼虚", "里程碑", "首个职业踏入炼虚期"))
    if total_level >= 50:
        badges.append(("道行小成", "里程碑", "修为到 50 级"))
    if min(levels.values()) >= 10:
        badges.append(("万法皆通", "隐藏", "八道皆入筑基"))
    if sum(1 for v in day_xp if v) >= 30:
        badges.append(("闭关一月", "里程碑", "累计修行 30 日"))
    # ---- 入门期机缘（前三天高密度正反馈时间线）----
    cfg = _load_config()
    inst = install_date()
    if inst:
        badges.append(("初入道门", "里程碑", "踏入仙门，气运加身"))
        if any(r["day"] >= inst for r in manual):
            badges.append(("首战告捷", "奇遇", "入门后首场历练功成"))
    if cfg.get("cards_made", 0) >= 1:
        badges.append(("开光", "隐藏", "首张等级卡开光"))
    daily_counts = defaultdict(int)
    for r in manual:
        daily_counts[r["day"]] += 1
    if any(v >= 3 for v in daily_counts.values()):
        badges.append(("一日三省", "隐藏", "单日亲身历练三场"))
    if any(v >= 5 for v in daily_counts.values()):
        badges.append(("渐入佳境", "里程碑", "单日亲身历练五场"))
    if len(manual) >= 10:
        badges.append(("小试牛刀", "里程碑", "亲身历练十次"))
    if len(manual) >= 30:
        badges.append(("轻车熟路", "里程碑", "亲身历练三十次"))
    if max(levels.values()) >= 5:
        badges.append(("初窥门径", "里程碑", "首个职业到 5 级"))
    if sum(1 for v in levels.values() if v >= 5) >= 2:
        badges.append(("一专多能", "里程碑", "两道皆入 5 级"))
    if sum(1 for v in levels.values() if v >= 3) >= 3:
        badges.append(("三足鼎立", "隐藏", "三道齐头并进"))
    if streak >= 3:
        badges.append(("勤学苦练", "里程碑", "连续修行三日"))
    try:
        with open(OUT_DIR / "watchdog-state.json", encoding="utf-8") as f:
            if json.load(f).get("catches", 0) > 0:
                badges.append(("明察秋毫", "隐藏", "护法初次察觉阵法停转"))
    except OSError:
        pass
    # ---- 新手期追加（前三日高密度小额正反馈）----
    if inst and any(r["day"] == inst for r in manual):
        badges.append(("闻道", "奇遇", "入门当日即开修"))
    if streak >= 2:
        badges.append(("二日不辍", "里程碑", "连续修行两日"))
    if any(r["diff"] in ("A", "S") for r in manual):
        badges.append(("初露锋芒", "奇遇", "初次完成 A 级历练"))
    if len({r["job"] for r in manual}) >= 3:
        badges.append(("五方问道", "隐藏", "历练涉足三道"))
    dh_day = defaultdict(set)
    for r in manual:
        for s in r.get("dh", []):
            try:
                d, h = s.split(" ")
                dh_day[d].add(int(h))
            except ValueError:
                pass
    if any(hs & set(range(6, 12)) and hs & set(range(18, 24)) for hs in dh_day.values()):
        badges.append(("早晚功课", "隐藏", "同日早晚皆有修行"))
    if inst:
        try:
            from datetime import timedelta
            d0 = datetime.strptime(inst, "%Y-%m-%d").date()
            first3 = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
            if datetime.now(LOCAL_TZ).date() >= d0 + timedelta(days=2) and \
               all(day_xp.get(d, 0) > 0 for d in first3):
                badges.append(("紫气盈门", "奇遇", "新手期三日全勤"))
        except ValueError:
            pass
    # ---- 仙缘（长线大器，晚成而丰厚）----
    all_hours = set()
    for r in manual:
        all_hours.update(r.get("hours", []))
    if len(all_hours) >= 24:
        badges.append(("周天圆满", "仙缘", "十二时辰皆曾修行"))
    active_days = sorted(d for d, v in day_xp.items() if v > 0)
    if active_days:
        try:
            span = (datetime.strptime(active_days[-1], "%Y-%m-%d")
                    - datetime.strptime(active_days[0], "%Y-%m-%d")).days
            if span >= 180:
                badges.append(("岁月成碑", "仙缘", "道行跨越半载"))
        except ValueError:
            pass
    if min(levels.values()) >= 20:
        badges.append(("万象归一", "仙缘", "八道皆入金丹"))
    if sum(r.get("out_tokens", 0) for r in ledger) >= 100_000_000:
        badges.append(("亿字真经", "仙缘", "累计炼化灵石一亿"))
    if len(active_days) >= 300:
        badges.append(("道行如山", "仙缘", "累计修行三百日"))
    return [(n, k, d, BADGE_ICONS.get(n, "🔸")) for n, k, d in badges]

# ---------- 台账读写 ----------
def load_ledger():
    if LEDGER.exists():
        with open(LEDGER, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json(path, data):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(path)

def template_counts_of(ledger):
    c = defaultdict(int)
    for r in ledger:
        c[r["first_msg"][:80]] += 1
    return c

# ---------- 面板 ----------
SRC_NAMES = {"claude-code": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI"}

def render_dashboard(state, ledger):
    levels, job_xp = state["levels"], state["job_xp"]
    n_manual = sum(1 for r in ledger if not r["auto"])
    n_auto = len(ledger) - n_manual
    srcs = sorted({r.get("src", "claude-code") for r in ledger})
    src_label = " + ".join(SRC_NAMES.get(s, s) for s in srcs)
    job_cards = ""
    for j in JOBS:
        lv, xp = levels[j], job_xp.get(j, 0)
        cur, nxt = LEVEL_XP[lv], LEVEL_XP[min(lv + 1, 99)]
        pct = 100 if lv >= 99 else round((xp - cur) / max(nxt - cur, 1) * 100)
        job_cards += f"""
        <div class="job">
          <div class="job-head"><span class="job-name">{j}</span><span class="job-lv">Lv {lv}</span></div>
          <div class="job-title">{realm_of(lv)} · {title_of(j, lv)}</div>
          <div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div>
          <div class="job-next">距突破 {pct}%</div>
        </div>"""
    day_xp = state["day_xp"]
    days = sorted(day_xp.keys())[-14:]
    maxd = max((day_xp[d] for d in days), default=1) or 1
    day_bars = "".join(
        f'<div class="dcol"><div class="dbar" style="height:{max(4, round(day_xp[d]/maxd*90))}px"></div><div class="dlab">{d[5:]}</div></div>'
        for d in days)
    badge_html = "".join(
        f'<div class="badge b-{"xian" if b[1]=="仙缘" else ("hid" if b[1]=="隐藏" else "norm")}">'
        f'<div class="badge-ico">{b[3] if len(b) > 3 else "🔸"}</div>'
        f'<div class="badge-name">{b[0]}</div><div class="badge-type">{b[1]}机缘</div>'
        f'<div class="badge-desc">{b[2]}</div></div>'
        for b in state["badges"]) or '<div class="empty">尚无机缘，道友继续修炼</div>'
    unlocked = {b[0] for b in state["badges"]}
    badge_html += "".join(
        f'<div class="badge b-locked"><div class="badge-ico">？</div>'
        f'<div class="badge-name">？？？</div><div class="badge-type">未悟 · {k}</div>'
        f'<div class="badge-desc">机缘未至</div></div>'
        for n, k in ALL_BADGES.items() if n not in unlocked)
    top = sorted([r for r in ledger if not r["auto"]], key=lambda r: -r["xp"])[:8]
    top_rows = "".join(
        f'<tr><td class="d-{r["diff"]}">{r["diff"]}</td><td>{r["job"]}</td><td class="xp">+{round(r["xp"])}</td><td class="msg">{html.escape(r["first_msg"][:60])}</td></tr>'
        for r in top)
    t_pct = round(state["total_in"] / max(state["total_need"], 1) * 100)
    page = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>AI修仙模拟器</title><style>
body{{background:#0b0e14;color:#e6e1cf;font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:0;padding:32px}}
.wrap{{max-width:960px;margin:0 auto}}
h1{{font-size:18px;letter-spacing:6px;color:#8a8f98;font-weight:400;margin:0 0 4px}}
.total{{font-size:72px;font-weight:800;color:#ffd166;line-height:1}}
.total small{{font-size:16px;color:#8a8f98;font-weight:400;margin-left:8px}}
.tbar{{height:8px;background:#1c2230;border-radius:4px;overflow:hidden;max-width:420px;margin:10px 0 4px}}
.tbar-fill{{height:100%;background:linear-gradient(90deg,#ffd166,#ff9f43)}}
.tnext{{font-size:12px;color:#5c6773}}
.meta{{color:#5c6773;font-size:13px;margin:8px 0 28px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.job{{background:#11151f;border:1px solid #1c2230;border-radius:10px;padding:14px}}
.job-head{{display:flex;justify-content:space-between;align-items:baseline}}
.job-name{{font-size:15px}}.job-lv{{font-size:20px;font-weight:700;color:#ffd166}}
.job-title{{font-size:12px;color:#59c2ff;margin:4px 0 8px}}
.bar{{height:6px;background:#1c2230;border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;background:linear-gradient(90deg,#59c2ff,#ffd166)}}
.job-next{{font-size:11px;color:#5c6773;margin-top:5px}}
h2{{font-size:14px;color:#8a8f98;letter-spacing:3px;margin:32px 0 12px;font-weight:400}}
.badges{{display:flex;gap:12px;flex-wrap:wrap}}
.badge{{background:#11151f;border:1px solid #2a3040;border-radius:10px;padding:12px 16px;min-width:130px;text-align:center}}
.b-hid{{border-color:#6c3fc5;box-shadow:0 0 12px rgba(108,63,197,.35)}}
.b-xian{{border-color:#ff8c5a;box-shadow:0 0 16px rgba(255,140,90,.45)}}
.b-locked{{opacity:.32;border-style:dashed}}
.badge-ico{{font-size:30px;line-height:1.2;margin-bottom:4px}}
.badge-name{{font-size:16px;font-weight:700;color:#ffd166}}
.b-hid .badge-name{{color:#c792ea}}
.b-xian .badge-name{{color:#ff8c5a}}
.badge-type{{font-size:10px;color:#5c6773;margin:2px 0 6px}}
.badge-desc{{font-size:12px;color:#8a8f98}}
.chart{{display:flex;gap:10px;align-items:flex-end;height:120px;padding:10px;background:#11151f;border-radius:10px;border:1px solid #1c2230}}
.dcol{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.dbar{{width:36px;background:linear-gradient(180deg,#ffd166,#59c2ff);border-radius:4px 4px 0 0}}
.dlab{{font-size:11px;color:#5c6773}}
table{{width:100%;border-collapse:collapse;background:#11151f;border-radius:10px;overflow:hidden}}
td{{padding:8px 12px;font-size:13px;border-top:1px solid #1c2230}}
.xp{{color:#ffd166;font-weight:700;white-space:nowrap}}
.msg{{color:#8a8f98}}
.d-S{{color:#ff6666;font-weight:800}}.d-A{{color:#ffa759;font-weight:700}}.d-B{{color:#59c2ff}}.d-C{{color:#8a8f98}}.d-D{{color:#5c6773}}
.empty{{color:#5c6773;font-size:13px}}
</style></head><body><div class="wrap">
<h1>AI修仙模拟器</h1>
<div class="total">修为 Lv {state["total_level"]}<small>无上限 · 大道无涯</small></div>
<div class="tbar"><div class="tbar-fill" style="width:{t_pct}%"></div></div>
<div class="tnext">距突破还差 {round(state["total_need"] - state["total_in"])} 灵气</div>
<div class="meta">{f"✨紫气东来·余{state['buff_days']}日 · " if state.get("buff_days") else ""}连修 {state.get("streak", 0)} 日 · 亲身历练 {n_manual} · 阵法代劳 {n_auto}（灵气稀薄） · 法器：{src_label} · 更新于 {datetime.now(LOCAL_TZ).strftime("%m-%d %H:%M")}</div>
<div class="grid">{job_cards}</div>
<h2>机缘</h2><div class="badges">{badge_html}</div>
<h2>每日修行</h2><div class="chart">{day_bars}</div>
<h2>斩妖录</h2><table>{top_rows}</table>
</div></body></html>"""
    for p in DASHBOARD_PATHS:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(page)
        except OSError:
            pass


# ── 彩色机缘图标（Tk 8.6 渲不出彩色 emoji：无头浏览器渲一张图集，Tk 切片缓存成 PNG）──
EMOJI_CACHE = OUT_DIR / ".emoji_cache"
_ICON_BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def emoji_icon_path(ch, px=30):
    return EMOJI_CACHE / ("-".join(f"{ord(c):04x}" for c in ch) + f"_{px}.png")


def ensure_emoji_icons(chars, px=30, bg="#171b22"):
    """把缺的 emoji 渲成彩色小图，返回 {emoji: PNG路径}。渲不了的缺席，调用方回退字体剪影。"""
    want = []
    for ch in dict.fromkeys(chars):
        if ch and max(ord(c) for c in ch) >= 0x2100:
            want.append(ch)
    if not want:
        return {}
    todo = [ch for ch in want if not emoji_icon_path(ch, px).exists()]
    if todo:
        try:
            _render_emoji_atlas(todo, px, bg)
        except Exception:
            pass
    return {ch: emoji_icon_path(ch, px) for ch in want if emoji_icon_path(ch, px).exists()}


def _render_emoji_atlas(todo, px, bg):
    import time as _time
    browser = next((b for b in _ICON_BROWSERS if Path(b).exists()), None)
    if not browser:
        return
    EMOJI_CACHE.mkdir(parents=True, exist_ok=True)
    cell = px * 2
    cols = min(8, len(todo))
    rows = (len(todo) + cols - 1) // cols
    cells = []
    for i, ch in enumerate(todo):
        shown = ch if ("‍" in ch or ch.endswith("️")) else ch + "️"
        r, c = divmod(i, cols)
        cells.append(
            f'<div style="position:absolute;left:{c*cell}px;top:{r*cell}px;'
            f'width:{cell}px;height:{cell}px;line-height:{cell}px;text-align:center;'
            f'font-size:{px}px">{html.escape(shown)}</div>')
    page = (f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:{bg};'
            f'font-family:\'Segoe UI Emoji\',\'Apple Color Emoji\',sans-serif">'
            + "".join(cells) + "</body>")
    atlas_html = EMOJI_CACHE / "_atlas.html"
    atlas_png = EMOJI_CACHE / "_atlas.png"
    with open(atlas_html, "w", encoding="utf-8") as f:
        f.write(page)
    if atlas_png.exists():
        atlas_png.unlink()
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.run([
        browser, "--headless", "--disable-gpu", "--hide-scrollbars",
        f"--screenshot={atlas_png}", f"--window-size={cols*cell},{rows*cell}",
        f"--default-background-color={bg.lstrip('#')}", atlas_html.as_uri(),
    ], capture_output=True, timeout=60, creationflags=flags)
    for _ in range(20):
        if atlas_png.exists() and atlas_png.stat().st_size > 100:
            break
        _time.sleep(0.3)
    if not atlas_png.exists():
        return
    import tkinter as tk
    root = getattr(tk, "_default_root", None)
    own_root = root is None
    if own_root:
        root = tk.Tk()
        root.withdraw()
    try:
        atlas = tk.PhotoImage(master=root, file=str(atlas_png))
        for i, ch in enumerate(todo):
            r, c = divmod(i, cols)
            x1, y1 = c * cell, r * cell
            if x1 + cell > atlas.width() or y1 + cell > atlas.height():
                continue
            atlas.write(str(emoji_icon_path(ch, px)), format="png",
                        from_coords=(x1, y1, x1 + cell, y1 + cell))
    finally:
        if own_root:
            root.destroy()


# ── 境界徽章（十境界各一款：SVG 经无头浏览器渲成 PNG 缓存，贴纸直接贴图）──
MEDAL_PX = 80


def realm_medal_path(i, px=MEDAL_PX):
    return EMOJI_CACHE / f"medal_{i}_{px}.png"


def _medal_svg(i, px):
    import math as _m
    realm, c1, c2, glow, fx = REALM_STYLE[i]
    s = px
    c = s / 2
    ch = "虚" if realm == "炼虚" else realm[0]  # 炼气/炼虚首字撞车
    gl = f"filter:drop-shadow(0 0 {round(2 + glow * 7)}px {c1})" if glow > 0.1 else ""
    txt = (f'<text x="{c}" y="{c + 1}" text-anchor="middle" dominant-baseline="central" '
           f'font-family="KaiTi,STKaiti,serif" font-weight="bold" font-size="{round(s * 0.33)}" '
           f'fill="{c1}">{ch}</text>')

    def octagon(cx, cy, r):
        k = r * 0.414
        return (f"{cx-k},{cy-r} {cx+k},{cy-r} {cx+r},{cy-k} {cx+r},{cy+k} "
                f"{cx+k},{cy+r} {cx-k},{cy+r} {cx-r},{cy+k} {cx-r},{cy-k}")

    def hexagon(cx, cy, r):
        return " ".join(f"{cx + r * _m.sin(_m.radians(a))},{cy - r * _m.cos(_m.radians(a))}"
                        for a in range(0, 360, 60))

    def star8(cx, cy, r1, r2):
        pts = []
        for j in range(16):
            r = r1 if j % 2 == 0 else r2
            a = _m.radians(j * 22.5)
            pts.append(f"{cx + r * _m.sin(a)},{cy - r * _m.cos(a)}")
        return " ".join(pts)

    defs = (f'<defs><linearGradient id="g{i}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>'
            f'</linearGradient><linearGradient id="rb" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#ff5f6d"/><stop offset="0.3" stop-color="#ffd166"/>'
            f'<stop offset="0.55" stop-color="#7ddf64"/><stop offset="0.8" stop-color="#59c2ff"/>'
            f'<stop offset="1" stop-color="#b78aff"/></linearGradient></defs>')

    r_o, r_i = s * 0.42, s * 0.31
    if fx == "cloth":
        body = (f'<circle cx="{c}" cy="{c}" r="{r_o - 2}" fill="none" stroke="{c2}" stroke-width="5" '
                f'stroke-dasharray="4 2"/>'
                f'<circle cx="{c}" cy="{c}" r="{r_i}" fill="#12161d" stroke="{c1}" stroke-width="1.5"/>')
    elif fx == "iron":
        body = (f'<polygon points="{octagon(c, c, r_o)}" fill="url(#g{i})" stroke="{c1}" stroke-width="2"/>'
                f'<polygon points="{octagon(c, c, r_i)}" fill="#12161d"/>')
    elif fx == "bronze":
        studs = "".join(f'<circle cx="{c + (r_o - 1) * dx}" cy="{c + (r_o - 1) * dy}" r="2.4" fill="{c1}"/>'
                        for dx, dy in ((0.71, 0.71), (-0.71, 0.71), (0.71, -0.71), (-0.71, -0.71)))
        body = (f'<circle cx="{c}" cy="{c}" r="{r_o}" fill="url(#g{i})" stroke="{c2}" stroke-width="2"/>'
                f'{studs}<circle cx="{c}" cy="{c}" r="{r_i}" fill="#12161d"/>')
    elif fx == "silver":
        d = r_o + 2
        body = (f'<polygon points="{c},{c - d} {c + d},{c} {c},{c + d} {c - d},{c}" fill="url(#g{i})" '
                f'stroke="#f2f6fb" stroke-width="1.5" style="{gl}"/>'
                f'<polygon points="{c},{c - r_i - 2} {c + r_i + 2},{c} {c},{c + r_i + 2} {c - r_i - 2},{c}" '
                f'fill="#12161d"/>')
    elif fx == "gold":
        body = (f'<polygon points="{hexagon(c, c, r_o)}" fill="url(#g{i})" stroke="{c1}" '
                f'stroke-width="2" style="{gl}"/>'
                f'<polygon points="{hexagon(c, c, r_i)}" fill="#12161d"/>')
    elif fx == "glass":
        body = (f'<polygon points="{hexagon(c, c, r_o)}" fill="{c1}" fill-opacity="0.3" '
                f'stroke="{c1}" stroke-width="2" style="{gl}"/>'
                f'<ellipse cx="{c - s * 0.1}" cy="{c - s * 0.14}" rx="{s * 0.16}" ry="{s * 0.07}" '
                f'fill="#ffffff" fill-opacity="0.22" transform="rotate(-30 {c - s * 0.1} {c - s * 0.14})"/>'
                f'<polygon points="{hexagon(c, c, r_i)}" fill="#12161d" fill-opacity="0.7"/>')
    elif fx == "amethyst":
        body = (f'<polygon points="{star8(c, c, r_o + 2, r_o * 0.72)}" fill="url(#g{i})" '
                f'stroke="{c1}" stroke-width="1.5" style="{gl}"/>'
                f'<polygon points="{octagon(c, c, r_i)}" fill="#12161d"/>')
    elif fx == "jade":
        q = r_o * 2
        body = (f'<rect x="{c - r_o}" y="{c - r_o}" width="{q}" height="{q}" rx="{s * 0.14}" '
                f'fill="url(#g{i})" stroke="#ffffff" stroke-width="1.2" style="{gl}"/>'
                f'<rect x="{c - r_i}" y="{c - r_i}" width="{r_i * 2}" height="{r_i * 2}" rx="{s * 0.09}" '
                f'fill="#12161d"/>')
    elif fx == "stormjade":
        zig = (f'<polyline points="{s*0.13},{s*0.18} {s*0.2},{s*0.3} {s*0.15},{s*0.3} {s*0.22},{s*0.44}" '
               f'fill="none" stroke="#dff1ff" stroke-width="2" stroke-linecap="round" style="{gl}"/>'
               f'<polyline points="{s*0.87},{s*0.56} {s*0.8},{s*0.68} {s*0.85},{s*0.68} {s*0.78},{s*0.82}" '
               f'fill="none" stroke="#dff1ff" stroke-width="2" stroke-linecap="round" style="{gl}"/>')
        body = (f'<polygon points="{octagon(c, c, r_o)}" fill="url(#g{i})" stroke="{c1}" '
                f'stroke-width="2" style="{gl}"/>'
                f'<polygon points="{octagon(c, c, r_i)}" fill="#12161d"/>{zig}')
    else:  # dao 飞升
        body = (f'<circle cx="{c}" cy="{c}" r="{r_o - 1}" fill="none" stroke="url(#rb)" '
                f'stroke-width="5" style="{gl}"/>'
                f'<circle cx="{c}" cy="{c}" r="{r_i}" fill="#12161d" stroke="#ffd166" stroke-width="1.5"/>')
        txt = txt.replace(f'fill="{c1}"', 'fill="#ffffff"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" '
            f'viewBox="0 0 {s} {s}">{defs}{body}{txt}</svg>')


def ensure_realm_medals(px=MEDAL_PX, bg="#171b22"):
    """十境界徽章 PNG 缓存，返回 {境界名: 路径}。渲不了则空，调用方回退手绘。"""
    import time as _time
    missing = [i for i in range(len(REALM_STYLE)) if not realm_medal_path(i, px).exists()]
    if missing:
        browser = next((b for b in _ICON_BROWSERS if Path(b).exists()), None)
        if browser:
            try:
                EMOJI_CACHE.mkdir(parents=True, exist_ok=True)
                n = len(REALM_STYLE)
                cells = "".join(
                    f'<div style="position:absolute;left:{j * px}px;top:0">{_medal_svg(j, px)}</div>'
                    for j in range(n))
                page = (f'<!doctype html><meta charset="utf-8">'
                        f'<body style="margin:0;background:{bg}">{cells}</body>')
                mhtml = EMOJI_CACHE / "_medals.html"
                mpng = EMOJI_CACHE / "_medals.png"
                with open(mhtml, "w", encoding="utf-8") as f:
                    f.write(page)
                if mpng.exists():
                    mpng.unlink()
                flags = 0x08000000 if os.name == "nt" else 0
                subprocess.run([
                    browser, "--headless", "--disable-gpu", "--hide-scrollbars",
                    f"--screenshot={mpng}", f"--window-size={n * px},{px}",
                    f"--default-background-color={bg.lstrip('#')}", mhtml.as_uri(),
                ], capture_output=True, timeout=60, creationflags=flags)
                for _ in range(20):
                    if mpng.exists() and mpng.stat().st_size > 100:
                        break
                    _time.sleep(0.3)
                if mpng.exists():
                    import tkinter as tk
                    root = getattr(tk, "_default_root", None)
                    own = root is None
                    if own:
                        root = tk.Tk()
                        root.withdraw()
                    try:
                        atlas = tk.PhotoImage(master=root, file=str(mpng))
                        for j in range(n):
                            if (j + 1) * px <= atlas.width():
                                atlas.write(str(realm_medal_path(j, px)), format="png",
                                            from_coords=(j * px, 0, (j + 1) * px, px))
                    finally:
                        if own:
                            root.destroy()
            except Exception:
                pass
    return {REALM_STYLE[j][0]: realm_medal_path(j, px)
            for j in range(len(REALM_STYLE)) if realm_medal_path(j, px).exists()}
