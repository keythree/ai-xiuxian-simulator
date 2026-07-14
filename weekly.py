# -*- coding: utf-8 -*-
"""AI修仙模拟器 修行周报卡
每周日 21:00 由计划任务自动生成（也可手动 python weekly.py --open）。
1080x1080 方卡：滚动统计近 7 天（对比再前 7 天）、七日修行柱、各道精进、新悟机缘。
黑箱纪律照旧：只有等级/灵气总量/机缘名，无判定数值。
"""
import json, sys, os, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta
import core
from card import BROWSERS

WEEK_HTML = core.OUT_DIR / "weekly.html"
WEEK_PNG = core.desktop_dir() / "AI修仙模拟器-周报.png"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ledger = core.load_ledger()
    with open(core.STATE, encoding="utf-8") as f:
        state = json.load(f)
    name = core.player_name()
    today = datetime.now(core.LOCAL_TZ).date()
    # 滚动窗口：近 7 天 vs 再往前 7 天
    w_start, w_end = today - timedelta(days=6), today
    lw_start, lw_end = today - timedelta(days=13), today - timedelta(days=7)

    day_xp, day_manual = {}, {}
    job_gain = {}
    for r in ledger:
        d = r.get("day", "")
        day_xp[d] = day_xp.get(d, 0) + r.get("total_xp", 0)
        if not r.get("auto"):
            ds = w_start.strftime("%Y-%m-%d") <= d <= w_end.strftime("%Y-%m-%d")
            if ds:
                day_manual[d] = day_manual.get(d, 0) + 1
                job_gain[r["job"]] = job_gain.get(r["job"], 0) + r.get("xp", 0)

    def span_sum(a, b):
        return sum(v for d, v in day_xp.items() if a.strftime("%Y-%m-%d") <= d <= b.strftime("%Y-%m-%d"))

    def span_tokens(a, b):
        lo, hi = a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        return sum(r.get("out_tokens", 0) for r in ledger if lo <= r.get("day", "") <= hi)

    this_week = span_sum(w_start, w_end)
    last_week = span_sum(lw_start, lw_end)
    tok_week = span_tokens(w_start, w_end)
    tok_last = span_tokens(lw_start, lw_end)
    if last_week > 0:
        pct = (this_week - last_week) / last_week * 100
        trend = f'<span style="color:{"#3fb950" if pct >= 0 else "#ff7b72"}">{"↑" if pct >= 0 else "↓"} {abs(pct):.0f}%</span> 较前七日'
    else:
        trend = "前七日无记录"

    # 法器消耗（output tokens 聚合 + 按模型 API 价折算美金）
    def fmt_tok(n):
        if n >= 1e8:
            return f"{n / 1e8:.1f} 亿"
        if n >= 1e4:
            return f"{n / 1e4:.0f} 万"
        return str(int(n))

    # USD / 1M output tokens（Claude 官方 API 价，2026-06 口径；codex:deepseek 按其公价）
    PRICES = {
        "claude-fable-5": 50.0, "claude-mythos": 50.0,
        "claude-opus-4-8": 25.0, "claude-opus-4-7": 25.0,
        "claude-opus-4-6": 25.0, "claude-opus-4-5": 25.0,
        "claude-opus-4-1": 75.0, "claude-opus-4": 75.0,
        "claude-sonnet-5": 15.0, "claude-sonnet-4": 15.0,
        "claude-haiku-4-5": 5.0, "claude-haiku": 5.0,
        "codex:deepseek": 1.1,
    }

    def price_of(model):
        for k, v in sorted(PRICES.items(), key=lambda x: -len(x[0])):
            if model.startswith(k):
                return v
        return 15.0  # 未知模型按 Sonnet 档保守估

    def span_usd(a, b):
        lo, hi = a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        usd = 0.0
        for r in ledger:
            if lo <= r.get("day", "") <= hi:
                for mdl, toks in (r.get("models") or {}).items():
                    usd += toks / 1e6 * price_of(mdl)
        return usd

    usd_week = span_usd(w_start, w_end)

    # 修为：七日前等级 → 当前等级；主修称号 = 最高职业
    lv_now = state.get("total_level", 1)
    lv_then = core.total_xp_to_level(max(0, state.get("total_xp", 0) - this_week))[0]
    lv_txt = f"Lv{lv_then} → {lv_now}" if lv_now > lv_then else f"Lv{lv_now}"
    lv_sub = f"修为{f' · 七日 +{lv_now - lv_then} 级' if lv_now > lv_then else ''}"
    main_job = max(state["levels"], key=lambda j: state["levels"][j])
    main_title = f'{core.realm_of(state["levels"][main_job])} · {core.title_of(main_job, state["levels"][main_job])}'

    # 七日柱（滚动窗口，标签用星期，最后一天标「今」）
    days_cn = "一二三四五六日"
    vals, labs = [], []
    for i in range(7):
        d = w_start + timedelta(days=i)
        vals.append(day_xp.get(d.strftime("%Y-%m-%d"), 0))
        labs.append("今" if d == today else days_cn[d.isoweekday() - 1])
    maxv = max((v for v in vals if v), default=1) or 1
    bars = ""
    for i, v in enumerate(vals):
        h = max(6, round(v / maxv * 150))
        bars += (f'<div class="wcol"><div class="wnum">{round(v) if v else ""}</div>'
                 f'<div class="wbar" style="height:{h}px{"" if v else ";background:#1c2230"}"></div>'
                 f'<div class="wlab">{labs[i]}</div></div>')

    # 各道精进 top3
    top = sorted(job_gain.items(), key=lambda x: -x[1])[:3]
    maxj = top[0][1] if top else 1
    jrows = "".join(
        f'<div class="jrow"><span class="jn">{j}</span>'
        f'<div class="jt"><div class="jf" style="width:{max(v / maxj * 100, 5):.0f}%"></div></div>'
        f'<span class="jl">{core.realm_of(state["levels"][j])}</span></div>'
        for j, v in top if v > 0) or '<div class="dim">本周无亲身历练</div>'

    # 本周新悟机缘
    try:
        with open(core.BADGE_LOG, encoding="utf-8") as f:
            blog = json.load(f)
    except Exception:
        blog = {}
    new_badges = [b for b in state["badges"]
                  if w_start.strftime("%Y-%m-%d") <= blog.get(b[0], "") <= w_end.strftime("%Y-%m-%d")]
    if new_badges:
        nb = "".join(
            f'<span class="nb {"xian" if b[1] == "仙缘" else ("hid" if b[1] == "隐藏" else "")}">'
            f'{b[3] if len(b) > 3 else ""} {b[0]}</span>'
            for b in new_badges[:4])
        if len(new_badges) > 4:
            nb += f'<span class="nb" style="opacity:.6">+{len(new_badges) - 4}</span>'
    else:
        nb = '<span class="dim">本周未悟新机缘，尚有未悟之缘</span>'

    n_tasks = sum(day_manual.values())
    page = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1080px;background:
  radial-gradient(ellipse 700px 420px at 50% -60px, rgba(255,209,102,.13), transparent 65%),
  #0b0e14;color:#e6e1cf;font-family:"Microsoft YaHei","PingFang SC",sans-serif;overflow:hidden;
  padding:56px 84px 40px;display:flex;flex-direction:column;position:relative}}
