"""
Page Streamlit : cartes actuellement en vente (vente directe ou enchère
ouverte), avec leur prix demandé comparé au floor price du marché.

Les données viennent de data/sorare.db, la même base que la page
principale. Ce fichier est automatiquement ajouté à la navigation de
l'app par Streamlit (convention du dossier `pages/`) : aucun bouton à
coder, l'entrée "Ventes" apparaît directement dans la barre latérale.

Pour que cette page ait quelque chose à afficher, rafraîchissez d'abord
les données depuis la page principale (bouton 🔄 ou `python -m src.main`) :
c'est ce rafraîchissement qui détecte les ventes actives et calcule
`sale_price_eur`.
"""

import pandas as pd
from dotenv import load_dotenv

import streamlit as st

from src import db
from src.data import load_cards
from src.ui import (
    colorize_by_sign_column,
    colorize_trend_column,
    floor_price_trend,
    format_countdown,
    highlight_u23_player_name,
)

load_dotenv()

st.set_page_config(page_title="Sorare Analyzer — Ventes", layout="wide", page_icon="💰")

st.title("💰 Cartes en vente")
st.caption(
    "Cartes pour lesquelles une vente directe ou une enchère est actuellement "
    "ouverte, d'après le dernier rafraîchissement (bouton 🔄 sur la page "
    "principale, ou `python -m src.main`)."
)

if not db.DB_FILE.exists():
    st.warning(
        "Aucune donnée trouvée. Lancez d'abord `python -m src.main` dans "
        "votre terminal, ou utilisez le bouton 🔄 de la page principale."
    )
    st.stop()

df = load_cards(db.last_updated())
if df.empty:
    st.warning("La base de données existe mais ne contient aucune carte.")
    st.stop()

on_sale = df[df["sale_price_eur"].notna()].copy()

if on_sale.empty:
    st.info(
        "Aucune carte actuellement en vente d'après les dernières données. "
        "Si vous venez de mettre une carte en vente sur Sorare, rafraîchissez "
        "depuis la page principale pour la voir apparaître ici."
    )
    st.stop()

on_sale["floor_price_trend"] = on_sale.apply(floor_price_trend, axis=1)
on_sale["ecart_vs_floor_eur"] = on_sale["sale_price_eur"] - on_sale["floor_price_eur"]
on_sale["sale_end_date"] = pd.to_datetime(
    on_sale["sale_end_date"], errors="coerce", utc=True
).apply(format_countdown)

# --- Indicateurs clés ----------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Cartes en vente", len(on_sale))
col2.metric("Valeur totale demandée", f"{on_sale['sale_price_eur'].sum():.2f} €")
col3.metric(
    "Écart total vs floor",
    f"{on_sale['ecart_vs_floor_eur'].sum(skipna=True):.2f} €",
    help="Somme de (prix demandé - floor price) sur les cartes dont le floor price est connu.",
)

st.caption(
    "💡 « Écart vs floor » = prix demandé - floor price actuel. Positif "
    "(vert) : vous demandez plus que le floor. Négatif (rouge) : votre prix "
    "est en dessous du floor, la carte devrait partir vite."
)

# --- Tableau détaillé ------------------------------------------------
sale_columns = [
    "player_name",
    "position",
    "club",
    "rarity",
    "sale_type",
    "sale_price_eur",
    "floor_price_eur",
    "floor_price_trend",
    "ecart_vs_floor_eur",
    "sale_end_date",
]
sale_table = on_sale.sort_values("sale_price_eur", ascending=False)[
    sale_columns + ["u23_eligible"]
]

st.caption("🔵 Nom en bleu ciel = joueur U23 éligible.")
st.dataframe(
    sale_table.style.apply(colorize_trend_column, subset=["floor_price_trend"])
    .apply(colorize_by_sign_column, subset=["ecart_vs_floor_eur"])
    .apply(highlight_u23_player_name, axis=1),
    use_container_width=True,
    hide_index=True,
    # `u23_eligible` reste dans le DataFrame pour le style ci-dessus mais
    # n'apparaît pas comme colonne à part.
    column_order=sale_columns,
    column_config={
        "player_name": "Joueur",
        "position": "Poste",
        "club": "Club",
        "rarity": "Rareté",
        "sale_type": "Type de vente",
        "sale_price_eur": st.column_config.NumberColumn("Prix demandé", format="%.2f €"),
        "floor_price_eur": st.column_config.NumberColumn("Floor price", format="%.2f €"),
        "floor_price_trend": st.column_config.TextColumn("Tendance floor", width="small"),
        "ecart_vs_floor_eur": st.column_config.NumberColumn("Écart vs floor", format="%.2f €"),
        "sale_end_date": "Fin d'enchère",
    },
)
