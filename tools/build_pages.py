#!/usr/bin/env python3
"""Genera le pagine statiche per Google (una per campionato), sitemap.xml e robots.txt
partendo dai file in data/. Va rilanciato dopo ogni aggiornamento dei dati:

    python3 tools/build_pages.py

Le pagine sono HTML semplice e leggibile dai motori di ricerca; il pulsante
"Apri in Motortime" porta all'app (index.html?s=<campionato>).
"""
import html
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://motortimeitalia.it"
ROME = ZoneInfo("Europe/Rome")

# chiave dati -> (cartella, nome completo, nome breve, colore, parola per l'evento, è endurance)
SERIES = [
    ("f1", "formula-1", "Formula 1", "F1", "#e8002d", "GP"),
    ("f2", "formula-2", "Formula 2", "F2", "#2f74ff", "round"),
    ("f3", "formula-3", "Formula 3", "F3", "#8e5cf0", "round"),
    ("motogp", "motogp", "MotoGP", "MotoGP", "#e5541a", "GP"),
    ("moto2", "moto2", "Moto2", "Moto2", "#b8860b", "GP"),
    ("moto3", "moto3", "Moto3", "Moto3", "#d6336c", "GP"),
    ("wsbk", "superbike", "Superbike (WorldSBK)", "Superbike", "#c8102e", "round"),
    ("wssp", "supersport", "Supersport (WorldSSP)", "Supersport", "#0a84c6", "round"),
    ("wssp300", "world-sportbike", "World Sportbike (WorldSPB)", "World Sportbike", "#4c9a2a", "round"),
    ("wec", "wec", "WEC – Mondiale Endurance", "WEC", "#13a374", "gara"),
    ("elms", "elms", "European Le Mans Series (ELMS)", "ELMS", "#3b5bdb", "gara"),
    ("imsa", "imsa", "IMSA WeatherTech SportsCar Championship", "IMSA", "#b5179e", "gara"),
    ("alms", "asian-le-mans", "Asian Le Mans Series", "Asian Le Mans", "#0e7c9b", "gara"),
]
GROUPS = [("Formula", ["f1", "f2", "f3"]), ("Moto", ["motogp", "moto2", "moto3"]),
          ("Superbike", ["wsbk", "wssp", "wssp300"]), ("Endurance", ["wec", "elms", "imsa", "alms"])]

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def parse(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rome(ts):
    d = parse(ts)
    return d.astimezone(ROME) if d else None


def giorno(d):
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def data_breve(s):
    try:
        y, m, dd = (int(x) for x in str(s)[:10].split("-"))
        return f"{dd} {MESI_BREVI[m - 1]} {y}"
    except ValueError:
        return e(s)


def load(key):
    try:
        with open(os.path.join(ROOT, "data", key + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def logo_svg():
    try:
        src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        m = re.search(r'<svg class="mtlogo".*?</svg>', src, re.S)
        return m.group(0) if m else "MOTORTIME"
    except OSError:
        return "MOTORTIME"


CSS = """
:root{--bg:#0b0c0e;--card:#121418;--card2:#171a1f;--text:#f1efea;--muted:#a3a6ad;--seam:rgba(255,255,255,.08);--red:#e3121b;--f:"Archivo",system-ui,sans-serif;--m:"JetBrains Mono",ui-monospace,monospace}
@media (prefers-color-scheme:light){:root{--bg:#f1efea;--card:#fff;--card2:#f6f4f0;--text:#14161a;--muted:#5b5f67;--seam:rgba(10,12,16,.1)}.logo{--logo-w:#cfcac1}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:400 16px/1.55 var(--f);-webkit-text-size-adjust:100%}
.kerb{height:4px;background:repeating-linear-gradient(90deg,var(--c,var(--red)) 0 14px,#f1efea 14px 28px)}
header{border-bottom:1px solid var(--seam)}
.in{max-width:820px;margin:0 auto;padding:0 16px}
header .in{display:flex;align-items:center;justify-content:space-between;gap:12px;height:58px}
.logo{display:flex;color:var(--text)}.mtlogo{height:20px;width:auto;display:block}
.cta{background:var(--text);color:var(--bg);text-decoration:none;font-weight:700;font-size:14px;padding:9px 14px;border-radius:999px;white-space:nowrap}
.crumbs{font-size:13px;color:var(--muted);margin:18px 0 0}.crumbs a{color:var(--muted)}
h1{font-size:clamp(26px,6.6vw,40px);font-stretch:112%;font-weight:800;line-height:1.08;margin:8px 0 8px;letter-spacing:-.01em;text-wrap:balance}
.lead{color:var(--muted);margin:0 0 14px;text-wrap:pretty}
.tag{display:inline-block;background:var(--c);color:#fff;font-weight:800;font-size:12px;letter-spacing:.04em;text-transform:uppercase;padding:3px 8px;border-radius:3px}
section{background:var(--card);border:1px solid var(--seam);border-radius:8px;padding:4px 14px 12px;margin:16px 0;min-width:0}
h2{font-size:20px;font-stretch:108%;font-weight:800;margin:14px 0 4px;text-wrap:balance}
h3{font-size:15px;font-weight:700;margin:14px 0 4px}
.note{color:var(--muted);font-size:14px;margin:6px 0}
table{width:100%;border-collapse:collapse;font-size:15px}
th{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 6px;border-bottom:1px solid var(--seam)}
td{padding:9px 6px;border-bottom:1px solid var(--seam);vertical-align:top;overflow-wrap:anywhere}
.tw{overflow-x:auto;margin:0 -4px}
tr:last-child td{border-bottom:0}
td.n,th.n{text-align:right;white-space:nowrap}
.mono{font-family:var(--m);font-variant-numeric:tabular-nums}
.t{font-family:var(--m);font-weight:700;white-space:nowrap}
.key td:nth-child(2){font-weight:700}
small{color:var(--muted)}
.tv{color:var(--muted);font-size:13px;display:block}
.free{color:#8b7cf6;font-weight:600}
details summary{cursor:pointer;color:var(--red);font-weight:600;font-size:14px;padding:8px 0}
.news a{color:var(--text);font-weight:600;text-decoration:none}.news a:hover{text-decoration:underline}
.news li{margin:8px 0}.news ul{padding-left:18px;margin:6px 0}
.links{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.links a{background:var(--card2);border:1px solid var(--seam);color:var(--text);text-decoration:none;font-size:13px;font-weight:600;padding:6px 12px;border-radius:999px}
.links a.on{background:var(--text);color:var(--bg)}
.big{display:block;text-align:center;margin:18px 0;white-space:normal;line-height:1.35;padding:12px 16px}
footer{color:var(--muted);font-size:13px;text-align:center;padding:20px 16px 40px}footer a{color:var(--muted)}
"""

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&family=JetBrains+Mono:wght@500;700&display=swap">'
GC = '<script data-goatcounter="https://motortimeitalia.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'


def channels(s):
    out = e(s.get("live") or "")
    tv = s.get("tv8")
    if isinstance(tv, dict) and tv.get("time"):
        free = "TV8"
        when = rome(tv["time"])
        if tv.get("live"):
            out += f' · <span class="free">{free} in diretta</span>'
        elif when:
            out += f' · <span class="free">{free} differita {giorno(when).split(" ")[0]} {when:%H:%M}</span>'
    return out


def sessions_html(w, short, unit):
    ss = [s for s in (w.get("sessions") or []) if parse(s.get("start"))]
    if not w.get("gp"):
        return ""
    title = f"Orari {e(w['gp'])} in ora italiana e dove vederlo in TV"
    h = [f'<section id="orari"><h2>{title}</h2>']
    if w.get("circuit"):
        h.append(f'<p class="note">{e(w["circuit"])}</p>')
    if not ss:
        h.append('<p class="note">Gli orari ufficiali non sono ancora stati pubblicati: questa pagina si aggiorna da sola appena escono.</p></section>')
        return "".join(h)
    ss.sort(key=lambda s: parse(s["start"]))
    h.append('<div class="tw"><table><thead><tr><th>Ora</th><th>Sessione</th></tr></thead><tbody>')
    last_day = None
    for s in ss:
        d = rome(s["start"])
        day = giorno(d)
        if day != last_day:
            h.append(f'<tr><td colspan="2"><b>{e(day.capitalize())}</b></td></tr>')
            last_day = day
        tv = channels(s)
        cls = ' class="key"' if s.get("key") else ""
        h.append(f'<tr{cls}><td class="t">{d:%H:%M}</td><td>{e(s.get("name"))}'
                 f'{f"<span class=tv>{tv}</span>" if tv else ""}</td></tr>')
    h.append("</tbody></table></div>")
    if w.get("tv8note"):
        h.append(f'<p class="note">{e(w["tv8note"])}</p>')
    h.append("</section>")
    return "".join(h)


def rows_table(rows, kind, limit=None):
    rows = rows or []
    shown = rows[:limit] if limit else rows
    last = "Distacco" if kind == "race" else "Tempo"
    h = [f'<div class="tw"><table><thead><tr><th>Pos.</th><th>Pilota</th><th class="n">{last}</th></tr></thead><tbody>']
    for r in shown:
        val = r.get("gap") if kind == "race" else r.get("time")
        h.append(f'<tr><td class="mono">{e(r.get("pos"))}</td><td>{e(r.get("name"))}<small> · {e(r.get("team"))}</small></td>'
                 f'<td class="n mono">{e(val or "")}</td></tr>')
    h.append("</tbody></table></div>")
    out = "".join(h)
    if limit and len(rows) > limit:
        rest = rows_table(rows[limit:], kind)
        out += f'<details><summary>Mostra tutti i {len(rows)} classificati</summary>{rest}</details>'
    return out


def results_html(r):
    tabs = [t for t in (r.get("tabs") or []) if t.get("rows")]
    if not r.get("gp") or not tabs:
        return ""
    h = [f'<section id="risultati"><h2>Risultati {e(r["gp"])}</h2>']
    if r.get("summary"):
        h.append(f'<p class="lead">{e(r["summary"])}</p>')
    races = [t for t in tabs if t.get("kind") == "race"] or tabs
    for t in races:
        label = f'{t.get("cls") + " · " if t.get("cls") else ""}{t.get("label")}'
        h.append(f"<h3>{e(label)}</h3>")
        h.append(rows_table(t["rows"], t.get("kind", "race"), limit=10))
    quali = [t for t in tabs if t.get("kind") == "quali"]
    for t in quali:
        label = f'{t.get("cls") + " · " if t.get("cls") else ""}{t.get("label")}'
        h.append(f'<details><summary>{e(label)}</summary>{rows_table(t["rows"], "quali")}</details>')
    h.append("</section>")
    return "".join(h)


def standing_table(items, who, with_team=True):
    h = [f'<div class="tw"><table><thead><tr><th>Pos.</th><th>{who}</th><th class="n">Punti</th></tr></thead><tbody>']
    for x in items:
        name = e(x.get("name") or x.get("team"))
        sub = ""
        if with_team and x.get("name") and x.get("team"):
            sub = f"<small> · {e(x['team'])}</small>"
        elif x.get("drivers") and not x.get("name"):
            dr = x["drivers"] if isinstance(x["drivers"], str) else ", ".join(map(str, x["drivers"]))
            sub = f"<small> · {e(dr)}</small>"
        champ = " 🏆" if x.get("champion") else ""
        h.append(f'<tr><td class="mono">{e(x.get("pos"))}</td><td>{name}{champ}{sub}</td><td class="n mono">{e(x.get("points"))}</td></tr>')
    h.append("</tbody></table></div>")
    return "".join(h)


def standings_html(st, season, short):
    if not st:
        return ""
    after = f' <span class="note">({e(st["after"])})</span>' if st.get("after") else ""
    blocks = []
    if st.get("classes"):
        for c in st["classes"]:
            if c.get("drivers"):
                blocks.append((f"Classifica piloti {c['cls']}", c["drivers"], "Pilota", True))
            if c.get("constructors"):
                blocks.append((f"Classifica team {c['cls']}", c["constructors"], "Team", False))
    else:
        if st.get("drivers"):
            blocks.append(("Classifica piloti", st["drivers"], "Pilota", True))
        if st.get("constructors"):
            blocks.append(("Classifica team e costruttori", st["constructors"], "Team", False))
    if not blocks:
        return ""
    h = [f'<section id="classifica"><h2>Classifica {e(short)} {e(season)}</h2><p class="note">{after.strip()}</p>' if after else f'<section id="classifica"><h2>Classifica {e(short)} {e(season)}</h2>']
    for i, (title, items, who, team) in enumerate(blocks):
        table = standing_table(items, who, team)
        if i == 0:
            h.append(f"<h3>{e(title)}</h3>{table}")
        else:
            h.append(f"<details><summary>{e(title)}</summary>{table}</details>")
    h.append("</section>")
    return "".join(h)


def calendar_html(cal, short):
    rounds = cal.get("rounds") or []
    if not rounds:
        return ""
    h = [f'<section id="calendario"><h2>Calendario {e(short)} {e(cal.get("season", ""))}</h2>',
         '<div class="tw"><table><thead><tr><th>Data</th><th>Evento</th><th>Vincitore</th></tr></thead><tbody>']
    for r in rounds:
        win = r.get("winner") or ""
        if r.get("status"):
            win = r["status"] if not win else f'{win} ({r["status"]})'
        h.append(f'<tr><td class="mono" style="white-space:nowrap">{data_breve(r.get("date"))}</td>'
                 f'<td>{e(r.get("name"))}<small> · {e(r.get("circuit"))}</small></td><td>{e(win)}</td></tr>')
    h.append("</tbody></table></div></section>")
    return "".join(h)


def news_html(news):
    items = sorted([n for n in (news or []) if n.get("title")], key=lambda n: n.get("published") or "", reverse=True)[:6]
    if not items:
        return ""
    h = ['<section id="notizie" class="news"><h2>Ultime notizie</h2><ul>']
    for n in items:
        d = rome(n.get("published"))
        when = f"{d.day} {MESI_BREVI[d.month - 1]}" if d else ""
        link = f'<a href="{e(n["url"])}" rel="noopener" target="_blank">{e(n["title"])}</a>' if n.get("url") else e(n["title"])
        h.append(f'<li>{link}<br><small>{e(when)} · {e(n.get("source"))}</small><br><span class="note">{e(n.get("summary"))}</span></li>')
    h.append("</ul></section>")
    return "".join(h)


def stand_season(d, season):
    """La classifica può riferirsi alla stagione appena finita mentre il calendario è già quello nuovo."""
    st = d.get("standings") or {}
    u = parse(st.get("updated"))
    m = re.match(r"(\d{4})", str(season))
    if u and m and int(m.group(1)) > u.year:
        return str(u.year)
    return season


def page(key, slug, full, short, color, unit, logo):
    d = load(key)
    info = d.get("info") or {}
    w = d.get("weekend") or {}
    cal = d.get("calendar") or {}
    season = cal.get("season") or ""
    nxt = info.get("nextGp") or {}
    event = w.get("gp") or nxt.get("name") or ""
    upd = parse(info.get("updated")) or datetime.now(timezone.utc)

    if event:
        title = f"{short} {season}: orari TV {event}, risultati e classifica | Motortime"
        desc = (f"Orari in ora italiana di {event} con canali TV (Sky, NOW, TV8), risultati dell'ultima gara, "
                f"classifica e calendario {short} {season}. Aggiornato più volte al giorno.")
    else:
        title = f"{short} {season}: orari TV, risultati e classifica | Motortime"
        desc = f"Orari in ora italiana, canali TV, risultati, classifica e calendario {short} {season}. Aggiornato più volte al giorno."
    url = f"{SITE}/{slug}/"

    lead = ""
    if nxt.get("name") and parse(nxt.get("date")):
        nd = rome(nxt["date"])
        when = giorno(nd) + ("" if nxt.get("dateOnly") else f" alle {nd:%H:%M}")
        lead = f"Prossimo appuntamento: <b>{e(nxt['name'])}</b>{' · ' + e(nxt.get('circuit')) if nxt.get('circuit') else ''}, {e(nxt.get('label') or 'gara').lower()} {e(when)}."

    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Motortime", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": short, "item": url}]}]
    if nxt.get("name") and parse(nxt.get("date")):
        ev = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{short} – {nxt['name']}",
              "startDate": parse(nxt["date"]).isoformat(), "eventStatus": "https://schema.org/EventScheduled",
              "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "sport": "Motorsport",
              "url": url}
        if nxt.get("circuit"):
            ev["location"] = {"@type": "Place", "name": nxt["circuit"]}
        ld.append(ev)

    others = []
    for gname, keys in GROUPS:
        for k in keys:
            s = next(x for x in SERIES if x[0] == k)
            on = ' class="on"' if k == key else ""
            others.append(f'<a{on} href="../{s[1]}/">{e(s[3])}</a>')

    body = "".join([
        sessions_html(w, short, unit),
        results_html(d.get("results") or {}),
        standings_html(d.get("standings") or {}, stand_season(d, season), short),
        calendar_html(cal, short),
        news_html(d.get("news")),
    ])
    app = f"../?s={key}"
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Motortime">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/icon-512.png"><meta property="og:locale" content="it_IT">
<meta name="theme-color" content="#0a0b0d">
<link rel="icon" href="../favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="../icon-180.png">
{FONTS}
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
{GC}
</head>
<body style="--c:{color}">
<div class="kerb"></div>
<header><div class="in"><a class="logo" href="../" aria-label="Motortime">{logo}</a><a class="cta" href="{app}">Apri in Motortime</a></div></header>
<main class="in">
<p class="crumbs"><a href="../">Motortime</a> › {e(short)}</p>
<span class="tag">{e(short)}</span>
<h1>{e(short)} {e(season)}: orari TV, risultati e classifica</h1>
<p class="lead">{lead} Orari in ora italiana, aggiornati il {upd.astimezone(ROME).day} {MESI[upd.astimezone(ROME).month - 1]} alle {upd.astimezone(ROME):%H:%M}.</p>
{body}
<h2 style="margin-top:22px">Altri campionati</h2>
<nav class="links" aria-label="Campionati">{''.join(others)}</nav>
<a class="cta big" href="{app}">Segui {e(short)} su Motortime: conto alla rovescia, meteo e preferiti</a>
</main>
<footer>Motortime · orari italiani, TV, risultati e notizie del motorsport<br>
<a href="../">motortimeitalia.it</a> · <a href="../info.html#note-legali">Note legali</a> · <a href="../info.html#privacy">Privacy e cookie</a> · <a href="../info.html#contatti">Contatti</a><br>
Sito indipendente, non affiliato ai campionati, alle federazioni o ai team citati.</footer>
</body>
</html>
""", upd


def main():
    logo = logo_svg()
    urls = []
    newest = None
    for key, slug, full, short, color, unit in SERIES:
        out, upd = page(key, slug, full, short, color, unit, logo)
        os.makedirs(os.path.join(ROOT, slug), exist_ok=True)
        with open(os.path.join(ROOT, slug, "index.html"), "w", encoding="utf-8") as f:
            f.write(out)
        urls.append((f"{SITE}/{slug}/", upd))
        newest = upd if newest is None or upd > newest else newest
    urls.insert(0, (SITE + "/", newest))
    urls.append((SITE + "/info.html", None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, d in urls:
        lm = f"<lastmod>{d.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}</lastmod>" if d else ""
        sm.append(f"<url><loc>{u}</loc>{lm}</url>")
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")
    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    print(f"Pagine generate: {len(SERIES)} + sitemap.xml + robots.txt")


if __name__ == "__main__":
    main()
