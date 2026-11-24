"""Haalt AI-nieuws op uit openbare Google Nieuws RSS-feeds en schrijft ai-nieuws.json.

Vijf categorieen in balans (zelfde aantal berichten per categorie).
Alleen kop, bron, datum en link: geen volledige artikelen.
Draait straks dagelijks om 07:00 (Nederlandse tijd) via GitHub Actions.
"""
import json, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

PER_CATEGORIE = 6

def feed(q, taal):
    if taal == "nl":
        return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "nl", "gl": "NL", "ceid": "NL:nl"})
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})

CATEGORIEEN = [
    {"id": "grappig", "naam": "Grappig AI-nieuws", "kort": "Grappig",
     "feeds": [feed('AI (bizarre OR funny OR weird OR hilarious OR "goes wrong") when:7d', "en"), feed('AI opmerkelijk OR bizar OR grappig when:14d', "nl")]},
    {"id": "nederland", "naam": "AI in Nederland", "kort": "Nederland",
     "feeds": [feed('"kunstmatige intelligentie" OR AI Nederland when:3d', "nl")]},
    {"id": "internationaal", "naam": "Internationaal AI-nieuws", "kort": "Internationaal",
     "feeds": [feed('AI (OpenAI OR Anthropic OR Google OR Meta OR Microsoft) when:2d', "en")]},
    {"id": "ondernemers", "naam": "AI voor ondernemers", "kort": "Ondernemers",
     "feeds": [feed('AI ondernemers OR mkb OR ondernemer when:7d', "nl"), feed('AI "small business" when:5d', "en")]},
    {"id": "tools", "naam": "Nieuwste AI-tools", "kort": "Tools",
     "feeds": [feed('AI (launches OR unveils OR releases OR rolls out) (tool OR app OR feature OR assistant) (site:techcrunch.com OR site:theverge.com OR site:venturebeat.com OR site:engadget.com OR site:zdnet.com OR site:tweakers.net) when:4d', "en")]},
]

def haal(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (riteshtikai.com nieuwsoverzicht)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def items(xml):
    root = ET.fromstring(xml)
    for it in root.iter("item"):
        titel = (it.findtext("title") or "").strip()
        bron_el = it.find("source")
        bron = (bron_el.text or "").strip() if bron_el is not None else ""
        if bron and titel.endswith(" - " + bron):
            titel = titel[: -len(" - " + bron)]
        try:
            datum = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        except Exception:
            continue
        yield {"titel": titel, "bron": bron, "link": (it.findtext("link") or "").strip(), "datum": datum.isoformat()}

STOP = set("the a an of to in on for and or with is are be as at by from its it this that de het een en van in op voor met is zijn te dat die ai".split())
def woorden(t):
    import re
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 2 and w not in STOP}

def main(uit):
    data = {"bijgewerkt": datetime.now(timezone.utc).isoformat(), "categorieen": []}
    gezien = set()
    for c in CATEGORIEEN:
        verzameld = []
        for u in c["feeds"]:
            try:
                verzameld += list(items(haal(u)))
            except Exception as e:
                print("feed mislukt:", c["id"], e, file=sys.stderr)
        verzameld.sort(key=lambda x: x["datum"], reverse=True)
        gekozen = []
        for x in verzameld:
            sleutel = x["titel"].lower()[:70]
            if sleutel in gezien or not x["link"].startswith("https://") or x["titel"].count("#") >= 2 or len(x["titel"]) < 25:
                continue
            w = woorden(x["titel"])
            if any(len(w & woorden(g["titel"])) >= 2 for g in gekozen):
                continue  # te veel hetzelfde verhaal
            if sum(1 for g in gekozen if g["bron"] == x["bron"]) >= 2:
                continue
            gezien.add(sleutel); gekozen.append(x)
            if len(gekozen) == PER_CATEGORIE:
                break
        data["categorieen"].append({"id": c["id"], "naam": c["naam"], "kort": c["kort"], "berichten": gekozen})
        print(c["id"], len(gekozen))
    Path(uit).write_text(json.dumps(data, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ai-nieuws.json")
