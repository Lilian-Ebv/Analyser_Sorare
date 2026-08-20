"""
Chargement et préparation des données de cartes, partagés entre app.py et
les pages additionnelles (pages/*.py) de l'app Streamlit.
"""

import pandas as pd
import streamlit as st

from src import db


@st.cache_data
def load_cards(mtime: float | None) -> pd.DataFrame:
    """
    Charge les cartes depuis SQLite et applique les conversions de types
    communes à toutes les pages. `mtime` (date de modification du fichier
    .db, voir `db.last_updated()`) fait partie de la clé de cache : si vous
    relancez `python -m src.main` (ou le bouton 🔄 de l'app), le cache est
    automatiquement invalidé au prochain rechargement de page.
    """
    df = db.load_cards()
    if df.empty:
        return df

    df["next_game_date"] = pd.to_datetime(df["next_game_date"], errors="coerce", utc=True)
    df["next_gameweek_deadline"] = pd.to_datetime(
        df["next_gameweek_deadline"], errors="coerce", utc=True
    )

    # SQLite n'a pas de vrai type booléen : ces colonnes reviennent en 0/1,
    # on les reconvertit explicitement.
    for bool_col in ["u23_eligible", "sealed", "in_season"]:
        df[bool_col] = df[bool_col].astype(bool)

    # Bases créées avant l'ajout d'une fonctionnalité récente : la colonne
    # peut être absente lors du tout premier chargement après mise à jour.
    if "floor_price_prev_eur" not in df.columns:
        df["floor_price_prev_eur"] = pd.NA
    if "sale_price_eur" not in df.columns:
        df["sale_price_eur"] = pd.NA
    if "sale_type" not in df.columns:
        df["sale_type"] = None
    if "sale_end_date" not in df.columns:
        df["sale_end_date"] = None

    return df


@st.cache_data
def load_watchlist_players(mtime: float | None) -> pd.DataFrame:
    """
    Charge les joueurs de watchlist depuis SQLite. Même logique de cache que
    `load_cards` : `mtime` (voir `db.last_updated()`, même fichier .db que
    les cartes) invalide le cache à chaque rafraîchissement.
    """
    df = db.load_watchlist_players()
    if df.empty:
        return df

    if "floor_price_prev_eur" not in df.columns:
        df["floor_price_prev_eur"] = pd.NA

    return df
