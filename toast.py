# -*- coding: utf-8 -*-
"""AI修仙模拟器 突破弹窗：右下角游戏式金色通知，几秒自动消失。
用法: pythonw toast.py '["修为精进 Lv12 → Lv13", "得隐藏机缘 · 暗夜苦修"]'
"""
import json, sys, subprocess
from pathlib import Path
import tkinter as tk

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
CHIME = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "chime.wav"
FONT = "Microsoft YaHei" if IS_WIN else ("PingFang SC" if IS_MAC else "Noto Sans CJK SC")

def play_sound(events):
    try:
        if IS_WIN:
            import winsound
            if any("⚠" in e for e in events):
                winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
            elif CHIME.exists():
                winsound.PlaySound(str(CHIME), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep()
        elif IS_MAC:
            if any("⚠" in e for e in events):
                subprocess.Popen(["afplay", "/System/Library/Sounds/Sosumi.aiff"])
            elif CHIME.exists():
                subprocess.Popen(["afplay", str(CHIME)])
    except Exception:
        pass

def main():
    events = json.loads(sys.argv[1]) if len(sys.argv) > 1 else ["突破"]
    play_sound(events)
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.0)
    root.configure(bg="#0b0e14")

    frame = tk.Frame(root, bg="#0b0e14", highlightbackground="#ffd166",
                     highlightthickness=2, padx=22, pady=14)
    frame.pack()
    tk.Label(frame, text="⚡ AI修仙模拟器", font=(FONT, 9), fg="#8a8f98", bg="#0b0e14").pack(anchor="w")
    for e in events[:6]:
        if "⚠" in e:
            fg, fnt = "#ff7b72", (FONT, 13, "bold")
        elif e.startswith("「"):
            fg, fnt = "#8a8f98", (FONT, 10)
        elif "历练完成" in e:
            fg, fnt = "#3fb950", (FONT, 13, "bold")
        elif "机缘" in e:
            fg, fnt = "#c792ea", (FONT, 13, "bold")
        elif "突破" in e and "修为" not in e:
            fg, fnt = "#ff8c66", (FONT, 13, "bold")
        else:
            fg, fnt = "#ffd166", (FONT, 13, "bold")
        tk.Label(frame, text=e, font=fnt, fg=fg, bg="#0b0e14").pack(anchor="w", pady=2)

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{sw - w - 24}+{sh - h - 72}")

    def fade(alpha=0.0):
        alpha += 0.12
        root.attributes("-alpha", min(alpha, 0.96))
        if alpha < 0.96:
            root.after(30, fade, alpha)
    def fade_out(alpha=0.96):
        alpha -= 0.08
        root.attributes("-alpha", max(alpha, 0.0))
        if alpha > 0:
            root.after(30, fade_out, alpha)
        else:
            root.destroy()
    fade()
    root.after(4200, fade_out)
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
