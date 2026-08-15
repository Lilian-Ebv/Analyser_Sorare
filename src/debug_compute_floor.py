"""
Diagnostic bout-en-bout : appelle EXACTEMENT les mêmes fonctions que
main.py (fetch_floor_prices_by_player + compute_floor_price), pour un seul
joueur, afin d'éliminer toute divergence entre le script de debug et le
vrai pipeline.

Usage :
    python -m src.debug_compute_floor "Kosei Tani" "kosei-tani" limited 2026 True
    python -m src.debug_compute_floor "Kosei Tani" "kosei-tani" limited 2024 False
"""

import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.floor_price import compute_floor_price, fetch_eth_eur_cents, fetch_floor_prices_by_player

load_dotenv()


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "Kosei Tani"
    slug = sys.argv[2] if len(sys.argv) > 2 else "kosei-tani"
    rarity = sys.argv[3] if len(sys.argv) > 3 else "limited"
    season = sys.argv[4] if len(sys.argv) > 4 else "2026"
    in_season = sys.argv[5].lower() in ("true", "1", "yes") if len(sys.argv) > 5 else True

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    eth_eur_cents = fetch_eth_eur_cents(client)
    print(f"Taux ETH/EUR (cents) : {eth_eur_cents}")

    floor_data = fetch_floor_prices_by_player(client, [(name, slug)], eth_eur_cents=eth_eur_cents)

    print(f"\nEntrées brutes pour '{name}' :")
    for entry in floor_data.get(name, []):
        print("  ", entry)

    result = compute_floor_price(name, rarity, season, in_season, floor_data)
    print(f"\n💰 Floor price calculé (rarity={rarity}, season={season}, in_season={in_season}) : {result}")


if __name__ == "__main__":
    main()