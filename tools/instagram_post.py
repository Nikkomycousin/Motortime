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
SLUG = {"f1": "formula-1", "motogp": "motogp", "wsbk": "superbike", "wec": "wec"}
GRAPH = "https://graph.facebook.com/v21.0"
STATE = os.path.join(ROOT, "tools", "instagram_state.json")
BUILD = os.path.join(ROOT, "build", "social")
OUT = os.path.join(ROOT, "social")

# Campionati pubblicati su Instagram (i principali, per non intasare il profilo)
MAIN = ["f1", "motogp", "wsbk", "wec"]
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
        if sid in state or not (now <= first <= now + timedelta(hours=36)) or last < now:
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
        items.append({"sid": sid, "name": f"weekend-{key}-{first:%Y%m%d}", "kind": "weekend", "key": key, "caption": cap})
    return items


def results_items(now, state):
    items = []
    for key in MAIN:
        r = sc.load(key).get("results") or {}
        upd = sc.parse(r.get("updated"))
        races = [t for t in (r.get("tabs") or []) if t.get("kind") == "race" and t.get("rows")]
        mains = [t for t in races if str(t.get("label", "")).startswith(("Gara", "Feature"))]
        if not r.get("gp") or not upd or not mains or now - upd > timedelta(hours=30):
            continue
        sid = f"results:{key}:{r['gp']}:{len(mains)}"
        if sid in state:
            continue
        main = mains[0]
        pod = [x for x in main["rows"] if str(x.get("pos")) in ("1", "2", "3")][:3]
        if len(pod) < 3:
            continue
        medals = "\n".join(f"{m} {x.get('name')} ({x.get('team')})" for m, x in zip(["🥇", "🥈", "🥉"], pod))
        cap = (f"🏁 {NAMES[key]} · {r['gp']}: il podio\n\n{medals}\n\n"
               "📲 Ordine d'arrivo completo e classifica: link in bio (motortimeitalia.it)"
               "\n🔔 Risultati e promemoria anche su Telegram @motortimeitalia\n\n" + TAGS[key])
        items.append({"sid": sid, "name": f"results-{key}-{now:%Y%m%d%H}", "kind": "results", "key": key, "caption": cap})
    return items


def plan():
    fonts = sys.argv[sys.argv.index("--fonts") + 1]
    sc.FLAGS = sys.argv[sys.argv.index("--flags") + 1] if "--flags" in sys.argv else None
    now = now_utc()
    state = load_state()
    first_run = state is None
    state = state or {}
    os.makedirs(BUILD, exist_ok=True)
    items = weekend_items(now, state) + results_items(now, state)
    if first_run:  # al primo avvio non pubblica risultati vecchi
        for it in [i for i in items if i["kind"] == "results"]:
            state[it["sid"]] = now.isoformat()
        items = [i for i in items if i["kind"] != "results"]
        save_state(state, now)
    pending = []
    for it in items[:4]:  # al massimo 4 pubblicazioni per giro
        if it["kind"] == "weekend":
            post = sc.weekend_card(it["key"], fonts)
            story = sc.weekend_card(it["key"], fonts, story=True)
        else:
            post, story = sc.results_card(it["key"], fonts), None
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
                print("pubblicato su Facebook:", it["name"])
            except Exception as ex:
                print(f"Facebook non pubblicato ({it['name']}): {ex}", file=sys.stderr)
        except Exception as ex:
            print(f"Errore pubblicazione {it['name']}: {ex}", file=sys.stderr)
    save_state(state, now)
    print(f"Pubblicati {done} di {len(pending)}")


if __name__ == "__main__":
    {"plan": plan, "publish": publish}[sys.argv[1]]()
