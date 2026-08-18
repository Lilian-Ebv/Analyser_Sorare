"""
Point d'entrée : connexion à Sorare, récupération de toutes vos cartes
football, et sauvegarde dans data/sorare.db (SQLite) pour l'application
Streamlit (app.py).

Usage :
    python -m src.main
"""

import os

from dotenv import load_dotenv

from src import db
from src.analysis import cards_to_dataframe, rank_best_lineup
from src.api_client import SorareClient
from src.auth import sign_in
from src.floor_price import compute_floor_price, fetch_eth_eur_cents, fetch_floor_prices_by_player
from src.queries import GET_CURRENT_USER, GET_USER_CARDS

load_dotenv()

# Raretés à récupérer DIRECTEMENT depuis l'API (filtre serveur) : ça réduit
# fortement le temps de récupération, car l'API n'a pas besoin de calculer
# tous les champs coûteux (historique, prix, game weeks...) pour les cartes
# qui ne vous intéressent pas.
# Exemples : ["limited"], ["rare", "super_rare"], ou None pour tout récupérer
# (beaucoup plus lent, mais permet de tout filtrer dynamiquement dans l'app).
FETCH_RARITIES = ["limited"]


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

    # Récupéré avant cards_to_dataframe : nécessaire pour convertir en euros
    # le prix des ventes/enchères actives réglées en wei (sale_price_eur).
    eth_eur_cents = fetch_eth_eur_cents(client)
    df = cards_to_dataframe(card_nodes, my_slug=slug, rarities=None, eth_eur_cents=eth_eur_cents)

    if not df.empty:
        players = (
            df[["player_name", "player_slug"]]
            .dropna(subset=["player_name"])
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        players = list(players)
        print(f"💰 Calcul du floor price pour {len(players)} joueurs...")
        floor_data = fetch_floor_prices_by_player(client, players, eth_eur_cents=eth_eur_cents)
        df["floor_price_eur"] = df.apply(
            lambda row: compute_floor_price(
                row["player_name"],
                row["rarity"],
                row["season"],
                row["in_season"],
                floor_data,
            ),
            axis=1,
        )

    db.save_cards(df)
    print(f"\n💾 {len(df)} cartes enregistrées dans {db.DB_FILE}")
    if not df.empty:
        on_sale_count = df["sale_price_eur"].notna().sum()
        print(f"🏷️  {on_sale_count} carte(s) actuellement en vente détectée(s).")
    print("   → Lancez maintenant : streamlit run app.py")

    if not df.empty:
        print("\n🏆 Meilleures cartes par poste :\n")
        top_cards = rank_best_lineup(df, top_n=5)
        print(top_cards.to_string(index=False))


if __name__ == "__main__":
    main()