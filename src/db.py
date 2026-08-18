"""
Stockage SQLite des cartes (remplace data/cards.csv).

Chaque rafraîchissement (`python -m src.main` ou le bouton de l'app)
écrase entièrement la table `cards` avec les données fraîchement
récupérées — pas de cache avec délai ici, les floor prices sont toujours
recalculés en direct sur l'API à chaque fetch.
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_FILE = Path("data/sorare.db")


def init_db(db_path: Path = DB_FILE) -> None:
    """Crée le fichier de base de données (et son dossier parent) si absent."""
    db_path.parent.mkdir(exist_ok=True)


def save_cards(df: pd.DataFrame, db_path: Path = DB_FILE) -> None:
    """
    Remplace entièrement la table `cards` par le contenu du DataFrame.

    Avant d'écraser les données, on conserve le floor price précédent de
    chaque carte (par `card_slug`) dans une nouvelle colonne
    `floor_price_prev_eur`. Ça permet à l'app d'afficher une tendance
    (hausse / baisse / stable) à chaque rafraîchissement, qu'il vienne de
    `python -m src.main` ou du bouton 🔄 de l'app.
    """
    init_db(db_path)

    # DataFrame totalement vide (aucune colonne, ex: 0 carte récupérée) :
    # rien d'exploitable à écrire, et un DataFrame sans colonnes fait
    # planter to_sql. On laisse la base existante intacte plutôt que de
    # perdre les données du dernier rafraîchissement réussi.
    if df.empty and len(df.columns) == 0:
        print("   ⚠️  Aucune carte à enregistrer, la base existante n'est pas modifiée.")
        return

    with sqlite3.connect(db_path) as conn:
        if "card_slug" in df.columns:
            try:
                previous = pd.read_sql("SELECT card_slug, floor_price_eur FROM cards", conn)
            except pd.errors.DatabaseError:
                previous = pd.DataFrame(columns=["card_slug", "floor_price_eur"])

            previous = previous.rename(columns={"floor_price_eur": "floor_price_prev_eur"})
            df = df.drop(columns=["floor_price_prev_eur"], errors="ignore").merge(
                previous, on="card_slug", how="left"
            )

        df.to_sql("cards", conn, if_exists="replace", index=False)


def load_cards(db_path: Path = DB_FILE) -> pd.DataFrame:
    """Charge la table `cards` dans un DataFrame. DataFrame vide si absente."""
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql("SELECT * FROM cards", conn)
        except pd.errors.DatabaseError:
            return pd.DataFrame()


def last_updated(db_path: Path = DB_FILE) -> float | None:
    """Timestamp de dernière modification du fichier de base (pour le cache Streamlit)."""
    if not db_path.exists():
        return None
    return db_path.stat().st_mtime