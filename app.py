# -*- coding: utf-8 -*-
"""AI修仙模拟器 入口（Windows/macOS 通用）
双击打开：首次运行走图形安装向导（取道号 → 结算历史 → 挂自动结算），
装完直接弹出主界面（桌面任务贴纸）；之后再双击就是打开贴纸。
子命令（供 hook / 计划任务调用，用户不用管）：
  settle          Claude Code Stop hook 实时结算（stdin 收 JSON）
  scan [--notify] 全量重建
  card [道号] [--open]
  weekly [--open]
  toast '<json>'
  sticky [--follow]
"""
import sys, io

# 窗口版没有标准流，补上假流防 print 崩溃
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

FONT = "Microsoft YaHei" if sys.platform == "win32" else \
       ("PingFang SC" if sys.platform == "darwin" else "Noto Sans CJK SC")

C = {"bg": "#0b0e14", "card": "#141926", "gold": "#ffd166", "dim": "#8a8f98",
     "dimmer": "#4a5160", "blue": "#59c2ff", "green": "#3fb950"}


def dispatch():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "settle":
        import settle
        try:
            settle.main()
        except Exception:
            pass
        sys.exit(0)
    if cmd == "scan":
        sys.argv = ["scan"] + args[1:]
        import scan
        scan.main()
        sys.exit(0)
    if cmd == "card":
        sys.argv = ["card"] + args[1:]
        import card
        card.main()
        sys.exit(0)
    if cmd == "weekly":
        sys.argv = ["weekly"] + args[1:]
        import weekly
        weekly.main()
        sys.exit(0)
    if cmd == "toast":
        sys.argv = ["toast"] + args[1:]
        import toast
        try:
            toast.main()
        except Exception:
            pass
        sys.exit(0)
    if cmd == "sticky":
        sys.argv = ["sticky"] + args[1:]
        import sticky
        try:
            sticky.main()
        except Exception:
            pass
        sys.exit(0)
    if cmd == "stickyboot":
        # SessionStart hook 用：派生独立贴纸进程后立刻退出，不占 hook 生命周期
        launch_sticky(follow=True)
        sys.exit(0)
    gui()


def launch_sticky(follow=False):
    """独立进程拉起桌面贴纸（主界面）。follow=True 时尊重当天手动关闭。"""
    import subprocess
    from pathlib import Path
    import core
    py = Path(sys.executable)
    if core.IS_WIN:
        pyw = py.with_name("pythonw.exe")
        exe = str(pyw if pyw.exists() else py)
        kw = {"creationflags": 0x00000008 | 0x00000200, "close_fds": True}
    else:
        exe = str(py)
        kw = {"start_new_session": True, "close_fds": True}
    args = [exe, str(Path(__file__).resolve().parent / "sticky.py")]
    if follow:
        args.append("--follow")
    try:
        subprocess.Popen(args, cwd=str(Path(__file__).resolve().parent), **kw)
    except Exception:
        pass


def gui():
    import json, threading
    import tkinter as tk
    import core

    def has_save():
        try:
            with open(core.STATE, encoding="utf-8") as f:
                json.load(f)
            return core.CONFIG.exists()
        except Exception:
            return False

    # 已装过：直接开主界面（贴纸），不再弹任何窗口
    if has_save():
        launch_sticky()
        return

    root = tk.Tk()
    root.title("AI修仙模拟器")
    root.configure(bg=C["bg"])
    root.resizable(False, False)

    body = tk.Frame(root, bg=C["bg"], padx=34, pady=26)
    body.pack()
    status = tk.StringVar(value="")

    def put(msg):
        root.after(0, status.set, msg)

    tk.Label(body, text="A I 修 仙 模 拟 器", font=(FONT, 13), fg=C["dim"], bg=C["bg"]).pack()
    tk.Label(body, text="把你用 AI 干活这件事\n变成一场修仙", font=(FONT, 17, "bold"),
             fg=C["gold"], bg=C["bg"], pady=14).pack()
    tk.Label(body, text="给自己取个道号", font=(FONT, 11), fg=C["dim"], bg=C["bg"]).pack(pady=(8, 4))
    name_var = tk.StringVar(value="")
    ent = tk.Entry(body, textvariable=name_var, font=(FONT, 14), justify="center",
                   bg=C["card"], fg="#e6e1cf", insertbackground=C["gold"],
                   relief="flat", width=16)
    ent.pack(ipady=6)
    ent.focus_set()
    btn = tk.Label(body, text="开 始 修 行", font=(FONT, 13, "bold"), fg="#0b0e14",
                   bg=C["gold"], padx=30, pady=8, cursor="hand2")
    btn.pack(pady=18)
    tk.Label(body, textvariable=status, font=(FONT, 9), fg=C["dim"],
             bg=C["bg"], justify="left", wraplength=300).pack()

    def install():
        btn.unbind("<Button-1>")
        ent.unbind("<Return>")
        btn.config(bg=C["dimmer"], text="结算历史中…")
        name = name_var.get().strip() or "无名道友"

        def work():
            import setup as setup_mod
            setup_mod.write_config(name)
            ok = setup_mod.first_scan(log=put)
            if not ok:
                put("未发现 Claude Code / Codex 的使用数据。\n先用一段时间 AI 再打开我。")
                root.after(0, btn.config, {"bg": C["gold"], "text": "重 试"})
                root.after(0, lambda: btn.bind("<Button-1>", lambda e: install()))
                root.after(0, lambda: ent.bind("<Return>", lambda e: install()))
                return
            setup_mod.install_schedule(log=put)
            setup_mod.install_claude_hook(log=put)
            put("安装完成，正在打开主界面…")
            root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def finish():
        launch_sticky()
        root.after(600, root.destroy)

    btn.bind("<Button-1>", lambda e: install())
    ent.bind("<Return>", lambda e: install())

    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")
    root.mainloop()


if __name__ == "__main__":
    dispatch()
