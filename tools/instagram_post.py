#!/usr/bin/env python3
"""Pubblicazione automatica su Instagram (@motortime_italia) tramite le API ufficiali di Meta.

Due fasi, eseguite dal workflow .github/workflows/instagram.yml:

  python3 tools/instagram_post.py plan  --fonts URL --flags DIR
      decide cosa pubblicare (orari del weekend, risultati), scrive le schede HTML in
      build/social/ e l'elenco in build/social/pending.json. Stampa "work=1" se c'è lavoro.

  python3 tools/instagram_post.py publish --base URL
      pubblica le immagini (già trasformate in PNG e caricate in social/) e aggiorna
      tools/instagram_state.json, così niente viene pubblicato due volte.

Segreto richiesto: META_PAGE_TOKEN (token della Pagina Facebook collegata all'account Instagram).
"""
import json
import re
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import social_cards as sc  # noqa: E402

ROOT = sc.ROOT
IG_USER = os.environ.get("IG_USER_ID", "17841480897571197")
FB_PAGE = os.environ.get("FB_PAGE_ID", "1470016799533338")
FB_CATCHUP = "--fb-catchup" in sys.argv  # recupero: solo Facebook per i post già usciti su Instagram
SLUG = {"f1": "formula-1", "motogp": "motogp", "wsbk": "superbike", "wec": "wec"}
GRAPH = "https://graph.facebook.com/v21.0"
STATE = os.path.join(ROOT, "tools", "instagram_state.json")
BUILD = os.path.join(ROOT, "build", "social")
OUT = os.path.join(ROOT, "social")

# Campionati pubblicati su Instagram e Facebook (solo questi, per non intasare il profilo)
MAIN = ["f1", "motogp", "wec"]
TAGS = {
    "f1": "#F1 #Formula1 #FormulaUno #F1Italia #Ferrari #SkySportF1 #TV8",
    "motogp": "#MotoGP #Moto2 #Moto3 #MotoGPItalia #Ducati #Aprilia #SkySportMotoGP #TV8",
    "wsbk": "#WorldSBK #Superbike #SBK #Ducati #Supersport",
    "wec": "#WEC #FIAWEC #Endurance #Hypercar #FerrariHypercar #LeMans",
}
NAMES = {"f1": "Formula 1", "motogp": "MotoGP", "wsbk": "Superbike", "wec": "WEC"}


def now_utc():
    if "--now" in sys.argv:
        return sc.parse(sys.argv[sys.argv.index("--now") + 1])
    return datetime.now(timezone.utc)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(state, now):
    cutoff = now - timedelta(days=60)
    state = {k: v for k, v in state.items() if (sc.parse(v) or now) > cutoff}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def weekend_items(now, state):
    items = []
    for key in MAIN:
        w = sc.load(key).get("weekend") or {}
        ss = sorted([s for s in (w.get("sessions") or []) if sc.parse(s.get("start"))], key=lambda s: sc.parse(s["start"]))
        if not w.get("gp") or not ss:
            continue
        first, last = sc.parse(ss[0]["start"]), sc.parse(ss[-1]["start"])
        sid = f"weekend:{key}:{w['gp']}:{first:%Y%m%d}"
        # esce a metà settimana: dal mercoledì alle 10 (ora italiana) della settimana della gara
        fr = first.astimezone(sc.ROME)
        wed = (fr - timedelta(days=(fr.weekday() - 2) % 7)).replace(hour=10, minute=0, second=0, microsecond=0)
        start = max(wed, first - timedelta(days=4))
        if not (start <= now < first) or last < now:
            continue
        if sid in state and (not FB_CATCHUP or "fb:" + sid in state):
            continue
        key_s = [s for s in ss if s.get("key")]
        lines = []
        for s in key_s:
            d = sc.parse(s["start"]).astimezone(sc.ROME)
            lines.append(f"• {s['name']}: {sc.GIORNI[d.weekday()].lower()} alle {d:%H:%M}")
        cap = (f"🏁 {NAMES[key]} · {w['gp']}: gli orari del weekend in ora italiana e dove vederlo in TV\n\n"
               + "\n".join(lines) +
               "\n\n📲 Programma completo, meteo e risultati: link in bio (motortimeitalia.it)"
               "\n🔔 Promemoria prima di ogni sessione sul canale Telegram @motortimeitalia\n\n" + TAGS[key])
        items.append({"sid": sid, "ig": sid not in state, "name": f"weekend-{key}-{first:%Y%m%d}" + ("" if sid not in state else "-fb"), "kind": "weekend", "key": key, "caption": cap})
    return items


