# -*- coding: utf-8 -*-
"""AI修仙模拟器 等级分享卡生成器 v2
1080x1350 竖卡：材质境界徽章（布→铁→铜→银→金→琉璃→紫晶→白玉→青玉→虹彩）
+ 八道雷达图 + 横向境界柱状图 + 机缘胶囊。无头浏览器截图出 PNG 到桌面。
黑箱纪律：卡上只有等级/境界/机缘名，绝不出现任何经验数值和机缘条件。
用法: python card.py [道号]   （默认道号：导演BK）
"""
import json, sys, os, subprocess, time, math
from pathlib import Path
from datetime import datetime
import core

BROWSERS = ([
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
] if core.IS_WIN else [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
])
CARD_HTML = core.OUT_DIR / "card.html"
CARD_PNG = core.desktop_dir() / "AI修仙模拟器-等级卡.png"

REALM_STYLE = core.REALM_STYLE

def octagon_points(cx, cy, r, rot=22.5):
    pts = []
    for i in range(8):
        a = math.radians(i * 45 + rot - 90)
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)

def radar_svg(levels):
    size, cx, cy, R = 420, 210, 218, 150
    rings = "".join(
        f'<polygon points="{octagon_points(cx, cy, R * k)}" fill="none" stroke="#242b3a" stroke-width="1.2"/>'
        for k in (0.25, 0.5, 0.75, 1.0))
    axes, labels = "", ""
    data_pts = []
    for i, j in enumerate(core.JOBS):
        a = math.radians(i * 45 - 90)
        x2, y2 = cx + R * math.cos(a), cy + R * math.sin(a)
        axes += f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#242b3a" stroke-width="1"/>'
        lx, ly = cx + (R + 34) * math.cos(a), cy + (R + 30) * math.sin(a)
        lv = levels[j]
        style_i = core.band_index(lv)
        color = REALM_STYLE[style_i][1] if lv <= 1 else REALM_STYLE[style_i][2]
        label_color = "#8a8f98" if lv > 1 else "#4a5160"
        labels += (f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="22" '
                   f'fill="{label_color}" font-family="Microsoft YaHei">{j}</text>'
                   f'<text x="{lx:.1f}" y="{ly + 24:.1f}" text-anchor="middle" font-size="18" font-weight="bold" '
                   f'fill="#ffd166" font-family="Microsoft YaHei">Lv{lv}</text>')
        frac = max((lv / 99) ** 0.7, 0.045)
        data_pts.append(f"{cx + R * frac * math.cos(a):.1f},{cy + R * frac * math.sin(a):.1f}")
    poly = " ".join(data_pts)
    return f"""<svg width="{size}" height="470" viewBox="0 0 {size} 470" xmlns="http://www.w3.org/2000/svg">
      {rings}{axes}
      <polygon points="{poly}" fill="rgba(255,209,102,.22)" stroke="#ffd166" stroke-width="2.5" stroke-linejoin="round"/>
      {labels}
    </svg>"""

