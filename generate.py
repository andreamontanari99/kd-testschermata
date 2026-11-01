#!/usr/bin/env python3
"""Genera l'immagine della dashboard per Kindle (600x800, 8 bit, scala di grigi).

Uso:
  python generate.py --demo     # dati finti, scrive preview.png (per provare il layout)
  python generate.py            # dati veri, scrive site/<SECRET_PATH>/dashboard.png

Variabili d'ambiente (nel workflow arrivano da GitHub Secrets/Variables):
  ICAL_URL     indirizzo segreto iCal di Google Calendar (secret)
  SECRET_PATH  stringa casuale lunga, usata come cartella dell'immagine (secret)
  LAT, LON     coordinate per il meteo (variables)
"""
import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

W, H = 600, 800
MARGIN = 30
TZ = ZoneInfo("Europe/Rome")

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# Codici meteo WMO usati da Open-Meteo
METEO = {
    0: "Sereno", 1: "Quasi sereno", 2: "Parz. nuvoloso", 3: "Coperto",
    45: "Nebbia", 48: "Nebbia", 51: "Pioggerella", 53: "Pioggerella",
    55: "Pioggerella", 56: "Pioggia gelata", 57: "Pioggia gelata",
    61: "Pioggia debole", 63: "Pioggia", 65: "Pioggia forte",
    66: "Pioggia gelata", 67: "Pioggia gelata", 71: "Neve debole", 73: "Neve",
    75: "Neve forte", 77: "Nevischio", 80: "Rovesci", 81: "Rovesci",
    82: "Rovesci forti", 85: "Rovesci di neve", 86: "Rovesci di neve",
    95: "Temporale", 96: "Temporale e grandine", 99: "Temporale e grandine",
}

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
             "/usr/share/fonts/TTF"]


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        path = os.path.join(d, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------- dati ----

def demo_events(now):
    today = now.date()
    tomorrow = today + dt.timedelta(days=1)

    def at(day, h, m):
        return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)

    return [
        {"day": today, "allday": True, "start": None, "end": None,
         "title": "Compleanno di Marco"},
        {"day": today, "allday": False, "start": at(today, 18, 30),
         "end": at(today, 19, 30), "title": "Allenamento"},
        {"day": today, "allday": False, "start": at(today, 20, 45),
         "end": at(today, 22, 0), "title": "Cena con i nonni"},
        {"day": tomorrow, "allday": False, "start": at(tomorrow, 9, 0),
         "end": at(tomorrow, 10, 0), "title": "Riunione di progetto con il team"},
        {"day": tomorrow, "allday": False, "start": at(tomorrow, 15, 30),
         "end": at(tomorrow, 16, 0), "title": "Dentista"},
    ]


def fetch_events(now):
    """Ritorna (lista eventi, errore). Non stampa mai l'indirizzo del calendario."""
    url = os.environ.get("ICAL_URL")
    if not url:
        return [], "Calendario non configurato"
    try:
        import icalendar
        import recurring_ical_events
        import requests

        r = requests.get(url, timeout=30)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)

        start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=TZ)
        end = start + dt.timedelta(days=2)
        out = []
        for ev in recurring_ical_events.of(cal).between(start, end):
            title = str(ev.get("SUMMARY", "(senza titolo)"))
            s = ev.get("DTSTART").dt
            e = ev.get("DTEND").dt if ev.get("DTEND") is not None else None
            if isinstance(s, dt.datetime):
                s = s.replace(tzinfo=TZ) if s.tzinfo is None else s.astimezone(TZ)
                if isinstance(e, dt.datetime):
                    e = e.replace(tzinfo=TZ) if e.tzinfo is None else e.astimezone(TZ)
                else:
                    e = None
                out.append({"day": s.date(), "allday": False, "start": s,
                            "end": e, "title": title})
            else:  # evento di tutto il giorno (anche su più giorni)
                last = (e - dt.timedelta(days=1)) if e else s
                for k in range((last - s).days + 1):
                    out.append({"day": s + dt.timedelta(days=k), "allday": True,
                                "start": None, "end": None, "title": title})
        return out, None
    except Exception as exc:  # solo il tipo di errore: niente URL nei log
        return [], "Calendario non disponibile (%s)" % type(exc).__name__


def demo_weather(now):
    return {"temp": 11, "code": 3, "tmax": 14, "tmin": 7, "pop": 40,
            "slots": [("15:00", 13, 20), ("18:00", 10, 50), ("21:00", 9, 60)]}


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
                "hourly": "temperature_2m,precipitation_probability",
                "daily": "temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max",
                "forecast_days": 2,
            },
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        times = d["hourly"]["time"]
        slots = []
        for step in (3, 6, 9):
            target = (now + dt.timedelta(hours=step)).replace(
                minute=0, second=0, microsecond=0, tzinfo=None)
            key = target.strftime("%Y-%m-%dT%H:00")
            if key in times:
                i = times.index(key)
                slots.append((target.strftime("%H:%M"),
                              round(d["hourly"]["temperature_2m"][i]),
                              d["hourly"]["precipitation_probability"][i] or 0))
        return {
            "temp": round(d["current"]["temperature_2m"]),
            "code": d["current"]["weather_code"],
            "tmax": round(d["daily"]["temperature_2m_max"][0]),
            "tmin": round(d["daily"]["temperature_2m_min"][0]),
            "pop": d["daily"]["precipitation_probability_max"][0] or 0,
            "slots": slots,
        }, None
    except Exception as exc:
        return None, "Meteo non disponibile (%s)" % type(exc).__name__


