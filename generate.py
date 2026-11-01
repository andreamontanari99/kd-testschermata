#!/usr/bin/env python3
"""Genera l'immagine della dashboard per Kindle (600x800, 8 bit, scala di grigi).

Uso:
  python generate.py --demo     # dati finti, scrive preview.png (per provare il layout)
  python generate.py            # dati veri, scrive site/<SECRET_PATH>/dashboard.png

Variabili d'ambiente (nel workflow arrivano da GitHub Secrets/Variables):
  ICAL_URL            indirizzo segreto iCal di Google Calendar (secret)
  BIRTHDAYS_ICAL_URL  (facoltativo) calendario separato con i compleanni (secret)
  SECRET_PATH         stringa casuale lunga, usata come cartella dell'immagine (secret)
  LAT, LON            coordinate per il meteo (variables)

I font Poppins vanno messi nella cartella "fonts" accanto a questo file.
"""
import datetime as dt
import math
import os
import re
import sys
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

W, H = 600, 800
TZ = ZoneInfo("Europe/Rome")

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set",
              "ott", "nov", "dic"]

# Codici meteo WMO usati da Open-Meteo
METEO = {
    0: "Sereno", 1: "Quasi sereno", 2: "Poco nuvoloso", 3: "Coperto",
    45: "Nebbia", 48: "Nebbia", 51: "Pioggerella", 53: "Pioggerella",
    55: "Pioggerella", 56: "Pioggia gelata", 57: "Pioggia gelata",
    61: "Pioggia debole", 63: "Pioggia", 65: "Pioggia forte",
    66: "Pioggia gelata", 67: "Pioggia gelata", 71: "Neve debole", 73: "Neve",
    75: "Neve forte", 77: "Nevischio", 80: "Rovesci", 81: "Rovesci",
    82: "Rovesci forti", 85: "Rovesci di neve", 86: "Rovesci di neve",
    95: "Temporale", 96: "Temporale", 99: "Temporale",
}

BDAY_RE = re.compile(r"compleann|birthday|b-?day|🎂", re.I)

# ---------------------------------------------------------------- font ----

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"),
             "/usr/share/fonts/truetype/google-fonts",
             "/usr/share/fonts/truetype/dejavu"]
FONT_FILES = {"light": "Poppins-Light.ttf", "regular": "Poppins-Regular.ttf",
              "medium": "Poppins-Medium.ttf"}
_cache = {}


def font(size, weight="regular"):
    key = (size, weight)
    if key in _cache:
        return _cache[key]
    fallback = "DejaVuSans-Bold.ttf" if weight == "medium" else "DejaVuSans.ttf"
    found = None
    for name in (FONT_FILES[weight], fallback):
        for folder in FONT_DIRS:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                found = ImageFont.truetype(path, size)
                break
        if found:
            break
    _cache[key] = found or ImageFont.load_default()
    return _cache[key]


# ---------------------------------------------------------------- dati ----

def demo_data(now):
    today = now.date()

    def at(day, h, m):
        return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)

    def day(n):
        return today + dt.timedelta(days=n)

    def ev(d, h, m, title, allday=False, bday=False):
        return {"day": d, "allday": allday, "bday": bday, "title": title,
                "start": None if allday else at(d, h, m),
                "end": None if allday else at(d, h + 1, m)}

    events = [
        ev(today, 0, 0, "Giornata di studio", allday=True),
        ev(today, 18, 30, "Allenamento"),
        ev(today, 20, 45, "Cena con i nonni"),
        ev(day(1), 9, 0, "Riunione di progetto"),
        ev(day(2), 15, 30, "Dentista"),
        ev(day(4), 0, 0, "Weekend a Bologna", allday=True),
        ev(day(5), 0, 0, "Compleanno di Giulia", allday=True, bday=True),
        ev(day(12), 0, 0, "Compleanno di Luca", allday=True, bday=True),
        ev(day(30), 0, 0, "Compleanno di Anna", allday=True, bday=True),
    ]
    weather = {
        "temp": 11, "code": 3, "tmax": 14, "tmin": 7, "pop": 40,
        "days": [
            {"day": day(1), "code": 61, "tmax": 13, "tmin": 8, "pop": 70},
            {"day": day(2), "code": 2, "tmax": 15, "tmin": 6, "pop": 10},
        ],
    }
    return events, weather


