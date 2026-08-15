"""
Diagnostic : teste plusieurs noms de champ de tri (sorts) pour trouver
lequel permet de trier les résultats de recherche par prix croissant.

Usage :
    python -m src.debug_floor_search "Pedri"
"""

import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in

load_dotenv()

CANDIDATE_SORT_FIELDS = [
    "price",
    "salePrice",
    "sale.price",
    "amount",
    "currentPrice",
    "minPrice",
]

QUERY_TEMPLATE = """
query TestSort($query: String!, $field: String!) {
  searchCards(query: $query, onSaleOnly: true, pageSize: 10, sorts: [{field: $field, direction: ASC}]) {
    hits {
      rarity
      season
      sale { price }
    }
  }
}
"""


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "Pedri"

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    for field in CANDIDATE_SORT_FIELDS:
        print(f"\n🔍 Test du tri par '{field}'...")
        try:
            data = client.execute(QUERY_TEMPLATE, {"query": name, "field": field})
            hits = data["searchCards"]["hits"]
            prices = [h["sale"]["price"] for h in hits if h.get("sale")]
            print(f"   Prix obtenus (devrait être croissant) : {prices}")
        except Exception as e:
            print(f"   ❌ Erreur : {e}")


if __name__ == "__main__":
    main()