# -------------------------------------------------------------- disegno ---

def fit(draw, text, fnt, max_w):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def centered(draw, y, text, fnt, fill=0):
    w = draw.textlength(text, font=fnt)
    draw.text(((W - w) / 2, y), text, font=fnt, fill=fill)


def events_for(events, day, now):
    sel = [e for e in events if e["day"] == day]
    if day == now.date():  # nascondi gli eventi già finiti
        def still_relevant(e):
            if e["allday"]:
                return True
            limit = e["end"] or e["start"]
            return limit >= now
        sel = [e for e in sel if still_relevant(e)]
    sel.sort(key=lambda e: (not e["allday"], e["start"] or now))
    return sel


def draw_agenda(draw, y, label, items, max_rows):
    """Disegna un blocco agenda; ritorna la nuova y."""
    f_head, f_time, f_text = font(22, True), font(22, True), font(22)
    draw.text((MARGIN, y), label, font=f_head, fill=0)
    y += 32
    draw.line((MARGIN, y, W - MARGIN, y), fill=0, width=2)
    y += 10
    if not items:
        draw.text((MARGIN, y), "Nessun impegno", font=f_text, fill=110)
        return y + 36
    shown = items[:max_rows]
    for e in shown:
        label_t = "Tutto il giorno" if e["allday"] else e["start"].strftime("%H:%M")
        if e["allday"]:
            draw.text((MARGIN, y), fit(draw, e["title"], f_text, W - 2 * MARGIN),
                      font=f_text, fill=0)
        else:
            draw.text((MARGIN, y), label_t, font=f_time, fill=0)
            tx = MARGIN + 80
            draw.text((tx, y), fit(draw, e["title"], f_text, W - MARGIN - tx),
                      font=f_text, fill=0)
        y += 34
    if len(items) > len(shown):
        draw.text((MARGIN, y), "+ altri %d" % (len(items) - len(shown)),
                  font=font(18), fill=90)
        y += 30
    return y + 6


def render(now, events, ev_err, weather, w_err):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)

    # Ora e data
    centered(d, 14, now.strftime("%H:%M"), font(128, True))
    data = "%s %d %s" % (GIORNI[now.weekday()], now.day, MESI[now.month - 1])
    centered(d, 158, data, font(32))
    d.line((MARGIN, 208, W - MARGIN, 208), fill=0, width=3)

    # Meteo
    y = 222
    if weather:
        d.text((MARGIN, y - 4), "%d°" % weather["temp"], font=font(72, True), fill=0)
        desc = METEO.get(weather["code"], "")
        d.text((MARGIN + 170, y + 6), desc, font=font(28, True), fill=0)
        d.text((MARGIN + 170, y + 44),
               "min %d°  max %d°  pioggia %d%%" % (
                   weather["tmin"], weather["tmax"], weather["pop"]),
               font=font(20), fill=60)
        cols = weather["slots"]
        if cols:
            cw = (W - 2 * MARGIN) / len(cols)
            for i, (hh, t, p) in enumerate(cols):
                x = MARGIN + i * cw
                d.text((x, y + 100), hh, font=font(18, True), fill=0)
                d.text((x, y + 124), "%d°  %d%%" % (t, p), font=font(20), fill=60)
        y += 168
    else:
        d.text((MARGIN, y + 10), w_err or "Meteo non disponibile",
               font=font(22), fill=110)
        y += 60
    d.line((MARGIN, y, W - MARGIN, y), fill=0, width=3)
    y += 16

    # Agenda
    today, tomorrow = now.date(), now.date() + dt.timedelta(days=1)
    if ev_err:
        d.text((MARGIN, y), ev_err, font=font(22), fill=110)
    else:
        y = draw_agenda(d, y, "OGGI", events_for(events, today, now), 5)
        y = draw_agenda(d, y + 4, "DOMANI", events_for(events, tomorrow, now), 4)

    # Piede
    d.text((MARGIN, H - 30), "aggiornato alle %s" % now.strftime("%H:%M"),
           font=font(16), fill=130)
    return img


# ----------------------------------------------------------------- main ---

def main():
    demo = "--demo" in sys.argv
    now = dt.datetime.now(TZ)

    if demo:
        events, ev_err = demo_events(now), None
        weather, w_err = demo_weather(now), None
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
