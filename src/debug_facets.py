"""
Script de diagnostic : teste plusieurs noms de facette possibles pour
trouver lequel permet de filtrer les cartes par club/équipe.

Usage :
    python -m src.debug_facets
"""

import os

from dotenv import load_dotenv

from src.auth import sign_in
from src.api_client import SorareClient
from src.queries import SEARCH_CARD_FACET_VALUES

load_dotenv()

# Candidats plausibles à tester (facetQuery="a" = recherche large, pour
# maximiser les chances de matcher un nom de club contenant "a").
CANDIDATE_FIELDS = [
    "rarity",
    "rarities",
    "position",
    "positions",
    "season",
    "seasonStartYears",
    "sport",
    "playerSlug",
    "playerSlugs",
    "teamSlug",
    "teamSlugs",
    "cardEditionName",
    "customCardEditionName",
    "u23Eligible",
    "inSeasonEligible",
    "shirtNumber",
    "serialNumber",
    "team_slugs",
    "player_slugs",
]


def main():
    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    print("\n🔍 Test des noms de facette possibles...\n")

    for field in CANDIDATE_FIELDS:
        try:
            data = client.execute(
                SEARCH_CARD_FACET_VALUES, {"field": field, "facetQuery": ""}
            )
            values = data["searchCardFacetValues"]
            if values:
                print(f"✅ '{field}' fonctionne ! Exemples de valeurs :")
                for v in values:
                    print(f"      - {v['value']} ({v['count']} cartes)")
            else:
                print(f"⚠️  '{field}' : requête OK mais aucune valeur retournée")
        except Exception as e:
            print(f"❌ '{field}' : erreur -> {e}")

    print("\nTerminé. Si aucun champ ne fonctionne, envoyez-moi ce résultat complet.")


if __name__ == "__main__":
    main()