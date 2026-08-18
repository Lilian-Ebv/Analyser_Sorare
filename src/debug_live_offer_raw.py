"""
Diagnostic : affiche le JSON brut de `liveSingleSaleOffer` pour les
annonces d'un joueur dont l'offre "existe" (`liveSingleSaleOffer` non nul)
mais dont `_resolve_confirmed_price` n'a pas réussi à en extraire un
montant (cas "❌ PÉRIMÉ" avec `offre_existe=True` dans debug_floor_search).

Objectif : voir exactement ce que contiennent `eurCents` et `wei` dans ces
cas, pour savoir si c'est une vraie offre au montant mal formé (bug à
corriger) ou une offre effectivement vide/périmée (comportement actuel
correct).

Usage :
    python -m src.debug_live_offer_raw "Kosei Tani"
    python -m src.debug_live_offer_raw "Kosei Tani" --max-index-price 20
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "Pedri"

    max_index_price = None
    if "--max-index-price" in sys.argv:
        idx = sys.argv.index("--max-index-price")
        max_index_price = float(sys.argv[idx + 1])

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    rates = fetch_currency_rates(client)
    print(f"Taux de change : {rates}\n")

    data = client.execute(PLAYER_FLOOR_SEARCH, {"query": name})
    hits = data["searchCards"]["hits"]

    shown = 0
    for hit in hits:
        card = hit.get("card") or {}
        offer = card.get("liveSingleSaleOffer")
        if offer is None:
            continue  # pas d'offre du tout, rien à inspecter ici

        index_price = (hit.get("sale") or {}).get("price")
        index_price_eur = index_price / 100 if index_price is not None else None
        if max_index_price is not None and (
            index_price_eur is None or index_price_eur > max_index_price
        ):
            continue

        confirmed = (
            _resolve_confirmed_price(card, index_price_eur, rates)
            if index_price_eur is not None
            else None
        )
        if confirmed is not None:
            continue  # on ne veut que les cas "périmés" (confirmed=None) ici

        shown += 1
        print("=" * 70)
        print(
            f"rarity={hit.get('rarity')} season={hit.get('season')} "
            f"in_season={card.get('inSeasonEligible')} "
            f"index_price={index_price_eur}€ card_slug={hit.get('slug')}"
        )
        print("liveSingleSaleOffer brut :")
        print(json.dumps(offer, indent=2, ensure_ascii=False))
        print()

    if shown == 0:
        print(
            "Aucune offre 'périmée' (existante mais montant non extrait) "
            "trouvée avec ces critères."
        )
    else:
        print(f"\n{shown} offre(s) affichée(s) ci-dessus.")


if __name__ == "__main__":
    main()
