"""Haalt AI-nieuws op uit openbare Google Nieuws RSS-feeds en schrijft ai-nieuws.json.

Vijf categorieen in balans (zelfde aantal berichten per categorie).
Alleen kop, bron, datum en link: geen volledige artikelen.
Grappig: filter A (zoekwoorden + serieuze onderwerpen eruit), daarna kiest Claude Haiku
de echt grappige koppen als ANTHROPIC_API_KEY bestaat (B). Zonder sleutel blijft A over.
Draait dagelijks om 07:00 (Nederlandse tijd) via GitHub Actions.
"""
import json, os, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
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
     "grappig": True,
     "feeds": [feed('AI (hilarious OR funny OR "goes viral" OR prank OR fail OR oops OR blunder OR mishap OR accidentally) when:7d', "en"),
               feed('chatbot (hilarious OR funny OR weird OR "went rogue" OR accidentally OR fail) when:10d', "en"),
               feed('AI (robot OR chatbot) (bizarre OR weird OR funny OR fail) when:7d', "en"),
               feed('AI opmerkelijk OR bizar OR grappig OR hilarisch OR blunder when:14d', "nl")]},
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

# Filter A: serieuze onderwerpen eruit, en zonder AI-beoordeling moet de kop echt grappig klinken
SERIEUS = re.compile(r"\b(trump|biden|election|verkiezing|war|oorlog|killed|death|dead|dood|suicide|zelfmoord|lawsuit|sued|rechtszaak|court|rechter|fraud|fraude|scam|abuse|misbruik|porn|nude|child|kind(eren)?|shooting|police|politie|layoffs?|ontslag|essay|opinie|opinion|interview|policy|beleid|regulation|wetgeving|stocks?|markets?|aandel(en)?|beurs|votes?|stem(men)?|backlash|critics)\b", re.I)
GRAP = re.compile(r"\b(hilarious|funny|funniest|lol|prank|oops|blunder|mishap|fail goes viral|ai fail|goes viral|went viral|went rogue|memes?|grappig|hilarisch|lachen|bizar|absurd|ridiculous)\b", re.I)

def claude_kiest(kandidaten, aantal):
    """Filter B: Claude Haiku kiest de koppen die echt luchtig of grappig zijn. Geeft None zonder sleutel of bij een fout."""
    sleutel = os.environ.get("ANTHROPIC_API_KEY")
    if not sleutel or not kandidaten:
        return None
    lijst = "\n".join(f"{i}. {k['titel']} ({k['bron']})" for i, k in enumerate(kandidaten))
    vraag = ("Hieronder staan nieuwskoppen over AI. Kies er maximaal " + str(aantal) + " die echt grappig, luchtig of "
             "opmerkelijk-om-te-lachen zijn: AI die iets geks doet, een blunder, een viral moment, een absurde toepassing. "
             "Sla alles over wat serieus, politiek, tragisch, zakelijk, wetenschappelijk of een opiniestuk is, ook als er "
             "'bizarre' of 'weird' in staat. Kies liever minder dan een twijfelgeval. Antwoord alleen met JSON: {\"kies\": [nummers]}, "
             "grappigste eerst.\n\n" + lijst)
    body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 3000, "messages": [{"role": "user", "content": vraag}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": sleutel, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ruw = r.read().decode(); tekst = "".join(b.get("text", "") for b in json.loads(ruw)["content"] if b.get("type") == "text")
        if not re.search(r"\{.*\}", tekst, re.S): print("Claude antwoordde:", tekst[:300], file=sys.stderr)
        nummers = json.loads(re.search(r"\{.*\}", tekst, re.S).group(0))["kies"]
        gekozen = [kandidaten[n] for n in nummers if isinstance(n, int) and 0 <= n < len(kandidaten)]
        print("grappig: Claude koos", len(gekozen), "van", len(kandidaten))
        return gekozen[:aantal]
    except Exception as e:
        print("Claude-keuze mislukt, terugval op filter:", e, file=sys.stderr)
        return None

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
        if c.get("grappig"):
            verzameld = [x for x in verzameld if not SERIEUS.search(x["titel"])]
        gekozen, max_aantal = [], (40 if c.get("grappig") else PER_CATEGORIE)
        for x in verzameld:
            sleutel = x["titel"].lower()[:70]
            if sleutel in gezien or not x["link"].startswith("https://") or x["titel"].count("#") >= 2 or len(x["titel"]) < 25:
                continue
            w = woorden(x["titel"])
            if any(len(w & woorden(g["titel"])) >= 2 for g in gekozen):
                continue  # te veel hetzelfde verhaal
            if sum(1 for g in gekozen if g["bron"] == x["bron"]) >= 2:
                continue
            gekozen.append(x)
            if len(gekozen) == max_aantal:
                break
        if c.get("grappig"):
            keuze = claude_kiest(gekozen, PER_CATEGORIE)
            if keuze is None:
                keuze = [x for x in gekozen if GRAP.search(x["titel"])][:PER_CATEGORIE]
            gekozen = keuze
        for x in gekozen:
            gezien.add(x["titel"].lower()[:70])
        data["categorieen"].append({"id": c["id"], "naam": c["naam"], "kort": c["kort"], "berichten": gekozen})
        print(c["id"], len(gekozen))
    Path(uit).write_text(json.dumps(data, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ai-nieuws.json")