def heatmap_html(ledger, max_weeks=12):
    """每日灵气热力图（金墙），只显示节奏不泄露内容。
    窗口自适应：从有数据的第一周画起（最少 6 周保形状），攒满后封顶 max_weeks，避免大片死黑。"""
    from datetime import timedelta
    day_xp = {}
    for r in ledger:
        day_xp[r["day"]] = day_xp.get(r["day"], 0) + r.get("total_xp", 0)
    today = datetime.now(core.LOCAL_TZ).date()
    active = sorted(d for d, v in day_xp.items() if v > 0)
    if active:
        first = datetime.strptime(active[0], "%Y-%m-%d").date()
        data_weeks = ((today - first).days // 7) + 1
    else:
        data_weeks = 1
    weeks = max(6, min(max_weeks, data_weeks))
    start = today - timedelta(days=today.isoweekday() - 1 + (weeks - 1) * 7)
    cells = ""
    for col in range(weeks):
        col_html = ""
        for row in range(7):
            d = start + timedelta(days=col * 7 + row)
            if d > today:
                col_html += '<i style="background:transparent"></i>'
                continue
            v = day_xp.get(d.strftime("%Y-%m-%d"), 0)
            c = "#171c28" if v <= 0 else ("#5d4d20" if v < 300 else ("#a8842b" if v < 1500 else "#ffd166"))
            col_html += f'<i style="background:{c}"></i>'
        cells += f'<div class="hcol">{col_html}</div>'
    return cells


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else core.player_name()
    with open(core.STATE, encoding="utf-8") as f:
        state = json.load(f)
    ledger = core.load_ledger()
    manual = [r for r in ledger if not r["auto"]]
    n_days = len({r["day"] for r in manual})
    n_tasks = len(manual)
    srcs = sorted({r.get("src", "claude-code") for r in ledger})
    src_label = " × ".join(core.SRC_NAMES.get(s, s) for s in srcs)

    levels = state["levels"]
    main_job = max(core.JOBS, key=lambda j: (levels[j], state["job_xp"].get(j, 0)))
    main_lv = levels[main_job]
    mi = core.band_index(main_lv)
    m_realm, m_c1, m_c2, m_glow, m_fx = REALM_STYLE[mi]

    # 横向柱状：颜色 = 该道境界材质
    bars = ""
    for j in sorted(core.JOBS, key=lambda j: -levels[j]):
        lv = levels[j]
        bi = core.band_index(lv)
        _, c1, c2, glow, _fx = REALM_STYLE[bi]
        w = max((lv / 99) ** 0.7 * 100, 3.5)
        shadow = f"box-shadow:0 0 {int(14 * glow + 2)}px {c1}66;" if glow > 0.2 else ""
        dim = "opacity:.5" if lv <= 1 else ""
        bars += f"""
        <div class="brow" style="{dim}">
          <span class="bname">{j}</span>
          <div class="btrack"><div class="bfill" style="width:{w:.1f}%;background:linear-gradient(90deg,{c2},{c1});{shadow}"></div></div>
          <span class="blv">Lv {lv}</span>
          <span class="btitle">{core.realm_of(lv)}·{core.title_of(j, lv)}</span>
        </div>"""

    def medal_html(b):
        n, t = b[0], b[1]
        ico = b[3] if len(b) > 3 else "🔸"
        cls = "hid" if t == "隐藏" else ("mile" if t == "里程碑" else "rare")
        return f'<div class="bm {cls}"><div class="bi">{ico}</div><div class="bn">{n}</div></div>'

    blist = state["badges"]
    counter = (f'<div class="bm more"><div class="bi">…</div>'
               f'<div class="bn">{len(blist)} / {core.TOTAL_BADGES}</div></div>')
    if len(blist) > 15:  # 勋章墙最多两行：稀有优先展示，其余收进收集进度（黑箱钩子）
        order = {"隐藏": 0, "奇遇": 1, "首次": 1, "里程碑": 2}
        shown_set = {tuple(b) for b in sorted(blist, key=lambda b: order.get(b[1], 3))[:15]}
        shown = [b for b in blist if tuple(b) in shown_set]
        badges = "".join(medal_html(b) for b in shown) + counter
    elif blist:
        badges = "".join(medal_html(b) for b in blist) + counter
    else:
        badges = f'<div class="bm more"><div class="bi">？</div><div class="bn">0 / {core.TOTAL_BADGES}</div></div>'

    page = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1350px;background:
  radial-gradient(ellipse 700px 500px at 50% -80px, rgba(255,209,102,.13), transparent 65%),
  radial-gradient(ellipse 500px 400px at 88% 105%, rgba(108,63,197,.16), transparent 60%),
  #0b0e14;
  color:#e6e1cf;font-family:"Microsoft YaHei","PingFang SC",sans-serif;overflow:hidden;
  padding:52px 80px 40px;display:flex;flex-direction:column;position:relative}}
