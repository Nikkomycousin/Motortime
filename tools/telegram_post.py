#!/usr/bin/env python3
"""Pubblica in automatico sul canale Telegram di Motortime, leggendo i file in data/.

Messaggi:
  1. Programma del weekend: quando la prima sessione di un campionato è entro 36 ore.
  2. Promemoria: circa un'ora prima di qualifiche, sprint e gare (sessioni con key: true).
  3. Risultati: quando cambia results.updated, con il podio della gara principale.

Ogni messaggio viene inviato una sola volta: quelli già pubblicati sono annotati in
tools/telegram_state.json. Senza TELEGRAM_BOT_TOKEN lo script si limita a stampare
cosa pubblicherebbe (prova a vuoto). Con --dry-run non invia nulla e non salva lo stato.

Variabili d'ambiente: TELEGRAM_BOT_TOKEN (segreto), TELEGRAM_CHAT_ID (es. @motortimeitalia).
"""
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "tools", "telegram_state.json")
SITE = "https://motortimeitalia.it"
ROME = ZoneInfo("Europe/Rome")

# chiave, nome, pagina del sito, emoji
SERIES = [
    ("f1", "Formula 1", "formula-1", "🏎️"), ("f2", "Formula 2", "formula-2", "🏎️"), ("f3", "Formula 3", "formula-3", "🏎️"),
    ("motogp", "MotoGP", "motogp", "🏍️"), ("moto2", "Moto2", "moto2", "🏍️"), ("moto3", "Moto3", "moto3", "🏍️"),
    ("wsbk", "Superbike", "superbike", "🏍️"), ("wssp", "Supersport", "supersport", "🏍️"),
    ("wssp300", "World Sportbike", "world-sportbike", "🏍️"),
    ("wec", "WEC", "wec", "🏁"), ("elms", "ELMS", "elms", "🏁"), ("imsa", "IMSA", "imsa", "🏁"),
    ("alms", "Asian Le Mans", "asian-le-mans", "🏁"),
]
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
e = lambda s: html.escape(str(s or ""), quote=False)


