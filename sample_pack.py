"""AI修仙模拟器 · 新法器样本打包：自动找到未接入 AI 工具的会话日志，打包放到桌面。

你不用知道文件在哪，这个脚本自己找。打包出来的 zip 发给开发者（GitHub 开
Issue 或群里发），拿到样本很快就能接入，你的历史使用会一并结算进修为。

打包时自动脱敏：对话正文全部替换成「[已脱敏 N 字符]」占位符，只保留
结构（键名/类型/时间戳/角色，接入写解析器够用）；密钥/令牌/JWT 打码、
邮箱换占位符、本机用户目录换成 ~；凭据类文件直接不收。
"""
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core

MAX_MB = 5      # 单文件上限，避免打出巨包
PER_TOOL = 3    # 每个工具取最近 N 个文件


def _sample_roots(name, detect_path):
    """每个工具的会话日志可能在哪。默认在探测目录下找 json/jsonl/log。"""
    if name == "GitHub Copilot (VS Code)":
        u = core._VSC_STORE.parent  # VS Code 的 User 目录
        return [(u / "workspaceStorage", "*/chatSessions/*.json"),
                (u / "globalStorage", "*copilot*/**/*.json")]
    if name == "Trae":
        t = Path(str(detect_path))
        return [(t / "User" / "workspaceStorage", "*/chatSessions/*.json"),
                (t / "User" / "globalStorage", "*/*.json")]
    if name == "JetBrains IDE (AI Assistant/Junie)":
        j = Path(str(detect_path))
        return [(j, "*/options/*ai*.xml"), (j, "*/options/*junie*.xml"),
                (j, "*/aiAssistant/**/*.json"), (j, "*/junie/**/*.json*")]
    sp = str(detect_path)
    pats = ("**/*.jsonl", "**/*.json", "**/*.log")
    if "*" in sp:
        import glob as _g
        return [(Path(d), pat) for d in _g.glob(sp) for pat in pats]
    return [(Path(sp), pat) for pat in pats]


import re

_CRED_NAMES = re.compile(r"(?i)(auth|token|cred|secret|password|apps\.json|hosts\.json|\.pem$|\.key$)")
_CRED_CONTENT = re.compile(
    r"(?i)(oauth_token|access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret"
    r"|gh[oupsr]_[A-Za-z0-9]{16}|sk-[A-Za-z0-9\-_]{16}|-----BEGIN)")

# 工具名可能含 / \ 等字符（如 JetBrains IDE (AI Assistant/Junie)），
# 直接当 zip 内目录名会被解压成多层嵌套目录，统一替换成 -
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')

def _safe_dirname(name):
    return _ILLEGAL_CHARS.sub("-", name).strip()


# 内容脱敏：密钥/令牌值打码、邮箱换占位符、私钥块整体抹掉，尽量不破坏 JSON/XML 结构
_REDACT_RULES = [
    (re.compile(r"-----BEGIN[^-]{0,40}-----[\s\S]*?-----END[^-]{0,40}-----"), "***REDACTED***"),
    # Bearer <token> 要先于通用 key/value 规则：后者按非空格截断，只会打码 Bearer 一词
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/=]{8,}"), r"\1***"),
    (re.compile(r"(?i)(\"?(?:oauth[_-]?token|access[_-]?token|refresh[_-]?token|id[_-]?token"
                r"|api[_-]?key|client[_-]?secret|password|authorization|bearer)\"?\s*[:=]\s*\"?)"
                r"[^\"'\s,}\]]+"), r"\1***"),
    (re.compile(r"gh[oupsr]_[A-Za-z0-9]{16,}"), "***"),
    (re.compile(r"sk-[A-Za-z0-9\-_]{16,}"), "***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"), "***"),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "user@example.com"),
]


def _mask_home(text):
    """本机主目录（含用户名）统一替换成 ~，兼顾原样、JSON 双反斜杠、正斜杠三种写法。"""
    home = str(Path.home())
    for h in (home.replace("\\", "\\\\"), home, home.replace("\\", "/")):
        text = text.replace(h, "~")
    return text


def _scrub(text):
    text = _mask_home(text)
    for pat, rep in _REDACT_RULES:
        text = pat.sub(rep, text)
    return text


# 对话正文只留占位符：接入只需要结构（键名/类型/时间戳/角色），不需要内容。
# 命中下列键名的字符串值，或任意超长字符串，都换成带长度的占位符。
_TEXT_KEYS = re.compile(
    r"(?i)^(content|text|message|prompt|completion|response|body|thinking|reasoning"
    r"|code|diff|patch|command|output|result|stdout|stderr|snippet|input|query"
    r"|question|answer|title|summary|description|markdown|html|delta|value)$")