.brand{{text-align:center;font-size:24px;letter-spacing:14px;color:#8a8f98}}
.dao{{text-align:center;margin-top:16px;font-size:38px;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC"}}
.hero{{display:flex;align-items:center;justify-content:center;gap:56px;margin-top:26px}}
.medal{{width:172px;height:172px;position:relative;flex:none;
  clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%);
  background:linear-gradient(150deg,{m_c1},{m_c2} 60%,{m_c1});
  display:flex;flex-direction:column;align-items:center;justify-content:center}}
.medal::before{{content:"";position:absolute;inset:9px;
  clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%);
  background:#0b0e14}}
.medal::after{{content:"";position:absolute;inset:9px;
  clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%);
  background:linear-gradient(150deg,{m_c1}33,{m_c2}22 55%,{m_c1}2e);}}
.medal.cloth::after{{background:
  repeating-linear-gradient(45deg,{m_c1}26 0 5px,{m_c2}30 5px 10px),
  repeating-linear-gradient(-45deg,{m_c1}1f 0 5px,transparent 5px 10px)}}
.medal.glass::after,.medal.jade::after,.medal.stormjade::after{{background:
  radial-gradient(circle at 32% 26%,#ffffff45,transparent 46%),
  linear-gradient(150deg,{m_c1}40,{m_c2}30)}}
.medal .r{{position:relative;z-index:2;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";font-size:52px;color:{m_c1};
  text-shadow:0 0 {int(26 * m_glow + 2)}px {m_c1}}}
.medal .rl{{position:relative;z-index:2;font-size:15px;letter-spacing:5px;color:#8a8f98;margin-top:4px}}
.medal-wrap{{filter:drop-shadow(0 0 {int(30 * m_glow + 2)}px {m_c1}{"aa" if m_glow > 0.3 else "44"})}}
.cult .lv{{font-size:120px;font-weight:800;color:#ffd166;line-height:1;text-shadow:0 0 55px rgba(255,209,102,.35)}}
.cult .lab{{font-size:22px;color:#8a8f98;letter-spacing:8px;margin-top:8px;text-align:center}}
.main-title{{text-align:center;margin-top:26px;font-size:34px;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";color:#59c2ff}}
.mid{{display:flex;align-items:center;gap:30px;margin-top:16px}}
.radar{{flex:none;margin-left:-16px}}
.bars{{flex:1;display:flex;flex-direction:column;gap:19px}}
.brow{{display:flex;align-items:center;gap:12px}}
.bname{{font-size:22px;width:52px;flex:none}}
.btrack{{width:200px;flex:none;height:20px;background:#171c28;border-radius:10px;overflow:hidden;border:1px solid #1f2635}}
.bfill{{height:100%;border-radius:10px}}
.blv{{font-size:20px;font-weight:700;color:#ffd166;width:64px;flex:none}}
.btitle{{font-size:17px;color:#6f7787;white-space:nowrap}}
h3{{margin:20px 0 12px;font-size:20px;color:#8a8f98;letter-spacing:6px;font-weight:400;text-align:center}}
.hwrap{{display:flex;justify-content:center;gap:4px;margin-top:4px}}
.hcol{{display:flex;flex-direction:column;gap:4px}}
.hcol i{{width:13px;height:13px;border-radius:3px;display:block}}
.hcap{{text-align:center;font-size:15px;color:#5c6773;margin-top:8px}}
.seal{{position:absolute;right:84px;bottom:104px;width:92px;height:92px;background:#9e2b25;
  border-radius:10px;transform:rotate(-7deg);display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 24px rgba(158,43,37,.4);opacity:.92}}
.seal span{{font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";font-size:56px;color:#f3e2d0;font-weight:700}}
.pills{{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}}
.bwall{{display:flex;flex-wrap:wrap;gap:8px 4px;justify-content:center}}
.bm{{width:100px;text-align:center}}
.bi{{width:50px;height:50px;margin:0 auto;border-radius:50%;font-size:23px;
  display:flex;align-items:center;justify-content:center;border:2px solid #3a4150;
  background:radial-gradient(circle at 32% 28%, #242b3a, #10141d)}}
.bm.hid .bi{{border-color:#8a5cd6;box-shadow:0 0 15px rgba(138,92,214,.5)}}
.bm.mile .bi{{border-color:#b8912f;box-shadow:0 0 10px rgba(255,209,102,.3)}}
.bm.rare .bi{{border-color:#3e9e9a;box-shadow:0 0 10px rgba(127,216,212,.35)}}
.bn{{margin-top:4px;font-size:14px;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";color:#c9c2a8}}
.bm.hid .bn{{color:#c792ea}}
.bm.more .bi{{color:#8a8f98;font-size:22px}}
.bm.more .bn{{color:#8a8f98}}
.foot{{margin-top:auto;display:flex;justify-content:space-between;align-items:baseline;
  color:#5c6773;font-size:20px}}
.foot .slogan{{font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";font-size:24px;color:#8a8f98;letter-spacing:4px}}
</style></head><body>
<div class="brand">AI修仙模拟器</div>
<div class="dao">道友 · {name}</div>
<div class="hero">
  <div class="medal-wrap"><div class="medal {m_fx}"><span class="r">{m_realm}</span><span class="rl">主修境界</span></div></div>
  <div class="cult"><div class="lv">Lv {state["total_level"]}</div><div class="lab">修为</div></div>
</div>
<div class="main-title">主修 {core.realm_of(main_lv)} · {core.title_of(main_job, main_lv)}</div>
<div class="mid">
  <div class="radar">{radar_svg(levels)}</div>
  <div class="bars">{bars}</div>
</div>
<h3>机缘 · 尚有未悟之缘</h3>
<div class="bwall">{badges}</div>
<h3>修行足迹</h3>
<div class="hwrap">{heatmap_html(ledger)}</div>
<div class="hcap">每格一日 · 越亮修行越勤</div>
<div class="seal"><span>修</span></div>
<div class="foot">
  <span>修行 {n_days} 日 · 历练 {n_tasks} 次 · 法器 {src_label}</span>
  <span class="slogan">大道无涯，道友几级了</span>
  <span>{datetime.now(core.LOCAL_TZ).strftime("%Y-%m-%d")}</span>
</div>
</body></html>"""

    with open(CARD_HTML, "w", encoding="utf-8") as f:
        f.write(page)

    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        print("未找到 Edge/Chrome，卡片以网页版打开:", CARD_HTML)
        core.open_path(CARD_HTML)
        return
    if CARD_PNG.exists():
        CARD_PNG.unlink()
    subprocess.run([
        browser, "--headless", "--disable-gpu", "--hide-scrollbars",
        f"--screenshot={CARD_PNG}", "--window-size=1080,1350",
        "--default-background-color=0b0e14", CARD_HTML.as_uri(),
    ], capture_output=True, timeout=60)
    for _ in range(20):
        if CARD_PNG.exists() and CARD_PNG.stat().st_size > 10000:
            break
        time.sleep(0.5)
    if CARD_PNG.exists():
        print("等级卡已生成:", CARD_PNG)
        try:
            cfg = core._load_config()
            cfg["cards_made"] = cfg.get("cards_made", 0) + 1
            core.save_json(core.CONFIG, cfg)
        except Exception:
            pass
        if "--open" in sys.argv:
            core.open_path(CARD_PNG)
    else:
        print("截图失败，HTML 在:", CARD_HTML)

if __name__ == "__main__":
    main()