def parse(ts):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def load(key):
    try:
        with open(os.path.join(ROOT, "data", key + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def tv(s):
    out = s.get("live") or ""
    t = s.get("tv8")
    if isinstance(t, dict) and t.get("time") and "TV8" not in out:
        when = parse(t["time"])
        if t.get("live"):
            out += " · TV8 in diretta"
        elif when:
            out += f" · TV8 in differita alle {when.astimezone(ROME):%H:%M}"
    return out


def link(slug, label="Orari, risultati e classifica"):
    return f'<a href="{SITE}/{slug}/">{label} su Motortime</a>'


def weekend_msgs(now, state):
    out = []
    for key, name, slug, em in SERIES:
        w = load(key).get("weekend") or {}
        ss = sorted([s for s in (w.get("sessions") or []) if parse(s.get("start"))], key=lambda s: parse(s["start"]))
        if not w.get("gp") or not ss:
            continue
        first, last = parse(ss[0]["start"]), parse(ss[-1]["start"])
        sid = f"weekend:{key}:{w['gp']}:{first:%Y%m%d}"
        if sid in state or not (now <= first <= now + timedelta(hours=36)) or last < now:
            continue
        lines = [f"{em} <b>{e(name)} · {e(w['gp'])}</b>", f"<i>{e(w.get('circuit'))}</i>", "", "Orari italiani e dove vederlo:"]
        day = None
        for s in ss:
            d = parse(s["start"]).astimezone(ROME)
            if d.date() != day:
                day = d.date()
                lines.append(f"\n<b>{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}</b>")
            name_s = f"<b>{e(s['name'])}</b>" if s.get("key") else e(s["name"])
            ch = tv(s)
            lines.append(f"{d:%H:%M} {name_s}" + (f" — {e(ch)}" if ch else ""))
        if w.get("tv8note"):
            lines += ["", f"📺 {e(w['tv8note'])}"]
        lines += ["", link(slug)]
        out.append((sid, "\n".join(lines), False))
    return out


def reminder_msgs(now, state):
    out = []
    for key, name, slug, em in SERIES:
        w = load(key).get("weekend") or {}
        for s in w.get("sessions") or []:
            st = parse(s.get("start"))
            if not s.get("key") or not st:
                continue
            sid = f"remind:{key}:{s['name']}:{st:%Y%m%d%H%M}"
            if sid in state or not (now + timedelta(minutes=20) <= st <= now + timedelta(minutes=95)):
                continue
            loc = st.astimezone(ROME)
            ch = tv(s)
            txt = (f"⏱️ <b>Tra poco: {e(name)} · {e(s['name'])}</b>\n{e(w.get('gp'))}\n\n"
                   f"🕐 Alle <b>{loc:%H:%M}</b> (ora italiana)" + (f"\n📺 {e(ch)}" if ch else "") + f"\n\n{link(slug, 'Segui la sessione')}")
            silent = loc.hour < 7  # di notte senza suono
            out.append((sid, txt, silent))
    return out


def results_msgs(now, state):
    out = []
    for key, name, slug, em in SERIES:
        r = load(key).get("results") or {}
        upd = parse(r.get("updated"))
        tabs = [t for t in (r.get("tabs") or []) if t.get("kind") == "race" and t.get("rows")]
        if not r.get("gp") or not upd or not tabs:
            continue
        sid = f"results:{key}:{r['gp']}:{r.get('updated')}"
        gp_sid = f"resultsgp:{key}:{r['gp']}:{len(tabs)}"
        if sid in state or gp_sid in state or now - upd > timedelta(hours=30):
            continue
        lines = [f"🏁 <b>{e(name)} · Risultati {e(r['gp'])}</b>"]
        for t in tabs[:4]:
            label = f"{t.get('cls') + ' · ' if t.get('cls') else ''}{t.get('label')}"
            pod = [x for x in t["rows"] if str(x.get("pos")) in ("1", "2", "3")][:3]
            if not pod:
                continue
            lines.append(f"\n<b>{e(label)}</b>")
            for x, medal in zip(pod, ["🥇", "🥈", "🥉"]):
                lines.append(f"{medal} {e(x.get('name'))} <i>({e(x.get('team'))})</i>")
        if r.get("summary"):
            summ = r["summary"]
            lines += ["", e(summ if len(summ) < 400 else summ[:397].rsplit(" ", 1)[0] + "…")]
        lines += ["", link(slug, "Ordine d'arrivo completo e classifica")]
        out.append((sid, "\n".join(lines), False, gp_sid))
    return out


def send(token, chat, text, silent):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true",
                                   "disable_notification": "true" if silent else "false"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read())
        if not body.get("ok"):
            raise RuntimeError(body)


def main():
    dry = "--dry-run" in sys.argv
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    now = datetime.now(timezone.utc)
    if "--now" in sys.argv:
        now = parse(sys.argv[sys.argv.index("--now") + 1])
    first_run = not os.path.exists(STATE)
    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        state = {}

    msgs = [(m[0], m[1], m[2], m[3] if len(m) > 3 else None)
            for m in weekend_msgs(now, state) + reminder_msgs(now, state) + results_msgs(now, state)]

    # Al primo avvio non ripubblica risultati vecchi: li segna come già inviati.
    if first_run and not dry:
        for sid, _, _, extra in msgs:
            if sid.startswith("results:"):
                state[sid] = now.isoformat()
                if extra:
                    state[extra] = now.isoformat()
        msgs = [m for m in msgs if not m[0].startswith("results:")]

    if token and chat and "welcome" not in state:
        msgs.insert(0, ("welcome",
            "👋 <b>Benvenuti su Motortime!</b>\n\n"
            "Qui trovate, in automatico:\n"
            "📅 gli <b>orari del weekend</b> in ora italiana, con i canali TV (Sky, NOW, TV8)\n"
            "⏱️ un <b>promemoria</b> prima di qualifiche, sprint e gare\n"
            "🏁 i <b>risultati</b> appena disponibili\n\n"
            "Formula 1, F2, F3, MotoGP, Moto2, Moto3, Superbike ed endurance (WEC, ELMS, IMSA, Asian Le Mans).\n\n"
            f'<a href="{SITE}/">Tutto su motortimeitalia.it</a>', False, None))

    sent = 0
    for sid, text, silent, extra in msgs:
        if dry or not token or not chat:
            print(f"--- {sid}{' (silenzioso)' if silent else ''}\n{text}\n")
            continue
        try:
            send(token, chat, text, silent)
            sent += 1
        except Exception as ex:  # un errore non deve bloccare gli altri messaggi
            print(f"Errore invio {sid}: {ex}", file=sys.stderr)
            continue
        state[sid] = now.isoformat()
        if extra:
            state[extra] = now.isoformat()

    if not dry and (token and chat or first_run):
        cutoff = now - timedelta(days=60)  # tiene il file piccolo
        state = {k: v for k, v in state.items() if (parse(v) or now) > cutoff}
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
    print(f"Messaggi da pubblicare: {len(msgs)}, inviati: {sent}" + ("" if token and chat else " (manca il token: prova a vuoto)"))


if __name__ == "__main__":
    main()