_LONG = 150


def _ph(s):
    return f"[已脱敏 {len(s)} 字符]"


def _strip_values(node, key=None):
    if isinstance(node, dict):
        return {k: _strip_values(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_values(v, key) for v in node]
    if isinstance(node, str) and node and (_TEXT_KEYS.match(key or "") or len(node) > _LONG):
        return _ph(node)
    return node


def _placeholder(text, suffix):
    """按文件类型把对话正文换成占位符，保留结构供写解析器。"""
    import json
    if suffix == ".json":
        try:
            return json.dumps(_strip_values(json.loads(text)), ensure_ascii=False, indent=1)
        except (ValueError, RecursionError):
            pass
    if suffix in (".json", ".jsonl", ".log"):  # jsonl 或 json-lines 风格的 log
        out = []
        for line in text.splitlines():
            t = line.strip()
            if t.startswith("{") or t.startswith("["):
                try:
                    out.append(json.dumps(_strip_values(json.loads(t)), ensure_ascii=False))
                    continue
                except (ValueError, RecursionError):
                    pass
            out.append(_ph(line) if len(line) > _LONG * 2 else line)
        return "\n".join(out)
    # XML 等：标签间文本与属性值超长的换占位符，标签结构不动
    text = re.sub(r">([^<>]{%d,})<" % _LONG, lambda m: ">" + _ph(m.group(1)) + "<", text)
    text = re.sub(r'="([^"]{%d,})"' % _LONG, lambda m: '="' + _ph(m.group(1)) + '"', text)
    return text


def _looks_credential(f):
    """凭据文件绝不入包：整个文件就是存密钥的，脱敏了也没有样本价值。"""
    if _CRED_NAMES.search(f.name):
        return True
    try:
        head = f.read_bytes()[:8192].decode("utf-8", errors="replace")
    except OSError:
        return True
    return bool(_CRED_CONTENT.search(head))


def _collect(roots):
    files = []
    for root, pat in roots:
        if not root.exists():
            continue
        try:
            for f in root.glob(pat):
                if not f.is_file():
                    continue
                st = f.stat()
                if 50 < st.st_size <= MAX_MB * 1024 * 1024 and not _looks_credential(f):
                    files.append((st.st_mtime, f))
        except OSError:
            continue
    files.sort(key=lambda t: t[0], reverse=True)
    return [f for _, f in files[:PER_TOOL]]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 46)
    print("  AI修仙模拟器 · 新法器样本打包")
    print("=" * 46)
    print()
    import glob as _glob
    found = {}
    for name, p in core.UNSUPPORTED_TOOLS:
        sp = str(p)
        hit = _glob.glob(sp) if "*" in sp else (p.exists() and [sp] or [])
        if not hit:
            continue
        samples = _collect(_sample_roots(name, p))
        found[name] = samples
    if not found:
        print("没发现未接入的 AI 工具，你在用的都已经支持了。")
        return
    out = core.desktop_dir() / "AI修仙-新法器样本.zip"
    manifest = []
    packed = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, samples in found.items():
            if not samples:
                manifest.append(f"{name}: 探测到在用，但没找到会话日志文件（可能存在云端或别的位置）")
                print(f"· {name}：探测到在用，但没自动找到日志，接入时可能要人工看一眼")
                continue
            n_ok = 0
            for j, f in enumerate(samples):
                arc = f"{_safe_dirname(name)}/{j}_{f.name}"  # 加序号防同名互相覆盖
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    manifest.append(f"{name}: 读取失败已跳过  <-  {_mask_home(str(f))}")
                    continue
                z.writestr(arc, _scrub(_placeholder(text, f.suffix.lower())))
                manifest.append(f"{arc}  <-  {_mask_home(str(f))}")
                n_ok += 1
            packed += n_ok
            skipped = len(samples) - n_ok
            tail = f"，{skipped} 个读取失败跳过" if skipped else ""
            print(f"· {name}：打包了 {n_ok} 个会话文件（正文已换占位符{tail}）")
        z.writestr("清单.txt", "\n".join(manifest) + "\n")
    print()
    print(f"样本包已放到桌面：{out}")
    print("已自动脱敏：对话正文全部换成占位符（只留结构），密钥/令牌打码、用户目录换成 ~。")
    print("发之前仍可自己解压检查一遍，放心后发到 GitHub Issue 或群里，拿到样本很快就能接入。")


if __name__ == "__main__":
    main()