def tv_text(s):
    """Dove vederla, in testo semplice (per le didascalie)."""
    out = [re.sub(r"^(Diretta|In diretta)\s+", "", p).strip() for p in re.split(r"\s*·\s*", s.get("live") or "")]
    out = [p for p in out if p and "TV8" not in p]
    t = s.get("tv8")
    if isinstance(t, dict) and t.get("time"):
        d = sc.parse(t["time"])
        out.append("TV8 in diretta" if t.get("live") else (f"TV8 in differita alle {d.astimezone(sc.ROME):%H:%M}" if d else "TV8 in differita"))
    elif "TV8" in (s.get("live") or ""):
        out.append("TV8")
    return ", ".join(out)


def day_items(now, state):
    """Il giorno stesso: la mattina di ogni giorno con qualifiche, sprint o gara, gli orari di oggi."""
    items = []
    for key in MAIN:
        w = sc.load(key).get("weekend") or {}
        ss = sorted([s for s in (w.get("sessions") or []) if sc.parse(s.get("start"))], key=lambda s: sc.parse(s["start"]))
        if not w.get("gp") or not ss:
            continue
        today = now.astimezone(sc.ROME).date()
        todays = [s for s in ss if sc.parse(s["start"]).astimezone(sc.ROME).date() == today]
        keys = [s for s in todays if s.get("key")]
        if not keys:
            continue
        k0 = sc.parse(keys[0]["start"])
        morning = datetime(today.year, today.month, today.day, 8, 0, tzinfo=sc.ROME)
        if not (min(morning, k0 - timedelta(hours=3)) <= now < k0):
            continue
        sid = f"day:{key}:{w['gp']}:{today:%Y%m%d}"
        if sid in state and (not FB_CATCHUP or "fb:" + sid in state):
            continue
        lines = []
        for s in todays:
            d = sc.parse(s["start"]).astimezone(sc.ROME)
            tv = tv_text(s)
            lines.append(f"• {s['name']}: alle {d:%H:%M}" + (f" — {tv}" if tv else ""))
        cap = (f"📺 Oggi in pista · {NAMES[key]} · {w['gp']}\n\nGli orari di oggi in ora italiana e dove vederli:\n"
               + "\n".join(lines) +
               "\n\n📲 Programma completo e risultati: link in bio (motortimeitalia.it)"
               "\n🔔 Promemoria prima di ogni sessione sul canale Telegram @motortimeitalia\n\n" + TAGS[key])
        items.append({"sid": sid, "ig": sid not in state, "name": f"day-{key}-{today:%Y%m%d}" + ("" if sid not in state else "-fb"),
                      "kind": "day", "key": key, "day": today.isoformat(), "caption": cap})
    return items


def session_tabs(key, r):
    """Sessioni con classifica da pubblicare, in ordine di svolgimento: qualifiche, sprint, gara.
    WEC: solo la classe Hypercar."""
    tabs = [t for t in (r.get("tabs") or []) if t.get("rows") and t.get("kind") in ("race", "quali")]
    if key == "wec":
        tabs = [t for t in tabs if (t.get("cls") or "Hypercar") == "Hypercar"]
    rank = lambda t: 0 if t["kind"] == "quali" else (2 if str(t.get("label", "")).startswith(("Gara", "Feature")) else 1)
    return sorted(tabs, key=rank)


