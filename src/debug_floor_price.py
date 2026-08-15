"""
Script de diagnostic : affiche les champs prix bruts (publicMinPrices,
lowestPriceCard, lowestPriceCardAnySeason...) pour UNE carte précise parmi
vos cartes, identifiée par un morceau du nom du joueur.

Usage :
    python -m src.debug_floor_price "Pedri"
"""

import json
import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.main import fetch_all_cards
from src.queries import GET_CURRENT_USER

load_dotenv()


def main():
    if len(sys.argv) < 2:
        print("Usage : python -m src.debug_floor_price \"nom du joueur\"")
        return
    name_filter = sys.argv[1].lower()

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    slug = client.execute(GET_CURRENT_USER)["currentUser"]["slug"]

    print("📥 Récupération de vos cartes limited...")
    cards = fetch_all_cards(client, slug, rarities=["limited"])

    matches = [
        c for c in cards if name_filter in c["anyPlayer"]["displayName"].lower()
    ]

    if not matches:
        print(f"Aucune carte trouvée pour '{name_filter}'.")
        return

    for card in matches:
        print(f"\n🔍 {card['anyPlayer']['displayName']} ({card['slug']})")
        print(json.dumps(
            {
                "inSeasonEligible": card.get("inSeasonEligible"),
                "publicMinPrices": card.get("publicMinPrices"),
                "lowestPriceCard": card.get("lowestPriceCard"),
                "lowestPriceCardAnySeason": card.get("lowestPriceCardAnySeason"),
            },
            indent=2,
        ))


if __name__ == "__main__":
    main()