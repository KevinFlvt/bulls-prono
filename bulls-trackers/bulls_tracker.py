#!/usr/bin/env python3
"""
Suivi des cotes Betclic des Chicago Bulls (NBA) + simulation d'une mise de 5 EUR sur leur victoire.

Le script est conçu pour être lancé souvent (toutes les 30 minutes par GitHub Actions).
À chaque passage il fait deux choses, sans jamais dupliquer ce qui est déjà fait :

  1. CAPTURE : dès qu'un match des Bulls commence dans moins de 2 h, il enregistre
     la cote Betclic "vainqueur du match" (une seule fois par match).
  2. RÈGLEMENT : pour chaque pari en attente dont le match doit être terminé,
     il récupère le score, détermine victoire/défaite et calcule le gain ou la perte.

Les données sont stockées dans data/bets.csv. Aucune dépendance externe (bibliothèque standard).
Clé API attendue dans la variable d'environnement ODDS_API_KEY (The Odds API).
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

API_KEY = os.environ.get("ODDS_API_KEY", "").strip()
BASE_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"
TEAM = "Chicago Bulls"
BOOKMAKER = "betclic_fr"
STAKE = 5.0  # mise simulée, en euros

CAPTURE_WINDOW = timedelta(hours=2)          # on enregistre la cote 2 h avant le coup d'envoi
SETTLE_AFTER = timedelta(hours=2, minutes=30)  # on cherche le score à partir de ce délai après le coup d'envoi
UNRESOLVED_AFTER = timedelta(days=3)         # au-delà, l'API ne renvoie plus le score (match reporté ?)

PARIS = ZoneInfo("Europe/Paris")
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bets.csv")
FIELDS = [
    "event_id", "commence_utc", "date_paris", "venue", "opponent",
    "odds_captured_utc", "bulls_odds", "opponent_odds",
    "status", "bulls_score", "opponent_score", "result",
    "stake", "profit", "cumulative_profit",
]
# status : pending (en attente du résultat) | settled (réglé) | no_odds (pas de cote Betclic
# avant le match) | unresolved (score introuvable, à vérifier à la main)


# ---------------------------------------------------------------- utilitaires

def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fmt_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_paris(dt):
    return dt.astimezone(PARIS).strftime("%Y-%m-%d %H:%M")


def api_get(path, **params):
    params["apiKey"] = API_KEY
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "bulls-tracker"})
    with urllib.request.urlopen(request, timeout=30) as response:
        remaining = response.headers.get("x-requests-remaining")
        data = json.load(response)
    print(f"[api] {path} -> crédits restants : {remaining}")
    return data


def load_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_rows(rows):
    rows.sort(key=lambda r: r["commence_utc"])
    cumulative = 0.0
    for row in rows:
        if row["profit"] != "":
            cumulative += float(row["profit"])
            row["cumulative_profit"] = f"{cumulative:.2f}"
        else:
            row["cumulative_profit"] = ""
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def new_row(event, start, status):
    home = event["home_team"] == TEAM
    return {
        "event_id": event["id"],
        "commence_utc": fmt_utc(start),
        "date_paris": fmt_paris(start),
        "venue": "Domicile" if home else "Extérieur",
        "opponent": event["away_team"] if home else event["home_team"],
        "odds_captured_utc": "", "bulls_odds": "", "opponent_odds": "",
        "status": status,
        "bulls_score": "", "opponent_score": "", "result": "",
        "stake": "", "profit": "", "cumulative_profit": "",
    }


def extract_odds(event_odds):
    """Renvoie (cote Bulls, cote adversaire) chez Betclic, ou None si indisponible."""
    for bookmaker in event_odds.get("bookmakers", []):
        if bookmaker.get("key") != BOOKMAKER:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            prices = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            if TEAM in prices and len(prices) == 2:
                other = next(v for k, v in prices.items() if k != TEAM)
                return float(prices[TEAM]), float(other)
    return None


# ---------------------------------------------------------------- étape 1 : capture

def capture_odds(rows, now):
    known = {r["event_id"]: r for r in rows}
    # La liste des événements ne consomme aucun crédit.
    events = [e for e in api_get("/events", dateFormat="iso")
              if TEAM in (e["home_team"], e["away_team"])]

    to_fetch = []
    for event in events:
        start = parse_time(event["commence_time"])
        row = known.get(event["id"])
        if row:
            # Match déjà suivi : on répercute un éventuel changement d'horaire.
            if row["status"] == "pending" and row["commence_utc"] != fmt_utc(start):
                row["commence_utc"] = fmt_utc(start)
                row["date_paris"] = fmt_paris(start)
                print(f"[info] horaire modifié pour {row['opponent']} -> {row['date_paris']}")
            continue
        if now >= start:
            # Le match a commencé sans qu'on ait capturé de cote : on le note, sans pari.
            rows.append(new_row(event, start, "no_odds"))
            print(f"[warn] match déjà commencé sans cote enregistrée : {event['id']}")
        elif now >= start - CAPTURE_WINDOW:
            to_fetch.append((event, start))

    if not to_fetch:
        print("Aucun nouveau match des Bulls dans les 2 prochaines heures.")
        return

    # 1 crédit pour tous les matchs demandés (un seul bookmaker, un seul marché).
    odds = api_get(
        "/odds", regions="eu", bookmakers=BOOKMAKER, markets="h2h",
        oddsFormat="decimal", dateFormat="iso",
        eventIds=",".join(e["id"] for e, _ in to_fetch),
    )
    odds_by_id = {o["id"]: o for o in odds}

    for event, start in to_fetch:
        found = extract_odds(odds_by_id.get(event["id"], {}))
        if not found:
            print(f"[warn] pas de cote Betclic pour l'instant ({event['id']}), nouvel essai au prochain passage")
            continue
        row = new_row(event, start, "pending")
        row["odds_captured_utc"] = fmt_utc(datetime.now(timezone.utc))
        row["bulls_odds"], row["opponent_odds"] = found
        row["stake"] = f"{STAKE:.2f}"
        rows.append(row)
        print(f"[ok] cote enregistrée : Bulls vs {row['opponent']} ({row['date_paris']}) -> {found[0]}")


# ---------------------------------------------------------------- étape 2 : règlement

def settle_bets(rows, now):
    pending = [r for r in rows
               if r["status"] == "pending" and now >= parse_time(r["commence_utc"]) + SETTLE_AFTER]
    if not pending:
        print("Aucun pari à régler.")
        return

    # daysFrom=3 : renvoie aussi les matchs terminés des 3 derniers jours (2 crédits).
    scores = api_get("/scores", daysFrom=3, dateFormat="iso")
    scores_by_id = {s["id"]: s for s in scores}

    for row in pending:
        start = parse_time(row["commence_utc"])
        game = scores_by_id.get(row["event_id"])
        if game and game.get("completed") and game.get("scores"):
            points = {s["name"]: int(s["score"]) for s in game["scores"]}
            bulls = points[TEAM]
            opponent = next(v for k, v in points.items() if k != TEAM)
            won = bulls > opponent
            row["bulls_score"], row["opponent_score"] = bulls, opponent
            row["result"] = "V" if won else "D"
            row["profit"] = f"{STAKE * (float(row['bulls_odds']) - 1):.2f}" if won else f"{-STAKE:.2f}"
            row["status"] = "settled"
            print(f"[ok] réglé : Bulls {bulls}-{opponent} {row['opponent']} -> {row['result']} ({row['profit']} EUR)")
        elif now - start > UNRESOLVED_AFTER:
            row["status"] = "unresolved"
            print(f"[warn] score introuvable pour {row['event_id']} : à vérifier à la main dans le CSV")
        else:
            print(f"Match pas encore terminé : Bulls vs {row['opponent']}")


# ---------------------------------------------------------------- main

def main():
    if not API_KEY:
        sys.exit("Variable d'environnement ODDS_API_KEY manquante.")
    now = datetime.now(timezone.utc)
    rows = load_rows()
    failed = False
    for step in (capture_odds, settle_bets):
        try:
            step(rows, now)
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            failed = True
            print(f"[erreur] {step.__name__} : {exc}", file=sys.stderr)
    save_rows(rows)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
