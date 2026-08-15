"""
Diagnostic : teste le champ dédié lowestPriceAnyCard (in-season / off-season)
pour un joueur, via son slug.

Usage :
    python -m src.debug_lowest_price "kosei-tani"
"""

import json
import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.queries import PLAYER_LOWEST_PRICE

load_dotenv()


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "kosei-tani"
    rarity = sys.argv[2] if len(sys.argv) > 2 else "limited"

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    print(f"\n🔍 lowestPriceAnyCard pour '{slug}' (rareté: {rarity})...\n")
    data = client.execute(PLAYER_LOWEST_PRICE, {"slugs": [slug], "rarity": rarity})
    players = data["players"]

    if not players:
        print("Aucun joueur trouvé pour ce slug.")
        return

    player = players[0]
    print("--- In season ---")
    print(json.dumps(player.get("inSeasonCard"), indent=2))
    print("\n--- Off season ---")
    print(json.dumps(player.get("offSeasonCard"), indent=2))

    # Test de conversion wei -> EUR si eurCents est cassé
    for label, card in [("in season", player.get("inSeasonCard")), ("off season", player.get("offSeasonCard"))]:
        if not card:
            continue
        offer = card.get("liveSingleSaleOffer") or {}
        for side_key in ("receiverSide", "senderSide"):
            side = (offer.get(side_key) or {})
            if not side.get("anyCards"):
                wei = (side.get("amounts") or {}).get("wei")
                if wei:
                    print(f"\n💡 {label} : wei trouvé côté argent = {wei}")


if __name__ == "__main__":
    main()