def results_items(now, state):
    items = []
    for key in MAIN:
        r = sc.load(key).get("results") or {}
        upd = sc.parse(r.get("updated"))
        if not r.get("gp") or not upd or now - upd > timedelta(hours=30):
            continue
        for t in session_tabs(key, r):
            label = t.get("label") or "Gara"
            sid = f"results:{key}:{r['gp']}:{t.get('cls') or ''}:{label}"
            if sid in state and (not FB_CATCHUP or "fb:" + sid in state):
                continue
            pod = [x for x in t["rows"] if str(x.get("pos")) in ("1", "2", "3")][:3]
            if len(pod) < 3:
                continue
            endu = key == "wec"

            def who(x):
                if endu:  # endurance: vettura e equipaggio
                    return f"{x.get('team')} ({x.get('name')})"
                return f"{x.get('name')} ({x.get('team')})"
            if t["kind"] == "quali":
                tm = lambda x: f" · {x['time']}" if str(x.get("time") or "").strip("—- ") else ""
                lines = [f"🥇 Pole position: {who(pod[0])}{tm(pod[0])}",
                         f"2️⃣ {who(pod[1])}{tm(pod[1])}", f"3️⃣ {who(pod[2])}{tm(pod[2])}"]
                cap = (f"⏱️ {NAMES[key]} · {r['gp']}: {label}, la griglia di partenza\n\n" + "\n".join(lines) +
                       "\n\n📲 Griglia completa e orari della gara: link in bio (motortimeitalia.it)")
            else:
                medals = "\n".join(f"{m} {who(x)}" for m, x in zip(["🥇", "🥈", "🥉"], pod))
                what = "della gara" if label.startswith("Gara") else f"della {label}"
                cap = (f"🏁 {NAMES[key]} · {r['gp']}: il podio {what}\n\n{medals}\n\n"
                       "📲 Ordine d'arrivo completo e classifica: link in bio (motortimeitalia.it)")
            cap += "\n🔔 Risultati e promemoria anche su Telegram @motortimeitalia\n\n" + TAGS[key]
            slug = "".join(c if c.isalnum() else "-" for c in f"{label}-{t.get('cls') or ''}".lower()).strip("-")
            items.append({"sid": sid, "ig": sid not in state, "name": f"results-{key}-{slug}-{now:%Y%m%d%H}" + ("" if sid not in state else "-fb"),
                          "kind": "results", "key": key, "tab": {"label": label, "cls": t.get("cls")}, "caption": cap})
    return items


