"""
Diagnostic : teste la recherche floor price avec la logique
"existence d'offre" pour un joueur donné.

Usage :
    python -m src.debug_floor_search "Lammens"
"""

import json
import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.floor_price import _resolve_confirmed_price, fetch_currency_rates
from src.queries import PLAYER_FLOOR_SEARCH

load_dotenv()


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "Pedri"

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    rates = fetch_currency_rates(client)

    print(f"\n🔍 Recherche floor price pour '{name}' (triée par prix)...\n")
    data = client.execute(PLAYER_FLOOR_SEARCH, {"query": name})
    hits = data["searchCards"]["hits"]

    for hit in hits[:15]:
        card = hit.get("card") or {}
        player_slug = (card.get("anyPlayer") or {}).get("slug")
        index_price = (hit.get("sale") or {}).get("price")
        index_price_eur = index_price / 100 if index_price is not None else None
        offer_exists = card.get("liveSingleSaleOffer") is not None

        if index_price_eur is None:
            confirmed = None
        else:
            confirmed = _resolve_confirmed_price(card, index_price_eur, rates)

        status = "✅ CONFIRMÉ" if confirmed is not None else "❌ PÉRIMÉ"
        print(
            f"{hit.get('rarity'):12} {hit.get('season')} | "
            f"index={index_price_eur}€  confirmé={confirmed}€  "
            f"in_season={card.get('inSeasonEligible')}  "
            f"offre_existe={offer_exists}  joueur={player_slug}  [{status}]"
        )


if __name__ == "__main__":
    main()