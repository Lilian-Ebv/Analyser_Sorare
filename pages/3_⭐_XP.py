"""
Page Streamlit : cartes possédées triées par XP restant avant le prochain
niveau (les plus proches d'un level up en premier).

Les données viennent de data/sorare.db, la même base que les autres pages.
Ajoutée automatiquement à la navigation par la convention du dossier
`pages/` de Streamlit.

Pour que cette page ait quelque chose à afficher, rafraîchissez d'abord les
données depuis la page principale (bouton 🔄 ou `python -m src.main`) :
c'est ce rafraîchissement qui récupère `xp`, `grade` et le seuil du niveau
suivant pour chaque carte.

⚠️ Comme le reste de l'app, seules les cartes Limited sont actuellement
récupérées (voir `FETCH_RARITIES` dans src/main.py) : cette page ne peut
donc montrer que vos cartes Limited, même si vous en possédez d'autres
raretés.
"""

import streamlit as st
from dotenv import load_dotenv

from src import db
from src.data import load_cards
from src.ui import highlight_sealed, highlight_u23_player_name

load_dotenv()

st.set_page_config(page_title="Sorare Analyzer — XP", layout="wide", page_icon="⭐")

st.title("⭐ XP avant level up")
st.caption(
    "Vos cartes triées par XP restant avant le prochain niveau (les plus "
    "proches d'un level up en premier), d'après le dernier rafraîchissement "
    "(bouton 🔄 sur la page principale, ou `python -m src.main`)."
)
st.caption(
    "⚠️ Comme le reste de l'application, seules les cartes Limited sont "
    "récupérées pour l'instant — dites-moi si vous voulez que j'élargisse "
    "la récupération aux autres raretés."
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

# Cartes dont le niveau/XP est connu (toujours le cas pour une carte
# fraîchement récupérée ; défensif pour une base pas encore rafraîchie
# depuis l'ajout de cette page).
xp_known = df[df["grade"].notna()].copy()
if xp_known.empty:
    st.info(
        "Aucune carte avec des informations de niveau/XP trouvée. "
        "Rafraîchissez depuis la page principale pour les récupérer."
    )
    st.stop()

xp_known["au_niveau_max"] = xp_known["xp_remaining"].isna()

# --- Indicateurs clés ----------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Cartes suivies", len(xp_known))
col2.metric("Au niveau maximum", int(xp_known["au_niveau_max"].sum()))
proche_du_level_up = xp_known[~xp_known["au_niveau_max"]]
if not proche_du_level_up.empty:
    closest = proche_du_level_up.loc[proche_du_level_up["xp_remaining"].idxmin()]
    col3.metric(
        "La plus proche d'un level up",
        f"{int(closest['xp_remaining'])} XP",
        help=f"{closest['player_name']}",
    )

st.caption(
    "💡 « Au niveau maximum » : plus de palier suivant pour cette carte, "
    "l'XP restant n'est pas applicable (affiché en bas du tableau, pas à 0)."
)
st.caption("🟥 Lignes en rouge pâle = cartes dans un coffre. 🔵 Nom en bleu ciel = joueur U23 éligible.")

# --- Tableau détaillé ------------------------------------------------
xp_columns = [
    "player_name",
    "position",
    "club",
    "rarity",
    "grade",
    "xp",
    "xp_needed_for_next_grade",
    "xp_remaining",
    "sealed",
]
xp_table = xp_known.sort_values(
    "xp_remaining", ascending=True, na_position="last"
)[xp_columns + ["u23_eligible"]]

st.dataframe(
    xp_table.style.apply(highlight_sealed, axis=1).apply(highlight_u23_player_name, axis=1),
    use_container_width=True,
    hide_index=True,
    # `u23_eligible` reste dans le DataFrame pour le style ci-dessus mais
    # n'apparaît pas comme colonne à part.
    column_order=xp_columns,
    column_config={
        "player_name": "Joueur",
        "position": "Poste",
        "club": "Club",
        "rarity": "Rareté",
        "grade": st.column_config.NumberColumn("Niveau actuel"),
        "xp": st.column_config.NumberColumn("XP actuel"),
        "xp_needed_for_next_grade": st.column_config.NumberColumn("XP requis (niveau suivant)"),
        "xp_remaining": st.column_config.NumberColumn("XP restant"),
        "sealed": "En coffre 🔒",
    },
)
