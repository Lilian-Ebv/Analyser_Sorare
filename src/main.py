"""
Point d'entrée : connexion à Sorare, récupération de toutes vos cartes
football, et sauvegarde dans data/cards.csv pour l'application Streamlit
(app.py).

Usage :
    python -m src.main
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from src.analysis import cards_to_dataframe, rank_best_lineup
from src.api_client import SorareClient
from src.auth import sign_in
from src.queries import GET_CURRENT_USER, GET_USER_CARDS

load_dotenv()

# Raretés à récupérer DIRECTEMENT depuis l'API (filtre serveur) : ça réduit
# fortement le temps de récupération, car l'API n'a pas besoin de calculer
# tous les champs coûteux (historique, prix, game weeks...) pour les cartes
# qui ne vous intéressent pas.
# Exemples : ["limited"], ["rare", "super_rare"], ou None pour tout récupérer
# (beaucoup plus lent, mais permet de tout filtrer dynamiquement dans l'app).
FETCH_RARITIES = ["limited"]

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "cards.csv"


def fetch_all_cards(client: SorareClient, slug: str, rarities: list[str] | None) -> list[dict]:
    """Récupère toutes les cartes de l'utilisateur, en paginant automatiquement."""
    all_cards = []
    cursor = None

    while True:
        data = client.execute(
            GET_USER_CARDS,
            {"slug": slug, "cursor": cursor, "rarities": rarities},
        )
        cards_page = data["user"]["cards"]
        all_cards.extend(cards_page["nodes"])

        if not cards_page["pageInfo"]["hasNextPage"]:
            break
        cursor = cards_page["pageInfo"]["endCursor"]

    return all_cards


def main():
    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]

    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    # On récupère le slug directement depuis l'API plutôt que de compter sur
    # le .env : le pseudo affiché ("nickname") diffère parfois du slug utilisé
    # en interne par l'API (minuscules, suffixes numériques, etc.)
    current_user = client.execute(GET_CURRENT_USER)["currentUser"]
    slug = current_user["slug"]
    print(f"ℹ️  Slug utilisé pour les requêtes : {slug}")

    print(f"📥 Récupération de vos cartes ({FETCH_RARITIES or 'toutes raretés'})...")
    card_nodes = fetch_all_cards(client, slug, rarities=FETCH_RARITIES)
    print(f"→ {len(card_nodes)} cartes récupérées.")

    df = cards_to_dataframe(card_nodes, my_slug=slug, rarities=None)

    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_FILE, index=False)
    print(f"\n💾 {len(df)} cartes exportées dans {DATA_FILE}")
    print("   → Lancez maintenant : streamlit run app.py")

    if not df.empty:
        print("\n🏆 Meilleures cartes par poste :\n")
        top_cards = rank_best_lineup(df, top_n=5)
        print(top_cards.to_string(index=False))


if __name__ == "__main__":
    main()