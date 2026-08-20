"""
Stockage SQLite des cartes et des watchlists (remplace data/cards.csv).

Chaque rafraîchissement (`python -m src.main` ou le bouton de l'app)
écrase entièrement les tables `cards` et `watchlist_players` avec les
données fraîchement récupérées — pas de cache avec délai ici, les floor
prices sont toujours recalculés en direct sur l'API à chaque fetch.
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_FILE = Path("data/sorare.db")


def init_db(db_path: Path = DB_FILE) -> None:
    """Crée le fichier de base de données (et son dossier parent) si absent."""
    db_path.parent.mkdir(exist_ok=True)


def _save_with_trend(
    df: pd.DataFrame, table_name: str, key_col: str, db_path: Path = DB_FILE
) -> None:
    """
    Remplace entièrement `table_name` par le contenu du DataFrame.

    Avant d'écraser les données, on conserve le `floor_price_eur` précédent
    de chaque ligne (par `key_col`) dans une colonne `floor_price_prev_eur`.
    Ça permet à l'app d'afficher une tendance (hausse / baisse / stable) à
    chaque rafraîchissement. Logique partagée par `save_cards` (key_col=
    "card_slug") et `save_watchlist_players` (key_col="player_slug") —
    `src/ui.py::floor_price_trend` sait lire ces deux colonnes quelle que
    soit la table d'origine.
    """
    init_db(db_path)

    # DataFrame totalement vide (aucune colonne) : rien d'exploitable à
    # écrire, et un DataFrame sans colonnes fait planter to_sql. On laisse
    # la table existante intacte plutôt que de perdre le dernier
    # rafraîchissement réussi.
    if df.empty and len(df.columns) == 0:
        print(f"   ⚠️  Rien à enregistrer dans '{table_name}', la table existante n'est pas modifiée.")
        return

    with sqlite3.connect(db_path) as conn:
        if key_col in df.columns:
            try:
                previous = pd.read_sql(f"SELECT {key_col}, floor_price_eur FROM {table_name}", conn)
            except pd.errors.DatabaseError:
                previous = pd.DataFrame(columns=[key_col, "floor_price_eur"])

            previous = previous.rename(columns={"floor_price_eur": "floor_price_prev_eur"})
            df = df.drop(columns=["floor_price_prev_eur"], errors="ignore").merge(
                previous, on=key_col, how="left"
            )

        df.to_sql(table_name, conn, if_exists="replace", index=False)


def save_cards(df: pd.DataFrame, db_path: Path = DB_FILE) -> None:
    """Remplace la table `cards`, avec suivi de tendance par `card_slug` (voir `_save_with_trend`)."""
    _save_with_trend(df, "cards", "card_slug", db_path)


def load_cards(db_path: Path = DB_FILE) -> pd.DataFrame:
    """Charge la table `cards` dans un DataFrame. DataFrame vide si absente."""
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql("SELECT * FROM cards", conn)
        except pd.errors.DatabaseError:
            return pd.DataFrame()


def save_watchlist_players(df: pd.DataFrame, db_path: Path = DB_FILE) -> None:
    """Remplace la table `watchlist_players`, avec suivi de tendance par `player_slug`."""
    _save_with_trend(df, "watchlist_players", "player_slug", db_path)


def load_watchlist_players(db_path: Path = DB_FILE) -> pd.DataFrame:
    """Charge la table `watchlist_players`. DataFrame vide si absente."""
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql("SELECT * FROM watchlist_players", conn)
        except pd.errors.DatabaseError:
            return pd.DataFrame()


def last_updated(db_path: Path = DB_FILE) -> float | None:
    """Timestamp de dernière modification du fichier de base (pour le cache Streamlit)."""
    if not db_path.exists():
        return None
    return db_path.stat().st_mtime
