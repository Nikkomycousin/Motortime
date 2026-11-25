#!/usr/bin/env python3
"""Genera le schede grafiche per i social (Instagram) dai file in data/.

    python3 tools/social_cards.py OUTDIR [--fonts DIR]

Scrive in OUTDIR una pagina HTML per ogni scheda (1080x1350 post, 1080x1920 storia);
uno script separato le fotografa in PNG. Tipi di scheda:
  weekend-<campionato>   orari del weekend in ora italiana con i canali TV
  results-<campionato>   podio dell'ultima gara + prime posizioni della classifica
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROME = ZoneInfo("Europe/Rome")
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
SERIES = {
    "f1": ("Formula 1", "F1", "#e8002d"), "f2": ("Formula 2", "F2", "#2f74ff"), "f3": ("Formula 3", "F3", "#8e5cf0"),
    "motogp": ("MotoGP", "MotoGP", "#e5541a"), "moto2": ("Moto2", "Moto2", "#c9a227"), "moto3": ("Moto3", "Moto3", "#d6336c"),
    "wsbk": ("Superbike", "WorldSBK", "#c8102e"), "wssp": ("Supersport", "WorldSSP", "#0a84c6"),
    "wssp300": ("World Sportbike", "WorldSPB", "#4c9a2a"), "wec": ("WEC", "WEC", "#13a374"),
    "elms": ("ELMS", "ELMS", "#3b5bdb"), "imsa": ("IMSA", "IMSA", "#b5179e"), "alms": ("Asian Le Mans", "ALMS", "#0e7c9b"),
}
e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def parse(ts):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


COUNTRY = [  # parola nel nome del circuito o del GP -> codice paese (bandiera)
    (r"qatar|lusail|losail", "qa"), (r"valencia|cheste|ricardo tormo|jerez|arag|motorland|catalunya|barcel|montmel|madrid", "es"),
    (r"portim|algarve|portogallo|estoril", "pt"), (r"abu dhabi|yas marina", "ae"), (r"bahrain|sakhir", "bh"), (r"jeddah|arabia", "sa"),
    (r"las vegas|americas|austin|cota|miami|daytona|sebring|road atlanta|petit le mans|indianapolis|watkins|laguna|long beach|road america|elkhart|detroit|virginia|lime rock", "us"),
    (r"monza|imola|mugello|misano|cremona|vallelunga", "it"), (r"phillip island|albert park|melbourne|australia", "au"),
    (r"silverstone|donington|gran bretagna", "gb"), (r"\bspa\b|francorchamps|belgio", "be"), (r"zandvoort|assen|olanda", "nl"),
    (r"le mans|sarthe|paul ricard|castellet|magny|francia", "fr"), (r"sachsenring|hockenheim|n.rburgring|germania", "de"),
    (r"brno|\bmost\b|repubblica ceca", "cz"), (r"balaton|hungaroring|ungheria", "hu"), (r"red bull ring|spielberg|austria", "at"),
    (r"monaco|monte.?carlo", "mc"), (r"montr.al|mosport|canadian tire|canada", "ca"), (r"messico|mexico|hermanos", "mx"),
    (r"interlagos|s.o paulo|goi.nia|brasile", "br"), (r"baku|azerbaigian", "az"), (r"singapore|marina bay", "sg"),
    (r"suzuka|motegi|fuji|giappone", "jp"), (r"shanghai|cina", "cn"), (r"sepang|malesia", "my"), (r"mandalika|indonesia", "id"),
    (r"buriram|chang|thailandia", "th"), (r"termas|rio hondo|argentina", "ar"),
]


def flag(text, flags_dir):
    t = (text or "").lower()
    for rx, cc in COUNTRY:
        if re.search(rx, t):
            path = os.path.join(flags_dir or "", cc + ".svg")
            if flags_dir and os.path.exists(path):
                import base64
                b = base64.b64encode(open(path, "rb").read()).decode()
                return f'<img class="flag" src="data:image/svg+xml;base64,{b}" alt="">'
            return ""
    return ""


def coords(w):
    if isinstance(w.get("lat"), (int, float)) and isinstance(w.get("lon"), (int, float)):
        return w["lat"], w["lon"]
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    t = f"{w.get('circuit', '')} {w.get('gp', '')}".lower()
    for rx, la, lo in re.findall(r"\[/(.*?)/,(-?[\d.]+),(-?[\d.]+)\]", src):
        try:
            if re.search(rx, t):
                return float(la), float(lo)
        except re.error:
            continue
    return None


_WX = {}
FLAGS = None


def weather(w, iso):
    """Previsione oraria Open-Meteo per l'inizio della sessione: (codice, temperatura, prob. pioggia) o None."""
    if os.environ.get("MT_WX_DEMO"):  # solo per le anteprime grafiche: valori di esempio
        demo = [(1, 18, 5), (2, 19, 10), (61, 15, 70), (0, 20, 0)]
        return demo[sum(map(ord, str(iso))) % len(demo)]
    c = coords(w)
    d = parse(iso)
    if not c or not d or d - datetime.now(timezone.utc) > timedelta(days=15):
        return None
    key = f"{c[0]:.2f},{c[1]:.2f}"
    if key not in _WX:
        try:
            import urllib.request
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={c[0]}&longitude={c[1]}"
                   "&hourly=temperature_2m,precipitation_probability,weather_code&timezone=UTC&forecast_days=16")
            _WX[key] = json.loads(urllib.request.urlopen(url, timeout=15).read())["hourly"]
        except Exception:
            _WX[key] = None
    h = _WX[key]
    if not h:
        return None
    stamp = d.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
    if stamp not in h["time"]:
        return None
    i = h["time"].index(stamp)
    return h["weather_code"][i], round(h["temperature_2m"][i]), h["precipitation_probability"][i]


