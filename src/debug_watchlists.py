"""
Diagnostic : liste vos watchlists Sorare et le nombre de joueurs dans
chacune, sans calculer de floor price (rapide). À lancer une première fois
avant `python -m src.main` pour vérifier que la récupération fonctionne
comme prévu sur votre compte.

Usage :
    python -m src.debug_watchlists
    python -m src.debug_watchlists --show-players
"""

import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.watchlist import fetch_watchlist_players, fetch_watchlists

load_dotenv()


def main():
    show_players = "--show-players" in sys.argv

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    watchlists = fetch_watchlists(client)
    if not watchlists:
        print(
            "Aucune watchlist trouvée (ni créée, ni suivie) pour ce compte. "
            "Vérifiez que vous en avez bien sur sorare.com, ou que vous êtes "
            "connecté avec le bon compte."
        )
        return

    print(f"{len(watchlists)} watchlist(s) trouvée(s) :\n")
    for wl in watchlists:
        print(
            f"- {wl.get('title')!r} (slug={wl.get('slug')}, "
            f"id={wl.get('id')}, {wl.get('totalPlayersCount')} joueur(s) au total)"
        )
        if show_players:
            players = fetch_watchlist_players(client, wl["id"])
            print(f"  -> {len(players)} joueur(s) récupéré(s) :")
            for p in players:
                print(
                    f"     - {p['player_name']} ({p['position']}) "
                    f"{p['club']} / {p['league']} [slug={p['player_slug']}]"
                )
            if len(players) != wl.get("totalPlayersCount"):
                print(
                    f"  ⚠️  Écart entre totalPlayersCount ({wl.get('totalPlayersCount')}) "
                    f"et le nombre réellement paginé ({len(players)}) — "
                    "possible souci de pagination à investiguer."
                )
        print()


if __name__ == "__main__":
    main()