.brand{{text-align:center;font-size:22px;letter-spacing:12px;color:#8a8f98}}
.title{{text-align:center;margin-top:14px;font-size:40px;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC"}}
.mtitle{{text-align:center;margin-top:10px;font-size:24px;color:#ffd166;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";letter-spacing:4px}}
.range{{text-align:center;margin-top:8px;font-size:20px;color:#5c6773}}
.hero{{text-align:center;margin-top:30px}}
.hero .v{{font-size:96px;font-weight:800;color:#ffd166;line-height:1;text-shadow:0 0 50px rgba(255,209,102,.3)}}
.hero .l{{font-size:20px;color:#8a8f98;margin-top:8px;letter-spacing:4px}}
.hero .t{{font-size:22px;margin-top:10px;color:#8a8f98}}
.stats{{display:flex;justify-content:center;gap:16px;margin-top:26px}}
.stat{{background:rgba(23,27,34,.8);border:1px solid #1c2230;border-radius:12px;padding:14px 26px;text-align:center;min-width:200px}}
.stat .sv{{font-size:34px;font-weight:700;color:#59c2ff}}
.stat .sl{{font-size:15px;color:#5c6773;margin-top:4px}}
.wchart{{display:flex;justify-content:center;align-items:flex-end;gap:26px;margin-top:24px;height:170px}}
.wcol{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:6px}}
.wnum{{font-size:15px;color:#8a8f98}}
.wbar{{width:52px;background:linear-gradient(180deg,#ffd166,#8a6a1e);border-radius:6px 6px 0 0}}
.wlab{{font-size:17px;color:#5c6773}}
.sec{{margin-top:30px;font-size:18px;color:#8a8f98;letter-spacing:5px;text-align:center}}
.jwrap{{max-width:640px;margin:14px auto 0;width:100%}}
.jrow{{display:flex;align-items:center;gap:14px;margin-top:10px}}
.jn{{font-size:21px;width:56px}}
.jt{{flex:1;height:14px;background:#171c28;border-radius:7px;overflow:hidden}}
.jf{{height:100%;background:linear-gradient(90deg,#59c2ff,#ffd166);border-radius:7px}}
.jl{{font-size:16px;color:#59c2ff;width:110px;text-align:right}}
.nbwrap{{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:14px;max-width:760px;margin-left:auto;margin-right:auto}}
.nb{{font-size:20px;font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";color:#ffd166;border:1px solid #4a3f22;
  background:rgba(255,209,102,.07);border-radius:999px;padding:7px 20px}}
.nb.hid{{color:#c792ea;border-color:#4a3566;box-shadow:0 0 12px rgba(108,63,197,.3)}}
.nb.xian{{color:#ff8c5a;border-color:#7a4630;box-shadow:0 0 14px rgba(255,140,90,.35)}}
.dim{{color:#5c6773;font-size:18px;text-align:center}}
.foot{{margin-top:auto;display:flex;justify-content:space-between;align-items:baseline;color:#5c6773;font-size:18px}}
.foot .slogan{{font-family:KaiTi,"Kaiti SC","Microsoft YaHei","PingFang SC";font-size:21px;color:#8a8f98;letter-spacing:3px}}
.seal{{position:absolute;right:64px;bottom:120px;width:74px;height:74px;background:#9e2b25;border-radius:9px;
  transform:rotate(-7deg);display:flex;align-items:center;justify-content:center;opacity:.92;
  box-shadow:0 0 20px rgba(158,43,37,.4)}}
.seal span{{font-family:KaiTi;font-size:44px;color:#f3e2d0;font-weight:700}}
</style></head><body>
<div class="brand">AI修仙模拟器</div>
<div class="title">修行周报 · {name}</div>
<div class="mtitle">{main_title}</div>
<div class="range">{w_start.strftime("%m.%d")} 一 {w_end.strftime("%m.%d")} · 亲身历练 {n_tasks} 场 · 连修 {state.get("streak", 0)} 天</div>
<div class="hero"><div class="v">+{round(this_week)}</div><div class="l">近七日灵气</div><div class="t">{trend}</div></div>
<div class="stats">
  <div class="stat"><div class="sv">{lv_txt}</div><div class="sl">{lv_sub}</div></div>
  <div class="stat"><div class="sv">${usd_week:,.0f}</div><div class="sl">API 等值 · {fmt_tok(tok_week)} token</div></div>
</div>
<div class="wchart">{bars}</div>
<div class="sec">七日精力分布</div>
<div class="jwrap">{jrows}</div>
<div class="sec">七日新悟</div>
<div class="nbwrap">{nb}</div>
<div class="seal"><span>周</span></div>
<div class="foot"><span></span><span>{today.strftime("%Y-%m-%d")}</span></div>
</body></html>"""

    with open(WEEK_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        print("未找到浏览器，周报以网页版打开:", WEEK_HTML)
        core.open_path(WEEK_HTML)
        return
    if WEEK_PNG.exists():
        WEEK_PNG.unlink()
    subprocess.run([browser, "--headless", "--disable-gpu", "--hide-scrollbars",
                    f"--screenshot={WEEK_PNG}", "--window-size=1080,1080",
                    "--default-background-color=0b0e14", WEEK_HTML.as_uri()],
                   capture_output=True, timeout=60)
    for _ in range(20):
        if WEEK_PNG.exists() and WEEK_PNG.stat().st_size > 10000:
            break
        time.sleep(0.5)
    if WEEK_PNG.exists():
        print("周报已生成:", WEEK_PNG)
        if "--open" in sys.argv:
            core.open_path(WEEK_PNG)
    else:
        print("截图失败，HTML 在:", WEEK_HTML)


if __name__ == "__main__":
    main()