def parse_calendar(url, start, end, force_bday=False):
    import icalendar
    import recurring_ical_events
    import requests

    r = requests.get(url, timeout=30)
    r.raise_for_status()
    cal = icalendar.Calendar.from_ical(r.content)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        title = str(ev.get("SUMMARY", "(senza titolo)"))
        bday = force_bday or bool(BDAY_RE.search(title))
        s = ev.get("DTSTART").dt
        e = ev.get("DTEND").dt if ev.get("DTEND") is not None else None
        if isinstance(s, dt.datetime):
            s = s.replace(tzinfo=TZ) if s.tzinfo is None else s.astimezone(TZ)
            if isinstance(e, dt.datetime):
                e = e.replace(tzinfo=TZ) if e.tzinfo is None else e.astimezone(TZ)
            else:
                e = None
            out.append({"day": s.date(), "allday": False, "bday": bday,
                        "start": s, "end": e, "title": title})
        else:  # evento di tutto il giorno (anche su più giorni)
            last = (e - dt.timedelta(days=1)) if e else s
            for k in range((last - s).days + 1):
                out.append({"day": s + dt.timedelta(days=k), "allday": True,
                            "bday": bday, "start": None, "end": None,
                            "title": title})
    return out


def fetch_events(now):
    """Ritorna (eventi, errore). Non stampa mai gli indirizzi dei calendari."""
    url = os.environ.get("ICAL_URL")
    if not url:
        return [], "Calendario non configurato"
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=TZ)
    end = start + dt.timedelta(days=62)
    try:
        events = parse_calendar(url, start, end)
    except Exception as exc:  # solo il tipo di errore: niente URL nei log
        return [], "Calendario non disponibile (%s)" % type(exc).__name__
    bday_url = os.environ.get("BIRTHDAYS_ICAL_URL")
    if bday_url:
        try:
            events += parse_calendar(bday_url, start, end, force_bday=True)
        except Exception as exc:
            print("Avviso: compleanni non disponibili (%s)" % type(exc).__name__)
    return events, None


def fetch_weather(now):
    lat, lon = os.environ.get("LAT"), os.environ.get("LON")
    if not lat or not lon:
        return None, "Meteo non configurato"
    try:
        import requests

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "timezone": "Europe/Rome",
                "current": "temperature_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max",
                "forecast_days": 3,
            },
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        daily = d["daily"]
        days = []
        for i in (1, 2):
            days.append({
                "day": dt.date.fromisoformat(daily["time"][i]),
                "code": daily["weather_code"][i],
                "tmax": round(daily["temperature_2m_max"][i]),
                "tmin": round(daily["temperature_2m_min"][i]),
                "pop": daily["precipitation_probability_max"][i] or 0,
            })
        return {
            "temp": round(d["current"]["temperature_2m"]),
            "code": d["current"]["weather_code"],
            "tmax": round(daily["temperature_2m_max"][0]),
            "tmin": round(daily["temperature_2m_min"][0]),
            "pop": daily["precipitation_probability_max"][0] or 0,
            "days": days,
        }, None
    except Exception as exc:
        return None, "Meteo non disponibile (%s)" % type(exc).__name__


# --------------------------------------------------------------- icone ----

def icon_kind(code):
    if code in (0, 1):
        return "clear"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunder"
    return "rain"


