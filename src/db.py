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
    """Remplace entièrement la table `cards` par le contenu du DataFrame."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
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