def plan():
    fonts = sys.argv[sys.argv.index("--fonts") + 1]
    sc.FLAGS = sys.argv[sys.argv.index("--flags") + 1] if "--flags" in sys.argv else None
    now = now_utc()
    state = load_state()
    first_run = state is None
    state = state or {}
    os.makedirs(BUILD, exist_ok=True)
    items = results_items(now, state) + day_items(now, state) + weekend_items(now, state)
    if first_run:  # al primo avvio non pubblica risultati vecchi
        for it in [i for i in items if i["kind"] == "results"]:
            state[it["sid"]] = now.isoformat()
        items = [i for i in items if i["kind"] != "results"]
        save_state(state, now)
    pending = []
    for it in items[:4]:  # al massimo 4 pubblicazioni per giro
        if it["kind"] in ("weekend", "day"):
            post = sc.weekend_card(it["key"], fonts, day=it.get("day"))
            story = sc.weekend_card(it["key"], fonts, story=True, day=it.get("day")) if it["ig"] else None
        else:
            post, story = sc.results_card(it["key"], fonts, it.get("tab")), None
        if not post:
            continue
        open(os.path.join(BUILD, it["name"] + ".html"), "w", encoding="utf-8").write(post)
        it["image"] = it["name"] + ".png"
        if story:
            open(os.path.join(BUILD, it["name"] + "-story.html"), "w", encoding="utf-8").write(story)
            it["story"] = it["name"] + "-story.png"
        pending.append(it)
    json.dump(pending, open(os.path.join(BUILD, "pending.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # pulizia: immagini pubblicate da più di 14 giorni
    if os.path.isdir(OUT):
        for f in os.listdir(OUT):
            p = os.path.join(OUT, f)
            if f.endswith(".png") and time.time() - os.path.getmtime(p) > 14 * 86400:
                os.remove(p)
    print(f"work={1 if pending else 0}")
    for it in pending:
        print("da pubblicare:", it["name"], "(+ storia)" if it.get("story") else "")


def api(path, params, token):
    data = urllib.parse.urlencode({**params, "access_token": token}).encode()
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode(errors="replace")) from None


def wait_ready(cid, token):
    for _ in range(20):
        q = urllib.parse.urlencode({"fields": "status_code", "access_token": token})
        with urllib.request.urlopen(f"{GRAPH}/{cid}?{q}", timeout=30) as r:
            st = json.loads(r.read()).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"elaborazione Instagram: {st}")
        time.sleep(6)
    raise RuntimeError("elaborazione Instagram troppo lenta")


def publish_one(url, caption, token, story=False):
    params = {"image_url": url}
    if story:
        params["media_type"] = "STORIES"
    else:
        params["caption"] = caption
    cid = api(f"{IG_USER}/media", params, token)["id"]
    wait_ready(cid, token)
    return api(f"{IG_USER}/media_publish", {"creation_id": cid}, token)["id"]


def publish():
    base = sys.argv[sys.argv.index("--base") + 1].rstrip("/")
    token = os.environ.get("META_PAGE_TOKEN", "").strip()
    now = now_utc()
    state = load_state() or {}
    try:
        pending = json.load(open(os.path.join(BUILD, "pending.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pending = []
    if not token:
        print("Manca META_PAGE_TOKEN: nessuna pubblicazione.")
        return
    done = 0
    for it in pending:
        if not it.get("ig", True):  # recupero solo Facebook
            try:
                msg = it["caption"].replace("link in bio (motortimeitalia.it)", f"https://motortimeitalia.it/{SLUG.get(it['key'], '')}/")
                api(f"{FB_PAGE}/photos", {"url": f"{base}/{it['image']}", "message": msg}, token)
                state["fb:" + it["sid"]] = now.isoformat()
                done += 1
                print("pubblicato su Facebook:", it["name"])
            except Exception as ex:
                print(f"Facebook non pubblicato ({it['name']}): {ex}", file=sys.stderr)
            continue
        try:
            publish_one(f"{base}/{it['image']}", it["caption"], token)
            if it.get("story"):
                try:
                    publish_one(f"{base}/{it['story']}", "", token, story=True)
                except Exception as ex:  # la storia è un extra: se fallisce il post resta valido
                    print(f"Storia non pubblicata ({it['name']}): {ex}", file=sys.stderr)
            state[it["sid"]] = now.isoformat()
            done += 1
            print("pubblicato:", it["name"])
            # stesso post sulla Pagina Facebook (tentato una sola volta: se manca il permesso, lo segnala e basta)
            try:
                msg = it["caption"].replace("link in bio (motortimeitalia.it)", f"https://motortimeitalia.it/{SLUG.get(it['key'], '')}/")
                api(f"{FB_PAGE}/photos", {"url": f"{base}/{it['image']}", "message": msg}, token)
                state["fb:" + it["sid"]] = now.isoformat()
                print("pubblicato su Facebook:", it["name"])
            except Exception as ex:
                print(f"Facebook non pubblicato ({it['name']}): {ex}", file=sys.stderr)
        except Exception as ex:
            print(f"Errore pubblicazione {it['name']}: {ex}", file=sys.stderr)
    save_state(state, now)
    print(f"Pubblicati {done} di {len(pending)}")


if __name__ == "__main__":
    {"plan": plan, "publish": publish}[sys.argv[1]]()