def make_icon(kind, size, night=False):
    """Icona al tratto, disegnata ingrandita 4x e poi ridotta (bordi lisci)."""
    S = 4
    n = size * S
    img = Image.new("L", (n, n), 255)
    d = ImageDraw.Draw(img)
    sw = max(3, int(n * 0.055))

    def P(v):
        return v * n

    def sun(cx, cy, r, rays=True):
        d.ellipse([P(cx - r), P(cy - r), P(cx + r), P(cy + r)], outline=0, width=sw)
        if rays:
            for i in range(8):
                a = math.radians(i * 45)
                r1, r2 = r + 0.08, r + 0.17
                d.line([P(cx + r1 * math.cos(a)), P(cy + r1 * math.sin(a)),
                        P(cx + r2 * math.cos(a)), P(cy + r2 * math.sin(a))],
                       fill=0, width=sw)

    def moon(cx, cy, r):
        d.ellipse([P(cx - r), P(cy - r), P(cx + r), P(cy + r)], fill=0)
        o = r * 0.45
        d.ellipse([P(cx - r * 0.85 + o), P(cy - r * 0.85 - o),
                   P(cx + r * 0.85 + o), P(cy + r * 0.85 - o)], fill=255)

    def cloud(ox, oy, s):
        circles = [(0.30, 0.55, 0.14), (0.50, 0.42, 0.19), (0.70, 0.55, 0.13)]
        for grow, color in ((sw, 0), (0, 255)):
            for cx, cy, r in circles:
                x, y, rr = P(ox + cx * s), P(oy + cy * s), P(r * s) + grow
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)
            d.rounded_rectangle(
                [P(ox + 0.18 * s) - grow, P(oy + 0.50 * s) - grow,
                 P(ox + 0.82 * s) + grow, P(oy + 0.69 * s) + grow],
                radius=P(0.09 * s), fill=color)

    if kind == "clear":
        moon(0.5, 0.5, 0.26) if night else sun(0.5, 0.5, 0.2)
    elif kind == "partly":
        moon(0.36, 0.36, 0.17) if night else sun(0.36, 0.36, 0.13)
        cloud(0.12, 0.17, 0.85)
    elif kind == "cloud":
        cloud(0.0, 0.08, 1.0)
    elif kind == "fog":
        for y, (a, b) in zip((0.28, 0.44, 0.60, 0.76),
                             ((0.20, 0.80), (0.10, 0.90), (0.20, 0.80), (0.32, 0.68))):
            d.line([P(a), P(y), P(b), P(y)], fill=0, width=sw)
    else:
        cloud(0.0, -0.06, 1.0)
        if kind == "rain":
            for x in (0.34, 0.51, 0.68):
                d.line([P(x), P(0.74), P(x - 0.05), P(0.90)], fill=0, width=sw)
        elif kind == "snow":
            for x, y in ((0.34, 0.76), (0.51, 0.88), (0.68, 0.76)):
                r = 0.028
                d.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=0)
        elif kind == "thunder":
            pts = [(0.56, 0.62), (0.42, 0.84), (0.53, 0.84), (0.47, 0.98),
                   (0.68, 0.74), (0.56, 0.74)]
            d.polygon([(P(x), P(y)) for x, y in pts], fill=0)
    return img.resize((size, size), Image.LANCZOS)


# -------------------------------------------------------------- disegno ---

def text(d, x, y, s, f, fill=0, anchor="ls"):
    d.text((x, y), s, font=f, fill=fill, anchor=anchor)


def fit(d, s, f, max_w):
    if d.textlength(s, font=f) <= max_w:
        return s
    while s and d.textlength(s + "…", font=f) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def spaced(d, x, y, s, f, fill, spacing):
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += d.textlength(ch, font=f) + spacing


def center_in(d, box, s, f, ref=None, fill=0):
    x0, y0, x1, y1 = box
    _, t, _, b = d.textbbox((0, 0), ref or s, font=f, anchor="ls")
    y = y0 + ((y1 - y0) - (b - t)) / 2 - t
    d.text(((x0 + x1) / 2, y), s, font=f, fill=fill, anchor="ms")


def block(d, box, label=None, extra=None):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=14, outline=40, width=2)
    if label:
        spaced(d, x0 + 16, y0 + 27, label, font(12, "medium"), 110, 2.2)
    if extra:
        text(d, x1 - 16, y0 + 27, extra, font(12, "medium"), 110, "rs")


def clean_bday(title):
    t = re.sub(r"^\s*(buon\s+)?compleanno\s+(di\s+)?", "", title, flags=re.I)
    t = re.sub(r"['’]s\s+birthday\s*$", "", t, flags=re.I)
    t = t.replace("🎂", "").strip(" -–:")
    return t or title


