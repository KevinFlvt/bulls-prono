#!/usr/bin/env python3
"""
Bilan des paris simulés sur les Bulls : statistiques + graphiques (data/bilan.png).

Usage :
    python summary.py
    python summary.py --playoffs-from 2027-04-18     # sépare saison régulière / playoffs
"""
import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "bets.csv")
PNG_PATH = os.path.join(HERE, "data", "bilan.png")


def longest_streak(flags):
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def report(title, df):
    print(f"\n=== {title} ===")
    if df.empty:
        print("Aucun pari réglé.")
        return
    n = len(df)
    wins = int((df["result"] == "V").sum())
    staked = df["stake"].sum()
    net = df["profit"].sum()
    won = df["result"] == "V"
    print(f"Paris réglés          : {n}")
    print(f"Victoires / défaites  : {wins} / {n - wins}  ({wins / n:.1%} de réussite)")
    print(f"Mise totale           : {staked:.2f} EUR")
    print(f"Gain / perte net      : {net:+.2f} EUR")
    print(f"ROI                   : {net / staked:+.1%}")
    print(f"Cote moyenne          : {df['bulls_odds'].mean():.2f}")
    print(f"Réussite nécessaire   : {(1 / df['bulls_odds']).mean():.1%} (seuil de rentabilité moyen)")
    print(f"Meilleure série V     : {longest_streak(won)}")
    print(f"Pire série D          : {longest_streak(~won)}")
    for venue, sub in df.groupby("venue"):
        print(f"  {venue:<10} : {len(sub)} paris, {sub['profit'].sum():+.2f} EUR")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--playoffs-from", help="date (AAAA-MM-JJ) du premier match de playoffs")
    args = parser.parse_args()

    if not os.path.exists(CSV_PATH):
        sys.exit("data/bets.csv introuvable : lancez d'abord le suivi (ou faites un git pull).")

    df = pd.read_csv(CSV_PATH)
    skipped = df[df["status"].isin(["no_odds", "unresolved"])]
    pending = df[df["status"] == "pending"]
    df = df[df["status"] == "settled"].copy()
    if df.empty:
        print("Aucun pari réglé pour l'instant.")
        return

    df["date"] = pd.to_datetime(df["commence_utc"], utc=True).dt.tz_convert("Europe/Paris")
    df = df.sort_values("date").reset_index(drop=True)
    df["cumul"] = df["profit"].cumsum()

    report("Bilan global", df)
    if args.playoffs_from:
        limit = pd.Timestamp(args.playoffs_from, tz="Europe/Paris")
        report("Saison régulière", df[df["date"] < limit])
        report("Playoffs", df[df["date"] >= limit])
    if len(pending):
        print(f"\n{len(pending)} pari(s) en attente de résultat.")
    if len(skipped):
        print(f"{len(skipped)} match(s) ignoré(s) (pas de cote ou score introuvable) : voir data/bets.csv.")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.step(df["date"], df["cumul"], where="post", color="#ce1141", linewidth=2)
    ax1.axhline(0, color="grey", linewidth=0.8)
    ax1.set_title("Gains / pertes cumulés (mise de 5 EUR sur chaque victoire des Bulls)")
    ax1.set_ylabel("EUR")
    ax1.grid(alpha=0.3)
    colors = ["#2e8b57" if p > 0 else "#c0392b" for p in df["profit"]]
    ax2.bar(df["date"], df["profit"], color=colors, width=1.0)
    ax2.axhline(0, color="grey", linewidth=0.8)
    ax2.set_title("Résultat de chaque pari")
    ax2.set_ylabel("EUR")
    ax2.grid(alpha=0.3)
    if args.playoffs_from:
        for ax in (ax1, ax2):
            ax.axvline(limit, color="black", linestyle="--", linewidth=1)
        ax1.text(limit, ax1.get_ylim()[1], " playoffs", va="top")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=150)
    print(f"\nGraphique enregistré : {PNG_PATH}")


if __name__ == "__main__":
    main()
