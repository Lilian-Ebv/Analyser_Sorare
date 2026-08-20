"""
Helpers d'affichage partagés entre les pages Streamlit (🏠_Accueil.py et
pages/*.py) : formatage, code couleur, styles de tableau.
"""

import pandas as pd

TREND_UP = "▲"
TREND_DOWN = "▼"
TREND_STABLE = "➖"


def format_countdown(end_dt: pd.Timestamp) -> str:
    """Formate un timestamp en compte à rebours lisible (ex: '1j 2h 3min')."""
    if pd.isna(end_dt):
        return ""
    delta_seconds = int((end_dt - pd.Timestamp.now(tz="UTC")).total_seconds())
    if delta_seconds <= 0:
        return "Terminée"
    days, rem = divmod(delta_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if days > 0 or hours > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}min")
    return "Dans " + " ".join(parts)


def highlight_sealed(row: pd.Series) -> list[str]:
    """Colore toute la ligne en rouge pâle si la carte est dans un coffre."""
    color = "background-color: #ffd6d6" if row.get("sealed") else ""
    return [color] * len(row)


def highlight_u23_player_name(row: pd.Series) -> list[str]:
    """
    Colore uniquement la cellule `player_name` en bleu ciel si le joueur est
    U23 éligible (colonne `u23_eligible`, booléenne). N'affecte aucune autre
    cellule de la ligne — contrairement à `highlight_sealed` qui colore la
    ligne entière, ici seule la colonne du nom est visée.

    Nécessite que `u23_eligible` fasse partie du DataFrame passé à
    `.style.apply(..., axis=1)`, même si elle n'est pas affichée (utiliser
    `column_order` sur `st.dataframe` pour la garder disponible au style
    sans l'afficher comme colonne à part entière).
    """
    color = "background-color: #cdeeff" if row.get("u23_eligible") else ""
    return [color if col_name == "player_name" else "" for col_name in row.index]


def floor_price_trend(row: pd.Series) -> str:
    """
    Compare le floor price actuel au précédent (colonne `floor_price_prev_eur`,
    renseignée par `db.save_cards` à chaque rafraîchissement) et retourne le
    symbole de tendance correspondant. Chaîne vide si l'une des deux valeurs
    manque (première récupération pour cette carte, ou floor price introuvable).
    """
    new = row.get("floor_price_eur")
    old = row.get("floor_price_prev_eur")
    if pd.isna(new) or pd.isna(old):
        return ""
    if new > old:
        return TREND_UP
    if new < old:
        return TREND_DOWN
    return TREND_STABLE


def colorize_trend_column(col: pd.Series) -> list[str]:
    """Style le texte de la colonne tendance : vert (hausse), rouge (baisse), gris (stable)."""
    styles = {
        TREND_UP: "color: #1a7f37; font-weight: bold; text-align: center",
        TREND_DOWN: "color: #cf222e; font-weight: bold; text-align: center",
        TREND_STABLE: "color: #6e7781; font-weight: bold; text-align: center",
    }
    return [styles.get(val, "text-align: center") for val in col]


def colorize_by_sign_column(col: pd.Series) -> list[str]:
    """
    Style le texte d'une colonne numérique : vert si >= 0, rouge si < 0, rien
    si vide. Utile pour un écart (ex: prix de vente demandé - floor price).
    """
    styles = []
    for val in col:
        if pd.isna(val):
            styles.append("")
        elif val >= 0:
            styles.append("color: #1a7f37; font-weight: bold")
        else:
            styles.append("color: #cf222e; font-weight: bold")
    return styles