def events_today(events, now):
    sel = []
    for e in events:
        if e["bday"] or e["day"] != now.date():
            continue
        if not e["allday"] and (e["end"] or e["start"]) < now:
            continue  # già finito
        sel.append(e)
    sel.sort(key=lambda e: (not e["allday"], e["start"] or now))
    return sel


def events_future(events, now, days=14):
    today = now.date()
    sel = [e for e in events
           if not e["bday"] and today < e["day"] <= today + dt.timedelta(days=days)]
    sel.sort(key=lambda e: (e["day"], not e["allday"], e["start"] or now))
    seen, out = set(), []
    for e in sel:  # un evento su più giorni compare solo la prima volta
        if e["title"] in seen:
            continue
        seen.add(e["title"])
        out.append(e)
    return out


def birthdays(events, now, days=60):
    today = now.date()
    sel = [e for e in events
           if e["bday"] and today <= e["day"] <= today + dt.timedelta(days=days)]
    sel.sort(key=lambda e: e["day"])
    seen, out = set(), []
    for e in sel:
        key = (e["day"], e["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def render(now, events, ev_err, weather, w_err):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)

    M, GAP = 20, 12
    XL1 = 288
    XR0 = XL1 + GAP
    X1 = W - M
    today = now.date()

    # --- Orario
    box = (M, 20, X1, 180)
    d.rounded_rectangle(box, radius=14, outline=40, width=2)
    center_in(d, box, now.strftime("%H:%M"), font(124, "light"), ref="00:00")

    # --- Giorno, data, mese
    box = (M, 190, X1, 244)
    d.rounded_rectangle(box, radius=14, outline=40, width=2)
    data = "%s %d %s" % (GIORNI[now.weekday()], now.day, MESI[now.month - 1])
    center_in(d, box, data, font(27), ref="mercoledì 30 settembre")

    # --- Meteo (a sinistra)
    mid_top, mid_bot = 254, 520
    bx = (M, mid_top, XL1, mid_bot)
    block(d, bx, "METEO")
    x0, y0, x1, y1 = bx
    if weather:
        night = not (7 <= now.hour < 19)
        text(d, x0 + 16, y0 + 112, "%d°" % weather["temp"], font(84, "light"))
        img.paste(make_icon(icon_kind(weather["code"]), 84, night),
                  (x1 - 16 - 84, y0 + 38))
        text(d, x0 + 16, y0 + 162, METEO.get(weather["code"], ""), font(22, "medium"))
        text(d, x0 + 16, y0 + 198,
             "min %d°   max %d°" % (weather["tmin"], weather["tmax"]), font(18))
        text(d, x0 + 16, y0 + 228, "pioggia %d%%" % weather["pop"], font(16), 100)
    else:
        text(d, x0 + 16, y0 + 70, fit(d, w_err or "Meteo non disponibile",
                                      font(16), x1 - x0 - 32), font(16), 110)

    # --- Impegni di oggi (a destra, in alto)
    bx = (XR0, mid_top, X1, 392)
    today_ev = events_today(events, now) if not ev_err else []
    max_rows = 4
    extra = "+%d" % (len(today_ev) - max_rows) if len(today_ev) > max_rows else None
    block(d, bx, "OGGI", extra)
    x0, y0, x1, y1 = bx
    if ev_err:
        text(d, x0 + 16, y0 + 66, fit(d, ev_err, font(15), x1 - x0 - 32), font(15), 110)
    elif not today_ev:
        text(d, x0 + 16, y0 + 66, "Nessun impegno", font(17), 110)
    else:
        y = y0 + 54
        for e in today_ev[:max_rows]:
            if e["allday"]:
                d.ellipse([x0 + 17, y - 12, x0 + 26, y - 3], outline=0, width=2)
            else:
                text(d, x0 + 16, y, e["start"].strftime("%H:%M"), font(16, "medium"))
            tx = x0 + 72
            text(d, tx, y, fit(d, e["title"], font(17), x1 - 12 - tx), font(17))
            y += 24

    # --- Impegni futuri (a destra, in basso)
    bx = (XR0, 404, X1, mid_bot)
    block(d, bx, "PROSSIMI GIORNI")
    x0, y0, x1, y1 = bx
    fut = events_future(events, now) if not ev_err else []
    if not fut:
        text(d, x0 + 16, y0 + 62, "Nulla in programma", font(17), 110)
    else:
        y = y0 + 54
        for e in fut[:3]:
            lab = "%s %d" % (GIORNI_BREVI[e["day"].weekday()], e["day"].day)
            text(d, x0 + 16, y, lab, font(16, "medium"))
            tx = x0 + 80
            text(d, tx, y, fit(d, e["title"], font(17), x1 - 12 - tx), font(17))
            y += 24

    # --- Previsioni (in basso a sinistra)
    bot_top, bot_bot = 532, 742
    bx = (M, bot_top, XL1, bot_bot)
    block(d, bx, "PREVISIONI")
    x0, y0, x1, y1 = bx
    if weather:
        colw = (x1 - x0) / 2
        d.line((x0 + colw, y0 + 44, x0 + colw, y1 - 20), fill=190, width=1)
        for i, day in enumerate(weather["days"]):
            cx = x0 + colw * i + colw / 2
            lab = "%s %d" % (GIORNI_BREVI[day["day"].weekday()], day["day"].day)
            text(d, cx, y0 + 66, lab, font(17, "medium"), 0, "ms")
            img.paste(make_icon(icon_kind(day["code"]), 60),
                      (int(cx - 30), y0 + 78))
            text(d, cx, y0 + 168, "%d° / %d°" % (day["tmax"], day["tmin"]),
                 font(18), 0, "ms")
            text(d, cx, y0 + 192, "pioggia %d%%" % day["pop"], font(13), 100, "ms")
    else:
        text(d, x0 + 16, y0 + 70, "Non disponibili", font(16), 110)

    # --- Compleanni (in basso a destra)
    bx = (XR0, bot_top, X1, bot_bot)
    block(d, bx, "COMPLEANNI")
    x0, y0, x1, y1 = bx
    bds = birthdays(events, now) if not ev_err else []
    if not bds:
        text(d, x0 + 16, y0 + 66, "Nessuno a breve", font(17), 110)
    else:
        y = y0 + 62
        for e in bds[:5]:
            if e["day"] == today:
                lab = "oggi"
            elif e["day"] == today + dt.timedelta(days=1):
                lab = "domani"
            else:
                lab = "%d %s" % (e["day"].day, MESI_BREVI[e["day"].month - 1])
            text(d, x0 + 16, y, lab, font(16, "medium"))
            tx = x0 + 88
            text(d, tx, y, fit(d, clean_bday(e["title"]), font(17), x1 - 12 - tx),
                 font(17))
            y += 28

    # --- Piede
    text(d, W / 2, 770, "aggiornato alle %s" % now.strftime("%H:%M"),
         font(13), 140, "ms")
    return img


# ----------------------------------------------------------------- main ---

def main():
    demo = "--demo" in sys.argv
    now = dt.datetime.now(TZ)

    if demo:
        events, weather = demo_data(now)
        ev_err = w_err = None
        out_path = "preview.png"
    else:
        secret = os.environ.get("SECRET_PATH", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", secret):
            sys.exit("SECRET_PATH mancante o troppo corto (servono almeno 16 "
                     "caratteri tra lettere, numeri, - e _).")
        events, ev_err = fetch_events(now)
        weather, w_err = fetch_weather(now)
        os.makedirs(os.path.join("site", secret), exist_ok=True)
        with open(os.path.join("site", "index.html"), "w") as f:
            f.write("<!doctype html><title>.</title>")
        out_path = os.path.join("site", secret, "dashboard.png")

    img = render(now, events, ev_err, weather, w_err)
    img.save(out_path, optimize=True)
    print("Immagine generata (%dx%d)." % img.size)
    if ev_err:
        print("Avviso:", ev_err)
    if w_err:
        print("Avviso:", w_err)


if __name__ == "__main__":
    main()
