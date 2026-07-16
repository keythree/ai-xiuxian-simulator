"""AI修仙模拟器 · 新法器样本打包：自动找到未接入 AI 工具的会话日志，打包放到桌面。

你不用知道文件在哪，这个脚本自己找。打包出来的 zip 发给开发者（GitHub 开
Issue 或群里发），拿到样本很快就能接入，你的历史使用会一并结算进修为。

注意：样本里是你和 AI 的对话记录原文。介意的话，先解压打开看一遍，删掉
不想给人看的文件再发。
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
    sp = str(detect_path)
    pats = ("**/*.jsonl", "**/*.json", "**/*.log")
    if "*" in sp:
        import glob as _g
        return [(Path(d), pat) for d in _g.glob(sp) for pat in pats]
    return [(Path(sp), pat) for pat in pats]


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
                if 50 < st.st_size <= MAX_MB * 1024 * 1024:
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
            for f in samples:
                z.write(f, f"{name}/{f.name}")
                manifest.append(f"{name}/{f.name}  <-  {f}")
                packed += 1
            print(f"· {name}：打包了最近 {len(samples)} 个会话文件")
        z.writestr("清单.txt", "\n".join(manifest) + "\n")
    print()
    print(f"样本包已放到桌面：{out}")
    print("发之前可以自己解压检查一遍，里面是你和 AI 的对话记录，介意的删掉再发。")
    print("发到 GitHub Issue 或群里，拿到样本很快就能接入。")


if __name__ == "__main__":
    main()
