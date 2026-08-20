"""
Page Streamlit : joueurs suivis dans vos watchlists Sorare, avec leur floor
price Limited in-season (colonne principale, comme demandé au départ — pas
les autres raretés, pas les cartes hors saison) et, à titre de comparaison,
leur floor price Limited hors-saison.

Les données viennent de data/sorare.db, la même base que les autres pages.
Ajoutée automatiquement à la navigation par la convention du dossier
`pages/` de Streamlit.

Pour que cette page ait quelque chose à afficher, rafraîchissez d'abord les
données depuis la page principale (bouton 🔄 ou `python -m src.main`) :
c'est ce rafraîchissement qui récupère vos watchlists et calcule le floor
price de chaque joueur suivi.
"""

import streamlit as st
from dotenv import load_dotenv

from src import db
from src.data import load_watchlist_players
from src.ui import colorize_trend_column, floor_price_trend, highlight_u23_player_name

load_dotenv()

st.set_page_config(page_title="Sorare Analyzer — Watchlist", layout="wide", page_icon="👀")

st.title("👀 Watchlist")
st.caption(
    "Floor price Limited de vos joueurs suivis (toutes vos watchlists "
    "Sorare confondues), d'après le dernier rafraîchissement (bouton 🔄 sur "
    "la page principale, ou `python -m src.main`)."
)

if not db.DB_FILE.exists():
    st.warning(
        "Aucune donnée trouvée. Lancez d'abord `python -m src.main` dans "
        "votre terminal, ou utilisez le bouton 🔄 de la page principale."
    )
    st.stop()

df = load_watchlist_players(db.last_updated())
if df.empty:
    st.info(
        "Aucun joueur de watchlist trouvé. Si vous avez des watchlists sur "
        "Sorare, rafraîchissez depuis la page principale pour les récupérer "
        "ici — sinon, créez-en une sur sorare.com."
    )
    st.stop()

df["floor_price_trend"] = df.apply(floor_price_trend, axis=1)

# --- Filtre par watchlist (barre latérale) --------------------------------
# La colonne `watchlists` est une chaîne "Ma liste, Prospects" (un joueur
# peut appartenir à plusieurs listes) : on éclate chaque valeur pour obtenir
# la liste des noms de watchlists uniques proposés au filtre.
all_watchlist_names = sorted(
    {name.strip() for names in df["watchlists"].dropna() for name in names.split(",") if name.strip()}
)
st.sidebar.header("🔍 Filtre")
selected_watchlists = st.sidebar.multiselect(
    "Watchlist",
    all_watchlist_names,
    help="Aucune sélection = toutes les watchlists confondues.",
)
if selected_watchlists:
    selected_set = set(selected_watchlists)
    df = df[
        df["watchlists"]
        .fillna("")
        .apply(lambda names: bool(selected_set & {n.strip() for n in names.split(",")}))
    ]

if df.empty:
    st.info("Aucun joueur suivi dans la/les watchlist(s) sélectionnée(s).")
    st.stop()

# --- Indicateurs clés ----------------------------------------------------
known_price = df["floor_price_eur"].notna()
col1, col2, col3 = st.columns(3)
col1.metric("Joueurs suivis", len(df))
col2.metric("Avec un floor price connu", int(known_price.sum()))
if known_price.any():
    cheapest = df.loc[df["floor_price_eur"].idxmin()]
    col3.metric(
        "Moins cher",
        f"{cheapest['floor_price_eur']:.2f} €",
        help=f"{cheapest['player_name']}",
    )

st.caption(
    "💡 Aucune ligne n'a de floor price (in season ou hors saison) si "
    "aucune vente directe Limited correspondante n'a été trouvée pour ce "
    "joueur au moment du rafraîchissement (peu d'offres sur le marché, ou "
    "joueur pas encore in season)."
)

# --- Tableau détaillé ------------------------------------------------
watchlist_columns = [
    "player_name",
    "position",
    "club",
    "league",
    "floor_price_eur",
    "floor_price_trend",
    "floor_price_off_season_eur",
    "watchlists",
]
# Cartes avec un prix connu d'abord (les plus intéressantes), triées du
# moins cher au plus cher ; celles sans prix connu en bas.
watchlist_table = df.sort_values(
    "floor_price_eur", ascending=True, na_position="last"
)[watchlist_columns + ["u23_eligible"]]

st.caption("🔵 Nom en bleu ciel = joueur U23 éligible.")
st.dataframe(
    watchlist_table.style.apply(colorize_trend_column, subset=["floor_price_trend"]).apply(
        highlight_u23_player_name, axis=1
    ),
    use_container_width=True,
    hide_index=True,
    # `u23_eligible` reste dans le DataFrame pour le style ci-dessus mais
    # n'apparaît pas comme colonne à part.
    column_order=watchlist_columns,
    column_config={
        "player_name": "Joueur",
        "position": "Poste",
        "club": "Club",
        "league": "Championnat",
        "floor_price_eur": st.column_config.NumberColumn(
            "Floor price (Limited, in season)", format="%.2f €"
        ),
        "floor_price_trend": st.column_config.TextColumn("Tendance", width="small"),
        "floor_price_off_season_eur": st.column_config.NumberColumn(
            "Floor price (Limited, off season)", format="%.2f €"
        ),
        "watchlists": "Watchlist(s)",
    },
)