def wx_icon(code):
    sun = '<circle cx="12" cy="12" r="4.5" fill="#f5c542"/><g stroke="#f5c542" stroke-width="2" stroke-linecap="round"><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></g>'
    cloud = '<path d="M7 18h10a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 18z" fill="#c9ccd3"/>'
    rain = cloud + '<g stroke="#4ea1ff" stroke-width="2" stroke-linecap="round"><path d="M9 20.5l-1 2M13 20.5l-1 2M17 20.5l-1 2"/></g>'
    if code == 0:
        g = sun
    elif code <= 2:
        g = '<g transform="translate(-3 -3) scale(.8)">' + sun + "</g>" + cloud
    elif code <= 48:
        g = cloud
    else:
        g = rain
    return f'<svg class="wxi" viewBox="0 0 24 24">{g}</svg>'


def load(key):
    try:
        return json.load(open(os.path.join(ROOT, "data", key + ".json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def logo():
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    m = re.search(r'<svg class="mtlogo".*?</svg>', src, re.S)
    return m.group(0) if m else "MOTORTIME"


def css(fonts):
    return f"""
@font-face{{font-family:Archivo;src:url({fonts}/archivo-latin-wdth-normal.woff2) format("woff2");font-weight:100 900;font-stretch:62% 125%}}
@font-face{{font-family:JBM;src:url({fonts}/jetbrains-mono-latin-500-normal.woff2) format("woff2");font-weight:500}}
@font-face{{font-family:JBM;src:url({fonts}/jetbrains-mono-latin-700-normal.woff2) format("woff2");font-weight:700}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:1080px;height:var(--h);background:#0b0c0e}}
body{{font-family:Archivo,sans-serif;color:#f1efea;position:relative;overflow:hidden}}
.card{{position:absolute;inset:0;display:flex;flex-direction:column;padding:0 72px 64px}}
.kerb{{position:absolute;left:0;right:0;top:0;height:18px;background:repeating-linear-gradient(90deg,var(--c) 0 44px,#f1efea 44px 88px)}}
.glow{{position:absolute;right:-260px;top:-260px;width:820px;height:820px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--c) 30%,transparent),transparent 65%)}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-top:70px;position:relative}}
.mtlogo{{height:46px;width:auto;color:#f1efea}}
.tag{{background:var(--c);color:#fff;font-weight:800;font-stretch:112%;font-size:30px;letter-spacing:.06em;text-transform:uppercase;padding:10px 20px;border-radius:6px}}
.kicker{{margin-top:52px;font-size:30px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#a3a6ad;position:relative}}
.kicker b{{color:var(--c);font-weight:800}}
h1{{font-size:88px;line-height:.92;font-weight:900;font-stretch:118%;text-transform:uppercase;letter-spacing:-.01em;margin-top:14px;position:relative}}
.sub{{font-size:32px;color:#a3a6ad;margin-top:16px;position:relative}}
.days{{margin-top:44px;display:flex;flex-direction:column;gap:30px;flex:1;position:relative}}
.day h3{{font-size:28px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#a3a6ad;padding-bottom:10px;border-bottom:2px solid rgba(255,255,255,.1);margin-bottom:6px}}
.row{{display:flex;align-items:center;gap:28px;padding:12px 0}}
.t{{font-family:JBM;font-weight:700;font-size:46px;width:158px;letter-spacing:-.02em}}
.n{{font-size:38px;font-weight:600;flex:1;line-height:1.1}}
.row.key .n{{font-weight:800}}
.row.key .t{{color:var(--c)}}
.row:not(.key){{opacity:.72}}
.row:not(.key) .t{{font-size:40px}}
.row:not(.key) .n{{font-size:33px}}
.ch{{display:flex;gap:10px;flex-direction:column;align-items:flex-end;max-width:440px}}
.chip{{font-size:23px;font-weight:700;padding:7px 14px;border-radius:999px;background:#1b1e24;color:#d8d6d0;white-space:nowrap}}
.chip.free{{background:#7c6cf0;color:#fff}}
.note{{font-size:27px;color:#a3a6ad;line-height:1.35;margin-top:18px;position:relative}}
.foot{{display:flex;justify-content:space-between;align-items:flex-end;margin-top:28px;padding-top:26px;border-top:2px solid rgba(255,255,255,.1);position:relative}}
.foot .site{{font-size:34px;font-weight:800;font-stretch:110%}}
.foot .tz{{font-size:26px;color:#a3a6ad;text-align:right;line-height:1.35}}
/* risultati */
.podium{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:22px;margin-top:40px;align-items:end;position:relative}}
.p{{background:#14161b;border-radius:14px;padding:28px 24px;display:flex;flex-direction:column;gap:10px;border-top:8px solid #3a3d44}}
.p.p1{{border-top-color:var(--c);padding-top:36px;background:#181b21}}
.p .pos{{font-family:JBM;font-weight:700;font-size:64px;line-height:1}}
.p.p1 .pos{{font-size:80px;color:var(--c)}}
.p .nm{{font-size:36px;font-weight:800;line-height:1.05;font-stretch:96%}}
.p.p1 .nm{{font-size:42px}}
.p .tm{{font-size:25px;color:#a3a6ad;line-height:1.2}}
.sec{{margin-top:36px;font-size:28px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#a3a6ad;position:relative}}
.list{{margin-top:12px;display:flex;flex-direction:column;position:relative}}
.li{{display:flex;align-items:center;gap:24px;padding:10px 0;border-bottom:2px solid rgba(255,255,255,.07);font-size:34px}}
.li .ps{{font-family:JBM;font-weight:700;width:60px;color:#a3a6ad}}
.li .nm{{flex:1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
.li .nm small{{font-weight:500;color:#a3a6ad;font-size:26px;margin-left:12px}}
.li .pt{{font-family:JBM;font-weight:700}}
.li.champ .nm::after{{content:"CAMPIONE";font-size:20px;letter-spacing:.1em;background:var(--c);color:#fff;padding:4px 10px;border-radius:4px;margin-left:14px;vertical-align:5px}}
.mini{{display:flex;gap:16px;margin-top:22px;flex-wrap:wrap;position:relative}}
.mini div{{background:#14161b;border-radius:10px;padding:14px 18px;font-size:26px;color:#d8d6d0}}
.mini b{{color:#f1efea}}
.flag{{height:44px;width:auto;border-radius:6px;vertical-align:-8px;margin-right:16px;box-shadow:0 0 0 2px rgba(255,255,255,.12)}}
.wx{{display:flex;align-items:center;gap:8px;font-size:25px;font-weight:600;color:#c9ccd3;margin-top:6px}}.wx .wxi{{width:34px;height:34px}}.wx small{{color:#7f9fd6;font-size:23px;font-weight:600}}
.n{{display:flex;flex-direction:column}}
.big .days{{gap:46px;margin-top:60px}}.big .row{{padding:22px 0}}.big .t{{font-size:68px;width:220px}}.big .n{{font-size:54px}}.big .chip{{font-size:27px}}.big .day h3{{font-size:32px}}
.story h1{{font-size:112px}}.story .kicker{{margin-top:90px}}.story .days{{gap:52px;margin-top:70px}}.story .row{{padding:20px 0}}.story .t{{font-size:58px;width:190px}}.story .n{{font-size:46px}}.story .row:not(.key) .t{{font-size:50px}}.story .row:not(.key) .n{{font-size:40px}}.story .chip{{font-size:27px}}.story .day h3{{font-size:32px}}
"""


def chips(s):
    out = []
    live = s.get("live") or ""
    for part in re.split(r"\s*·\s*", live):
        p = re.sub(r"^(Diretta|In diretta)\s+", "", part).strip()
        if not p:
            continue
        if "TV8" in p:
            continue
        out.append(p)
    out = [f'<span class="chip">{e(" · ".join(out))}</span>'] if out else []
    t = s.get("tv8")
    if isinstance(t, dict) and t.get("time"):
        d = parse(t["time"])
        out.append(f'<span class="chip free">TV8 {"diretta" if t.get("live") else ("differita " + d.astimezone(ROME).strftime("%H:%M") if d else "differita")}</span>')
    elif "TV8" in live:
        out.append('<span class="chip free">TV8</span>')
    return "".join(out)


def page(key, h, body, fonts):
    name, tag, color = SERIES[key]
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><style>{css(fonts)}</style></head>
<body class="{"story" if h > 1500 else ""}" style="--c:{color};--h:{h}px"><div class="kerb"></div><div class="glow"></div><div class="card">
<div class="top">{logo()}<span class="tag">{e(tag)}</span></div>{body}</div></body></html>"""


def wx_html(w, s):
    if not s.get("key"):
        return ""
    x = weather(w, s.get("start"))
    if not x:
        return ""
    code, t, p = x
    return f'<span class="wx">{wx_icon(code)}{t}°C' + (f' <small>· pioggia {p}%</small>' if p else "") + "</span>"


def weekend_card(key, fonts, story=False):
    d = load(key)
    w = d.get("weekend") or {}
    ss = sorted([s for s in (w.get("sessions") or []) if parse(s.get("start"))], key=lambda s: parse(s["start"]))
    if not w.get("gp") or not ss:
        return None
    if not story:  # nel post solo le sessioni principali se sono troppe
        if len(ss) > 5:
            ss = [s for s in ss if s.get("key")] or ss[:5]
    days, cur = [], None
    for s in ss:
        dt = parse(s["start"]).astimezone(ROME)
        if dt.date() != cur:
            cur = dt.date()
            days.append([f"{GIORNI[dt.weekday()]} {dt.day} {MESI[dt.month - 1]}", []])
        days[-1][1].append((dt, s))
    blocks = "".join(
        f'<div class="day"><h3>{e(lbl)}</h3>' + "".join(
            f'<div class="row{" key" if s.get("key") else ""}"><span class="t">{dt:%H:%M}</span>'
            f'<span class="n">{e(s["name"])}{wx_html(w, s)}</span><span class="ch">{chips(s)}</span></div>' for dt, s in rows) + "</div>"
        for lbl, rows in days)
    gp = re.sub(r"^Round \d+\s*·\s*", "", w["gp"])
    big = (not story) and len(ss) <= 4
    body = (('<div class="big" style="display:contents">' if big else "") + f'<div class="kicker"><b>Orari TV</b> · {e(SERIES[key][0])}</div><h1>{e(gp)}</h1>'
            f'<div class="sub">{flag(w.get("circuit", "") + " " + w["gp"], FLAGS)}{e(w.get("circuit"))}</div><div class="days">{blocks}</div>'
            f'<div class="foot"><span class="site">motortimeitalia.it</span><span class="tz">Orari in ora italiana<br>Promemoria su Telegram: @motortimeitalia</span></div>' + ("</div>" if big else ""))
    return page(key, 1920 if story else 1350, body, fonts)


def results_card(key, fonts):
    d = load(key)
    r = d.get("results") or {}
    tabs = [t for t in (r.get("tabs") or []) if t.get("kind") == "race" and t.get("rows")]
    if not r.get("gp") or not tabs:
        return None
    main = next((t for t in tabs if t.get("label", "").startswith(("Gara", "Feature"))), tabs[0])
    pod = [x for x in main["rows"] if str(x.get("pos")) in ("1", "2", "3")][:3]
    if len(pod) < 3:
        return None
    order = [pod[1], pod[0], pod[2]]
    cls = ["p2", "p1", "p3"]
    endu = key in ("wec", "elms", "imsa", "alms")

    def who(x):  # endurance: in grande la vettura, sotto l'equipaggio
        if endu:
            car = re.sub(r"\s*\(.*\)\s*$", "", x.get("team") or "")
            return car or x.get("name"), x.get("name")
        return x.get("name"), x.get("team")
    podium = "".join(f'<div class="p {c}"><span class="pos">{x["pos"]}</span><span class="nm">{e(who(x)[0])}</span>'
                     f'<span class="tm">{e(who(x)[1])}</span></div>' for x, c in zip(order, cls))
    extra = ""
    others = [t for t in tabs if t is not main][:1 if endu else 2]
    if others:
        extra = '<div class="mini">' + "".join(
            f'<div>{e((t.get("cls") + " · ") if t.get("cls") else "")}{e(t["label"])}: <b>{e(next((x["name"] for x in t["rows"] if str(x.get("pos")) == "1"), "—"))}</b></div>'
            for t in others) + "</div>"
    st = d.get("standings") or {}
    drivers = st.get("drivers") or ((st.get("classes") or [{}])[0].get("drivers") or [])
    stand = ""
    if drivers:
        cl = (st.get("classes") or [{}])[0].get("cls")
        stand = f'<div class="sec">Classifica piloti{" " + e(cl) if cl else ""}</div><div class="list">' + "".join(
            f'<div class="li{" champ" if x.get("champion") and i == 0 else ""}"><span class="ps">{e(x.get("pos"))}</span>'
            f'<span class="nm">{e(x.get("name"))}<small>{e(x.get("team"))}</small></span><span class="pt">{e(x.get("points"))}</span></div>'
            for i, x in enumerate(drivers[:3 if endu else 5])) + "</div>"
    label = main.get("label", "Gara") + (f' · {main["cls"]}' if main.get("cls") else "")
    fl = flag(r["gp"] + " " + " ".join(x.get("circuit", "") for x in (d.get("calendar") or {}).get("rounds", []) if x.get("name") == r["gp"]), FLAGS)
    body = (f'<div class="kicker">{fl}<b>Risultati</b> · {e(label)}</div><h1>{e(r["gp"])}</h1>'
            f'<div class="podium">{podium}</div>{extra}{stand}<div style="flex:1"></div>'
            f'<div class="foot"><span class="site">motortimeitalia.it</span><span class="tz">Ordine d\'arrivo completo<br>sul sito e su Telegram @motortimeitalia</span></div>')
    return page(key, 1350, body, fonts)


def main():
    out = sys.argv[1]
    global FLAGS
    fonts = sys.argv[sys.argv.index("--fonts") + 1] if "--fonts" in sys.argv else "fonts"
    FLAGS = sys.argv[sys.argv.index("--flags") + 1] if "--flags" in sys.argv else os.path.join(ROOT, "tools", "flags")
    os.makedirs(out, exist_ok=True)
    made = []
    for key in SERIES:
        for name, fn in ((f"weekend-{key}", lambda k: weekend_card(k, fonts)),
                         (f"story-{key}", lambda k: weekend_card(k, fonts, story=True)),
                         (f"results-{key}", lambda k: results_card(k, fonts))):
            h = fn(key)
            if h:
                open(os.path.join(out, name + ".html"), "w", encoding="utf-8").write(h)
                made.append(name)
    print("\n".join(made))


if __name__ == "__main__":
    main()
