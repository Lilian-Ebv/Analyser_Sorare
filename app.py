"""
Application Streamlit : explore et filtre vos cartes Sorare.

Les données viennent de data/sorare.db (SQLite), généré en lançant :
    python -m src.main

Lancement de l'app :
    streamlit run app.py
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src import db
from src.analysis import cards_to_dataframe, eligible_leagues
from src.api_client import SorareClient
from src.auth import SorareAuthError, complete_sign_in, start_sign_in
from src.floor_price import compute_floor_price, fetch_eth_eur_cents, fetch_floor_prices_by_player
from src.main import FETCH_RARITIES, fetch_all_cards
from src.queries import GET_CURRENT_USER, GET_EXCHANGE_RATE, SEARCH_PLAYER_CARDS

load_dotenv()

st.set_page_config(page_title="Sorare Analyzer", layout="wide", page_icon="⚽")


@st.cache_data
def load_data(mtime: float | None) -> pd.DataFrame:
    """
    Charge les cartes depuis SQLite. `mtime` (date de modification du
    fichier .db) fait partie de la clé de cache : si vous relancez
    `python -m src.main` et régénérez la base, le cache est automatiquement
    invalidé au prochain rechargement de la page.
    """
    return db.load_cards()


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


def multiselect_or_all(label: str, options: list[str]) -> list[str]:
    """Multiselect où une sélection vide = 'toutes les valeurs' (pas de filtre)."""
    selected = st.sidebar.multiselect(label, options)
    return selected if selected else options


def highlight_sealed(row: pd.Series) -> list[str]:
    """Colore toute la ligne en rouge pâle si la carte est dans un coffre."""
    color = "background-color: #ffd6d6" if row.get("sealed") else ""
    return [color] * len(row)


def fetch_and_save(jwt_token: str) -> int:
    """Récupère les cartes via l'API et écrase data/cards.csv. Retourne le nombre de cartes."""
    client = SorareClient(jwt_token)
    current_user = client.execute(GET_CURRENT_USER)["currentUser"]
    slug = current_user["slug"]
    card_nodes = fetch_all_cards(client, slug, rarities=FETCH_RARITIES)
    new_df = cards_to_dataframe(card_nodes, my_slug=slug, rarities=None)

    if not new_df.empty:
        players = (
            new_df[["player_name", "player_slug"]]
            .dropna(subset=["player_name"])
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        players = list(players)
        eth_eur_cents = fetch_eth_eur_cents(client)
        floor_data = fetch_floor_prices_by_player(client, players, eth_eur_cents=eth_eur_cents)
        new_df["floor_price_eur"] = new_df.apply(
            lambda row: compute_floor_price(
                row["player_name"],
                row["rarity"],
                row["season"],
                row["in_season"],
                floor_data,
            ),
            axis=1,
        )

    db.save_cards(new_df)
    return len(new_df)


SALE_TYPE_LABELS = {
    "EnglishAuction": "Enchère",
    "SingleSaleOffer": "Vente directe",
    "SingleBuyOffer": "Offre d'achat",
}


def _fetch_limited_hits(client: SorareClient, query: str) -> list[dict]:
    """Interroge searchCards et ne garde que les résultats Limited."""
    data = client.execute(SEARCH_PLAYER_CARDS, {"query": query, "onSaleOnly": True})
    hits = data["searchCards"]["hits"]
    return [h for h in hits if h.get("rarity") == "limited"]


def _pack_teammates(hit: dict) -> list[str]:
    """Noms des coéquipiers d'un pack, uniquement si l'enchère est ouverte."""
    auction = (hit.get("card") or {}).get("latestEnglishAuction") or {}
    if not auction.get("open"):
        return []
    bundled = auction.get("bundledAnyCards") or []
    return [
        (c.get("anyPlayer") or {}).get("displayName")
        for c in bundled
        if (c.get("anyPlayer") or {}).get("displayName")
    ]


def _auction_live_price_eur(auction: dict, eth_eur_cents: float) -> float | None:
    """Convertit le prix live (wei) d'une enchère ouverte en euros."""
    current_price = auction.get("currentPrice")
    currency = auction.get("currency")
    if current_price is None or currency != "WEI":
        return None
    eth_amount = float(current_price) / 1e18
    return eth_amount * (eth_eur_cents / 100)


def _hit_to_row(hit: dict, eth_eur_cents: float) -> dict:
    """Transforme un hit de recherche brut en ligne de tableau."""
    card = hit.get("card") or {}
    player = card.get("anyPlayer") or {}
    sale = hit.get("sale") or {}
    price_cents = sale.get("price")
    sale_type = sale.get("type")
    auction = card.get("latestEnglishAuction") or {}
    pack_note = None
    auction_end = None
    price_eur = None

    if sale_type == "EnglishAuction" and auction.get("open"):
        # Pour une enchère en cours, `sale.price` peut être périmé (prix au
        # moment de l'indexation, avant de nouvelles offres) : on privilégie
        # toujours le prix live de l'enchère elle-même.
        price_eur = _auction_live_price_eur(auction, eth_eur_cents)
        auction_end = auction.get("endDate")
        other_players = _pack_teammates(hit)
        if other_players:
            pack_note = f"Pack de {len(other_players)} : " + ", ".join(other_players)
        if price_eur is None:
            # Repli si la conversion échoue pour une raison inattendue.
            price_eur = price_cents / 100 if price_cents is not None else None

    elif price_cents is not None:
        # Vente à prix fixe (SingleSaleOffer) : sale.price est fiable.
        price_eur = price_cents / 100

    elif auction.get("open"):
        # Pas de `sale` direct (carte secondaire d'un pack) mais une
        # enchère ouverte détectée : on utilise son prix live.
        price_eur = _auction_live_price_eur(auction, eth_eur_cents)
        sale_type = "EnglishAuction"
        auction_end = auction.get("endDate")
        other_players = _pack_teammates(hit)
        if other_players:
            pack_note = f"Pack de {len(other_players)} : " + ", ".join(other_players)

    else:
        sale_type = "Pas de vente active détectée"

    return {
        "player_name": player.get("displayName"),
        "club": (player.get("activeClub") or {}).get("name"),
        "rarity": hit.get("rarity"),
        "season": hit.get("season"),
        "sale_type": SALE_TYPE_LABELS.get(sale_type, sale_type),
        "price_eur": price_eur,
        "auction_end": auction_end,
        "pack": pack_note,
        "card_slug": hit.get("slug"),
    }


def search_player_market(jwt_token: str, query: str) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """
    Cherche les cartes Limited en vente pour un joueur. Si un résultat fait
    partie d'un pack (enchère groupée ouverte), relance automatiquement la
    recherche sur les coéquipiers du pack pour retrouver l'annonce même si
    Sorare l'a indexée sous un autre nom que celui recherché.

    Retourne (DataFrame fusionné, hits bruts, noms ajoutés automatiquement).
    """
    client = SorareClient(jwt_token)

    if "eth_eur_cents" not in st.session_state:
        rate_data = client.execute(GET_EXCHANGE_RATE)
        st.session_state.eth_eur_cents = rate_data["config"]["exchangeRate"]["ethRates"][
            "eurCents"
        ]
    eth_eur_cents = st.session_state.eth_eur_cents

    all_hits = _fetch_limited_hits(client, query)
    seen_slugs = {h.get("slug") for h in all_hits}
    searched_names = {query.strip().lower()}

    teammates = set()
    for hit in all_hits:
        for name in _pack_teammates(hit):
            if name.strip().lower() not in searched_names:
                teammates.add(name)

    extra_searched = []
    for name in teammates:
        if name.strip().lower() in searched_names:
            continue
        searched_names.add(name.strip().lower())
        extra_searched.append(name)
        for hit in _fetch_limited_hits(client, name):
            slug = hit.get("slug")
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                all_hits.append(hit)

    rows = [_hit_to_row(hit, eth_eur_cents) for hit in all_hits]
    # On ne garde que les cartes avec un prix effectivement trouvé.
    rows = [r for r in rows if r["price_eur"] is not None]
    return pd.DataFrame(rows), all_hits, extra_searched


st.title("⚽ Sorare Analyzer")

# --- Rafraîchissement des données depuis la barre latérale --------------
st.sidebar.header("🔄 Données")

if "refresh_state" not in st.session_state:
    st.session_state.refresh_state = "idle"  # "idle" ou "awaiting_otp"
    st.session_state.otp_challenge = None

if st.session_state.refresh_state == "idle":
    if st.sidebar.button("🔄 Rafraîchir les données", use_container_width=True):
        email = os.environ.get("SORARE_EMAIL")
        password = os.environ.get("SORARE_PASSWORD")
        if not email or not password:
            st.sidebar.error("SORARE_EMAIL / SORARE_PASSWORD manquants dans .env")
        else:
            try:
                with st.spinner("Connexion à Sorare..."):
                    token, otp_challenge = start_sign_in(email, password)
                if otp_challenge:
                    st.session_state.refresh_state = "awaiting_otp"
                    st.session_state.otp_challenge = otp_challenge
                    st.rerun()
                else:
                    with st.spinner("Récupération des cartes..."):
                        count = fetch_and_save(token)
                    st.session_state.jwt_token = token
                    st.cache_data.clear()
                    st.sidebar.success(f"✅ {count} cartes récupérées !")
                    st.rerun()
            except SorareAuthError as e:
                st.sidebar.error(f"Échec de connexion : {e}")

elif st.session_state.refresh_state == "awaiting_otp":
    st.sidebar.info("🔐 Entrez votre code 2FA (6 chiffres)")
    otp_code = st.sidebar.text_input("Code 2FA", max_chars=6, key="otp_input")
    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("Valider", use_container_width=True):
        try:
            with st.spinner("Vérification et récupération..."):
                token = complete_sign_in(st.session_state.otp_challenge, otp_code)
                count = fetch_and_save(token)
            st.session_state.jwt_token = token
            st.session_state.refresh_state = "idle"
            st.session_state.otp_challenge = None
            st.cache_data.clear()
            st.sidebar.success(f"✅ {count} cartes récupérées !")
            st.rerun()
        except SorareAuthError as e:
            st.sidebar.error(f"Code invalide : {e}")
    if col_b.button("Annuler", use_container_width=True):
        st.session_state.refresh_state = "idle"
        st.session_state.otp_challenge = None
        st.rerun()

st.sidebar.divider()

# --- Recherche d'un joueur sur le marché --------------------------------
st.sidebar.header("🔎 Recherche marché")
search_query = st.sidebar.text_input("Nom du joueur", placeholder="ex: Mbappé")
club_query = st.sidebar.text_input("Club (optionnel)", placeholder="ex: Gamba Osaka")
if st.sidebar.button("Rechercher", use_container_width=True):
    if not st.session_state.get("jwt_token"):
        st.sidebar.warning("Connectez-vous d'abord via 🔄 Rafraîchir les données.")
    elif not search_query and not club_query:
        st.sidebar.warning("Entrez un nom de joueur et/ou un club.")
    else:
        token = st.session_state.jwt_token
        all_extra = []
        all_raw = []

        if search_query:
            df1, raw1, extra1 = search_player_market(token, search_query)
            all_extra += extra1
            all_raw += raw1
        else:
            df1 = pd.DataFrame()

        if club_query:
            df2, raw2, extra2 = search_player_market(token, club_query)
            all_extra += extra2
            all_raw += raw2
        else:
            df2 = pd.DataFrame()

        combined = pd.concat([df1, df2], ignore_index=True)
        if not combined.empty:
            combined = combined.drop_duplicates(subset=["card_slug"])

        st.session_state.market_search_results = combined
        st.session_state.market_search_raw = all_raw
        st.session_state.market_search_query = " / ".join(
            [v for v in [search_query, club_query] if v]
        )
        st.session_state.market_search_extra = list(dict.fromkeys(all_extra))

st.sidebar.divider()

if "market_search_results" in st.session_state:
    st.subheader(f"🔎 Résultats pour \"{st.session_state.market_search_query}\"")
    if st.session_state.get("market_search_extra"):
        st.caption(
            "🔗 Recherche automatiquement étendue aux coéquipiers de pack détectés : "
            + ", ".join(st.session_state.market_search_extra)
        )
    results = st.session_state.market_search_results
    if results.empty:
        st.info("Aucune carte en vente trouvée pour ce joueur actuellement.")
    else:
        available_types = sorted(results["sale_type"].dropna().unique())
        col_a, col_b = st.columns(2)
        show_types = []
        for i, t in enumerate(available_types):
            col = col_a if i % 2 == 0 else col_b
            if col.checkbox(t, value=True, key=f"saletype_{t}"):
                show_types.append(t)

        results = results[results["sale_type"].isin(show_types)]

        if results.empty:
            st.info("Aucun résultat avec les types de vente sélectionnés.")
        else:
            display_results = results.copy()
            display_results["auction_end"] = pd.to_datetime(
                display_results["auction_end"], errors="coerce", utc=True
            ).apply(format_countdown)
            st.dataframe(
                display_results.drop(columns=["card_slug"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "price_eur": st.column_config.NumberColumn("Prix", format="%.2f €"),
                    "sale_type": "Type de vente",
                    "club": "Club",
                    "rarity": "Rareté",
                    "season": "Saison",
                    "auction_end": "Fin d'enchère",
                    "pack": "Pack (si groupé)",
                },
            )
    with st.expander("🐛 Debug : voir les données brutes de l'API"):
        st.json(st.session_state.market_search_raw)
    st.divider()

if not db.DB_FILE.exists():
    st.warning(
        "Aucune donnée trouvée. Lancez d'abord `python -m src.main` dans "
        "votre terminal (avec la connexion Sorare + le 2FA), puis rechargez "
        "cette page."
    )
    st.stop()

df = load_data(db.last_updated())
if df.empty:
    st.warning(
        "La base de données existe mais ne contient aucune carte. "
        "Relancez `python -m src.main`."
    )
    st.stop()

df["next_game_date"] = pd.to_datetime(df["next_game_date"], errors="coerce", utc=True)
df["next_gameweek_deadline"] = pd.to_datetime(df["next_gameweek_deadline"], errors="coerce", utc=True)

# SQLite n'a pas de vrai type booléen : ces colonnes reviennent en 0/1,
# on les reconvertit explicitement.
for bool_col in ["u23_eligible", "sealed", "in_season"]:
    df[bool_col] = df[bool_col].astype(bool)

# --- Filtres (barre latérale) -----------------------------------------
st.sidebar.header("🔍 Filtres")

rarities = sorted(df["rarity"].dropna().unique())
selected_rarities = multiselect_or_all("Rareté", rarities)

positions = sorted(df["position"].dropna().unique())
selected_positions = multiselect_or_all("Poste", positions)

leagues = sorted(df["league"].dropna().unique())
selected_leagues = multiselect_or_all("Championnat", leagues)

# Les clubs proposés dépendent des championnats déjà sélectionnés.
clubs_pool = df[df["league"].isin(selected_leagues)]
clubs = sorted(clubs_pool["club"].dropna().unique())
selected_clubs = multiselect_or_all("Club", clubs)

acquisitions = sorted(df["acquisition_type"].dropna().unique())
selected_acquisitions = multiselect_or_all("Type d'acquisition", acquisitions)

u23_only = st.sidebar.checkbox("U23 éligibles uniquement")
hide_sealed = st.sidebar.checkbox("Masquer les cartes en coffre")
season_filter = st.sidebar.radio(
    "Saison",
    ["Toutes", "In season uniquement", "Off season uniquement"],
    horizontal=False,
)

max_score = float(df["avg_score_l5"].max(skipna=True) or 100)
min_score = st.sidebar.slider("Score moyen minimum (L5)", 0.0, max_score, 0.0)

days_ahead = st.sidebar.slider("Deadline de composition dans les X jours", 1, 21, 7)

# --- Application des filtres -------------------------------------------
filtered = df[
    df["rarity"].isin(selected_rarities)
    & df["position"].isin(selected_positions)
    & df["league"].isin(selected_leagues)
    & df["club"].isin(selected_clubs)
    & df["acquisition_type"].isin(selected_acquisitions)
    & (df["avg_score_l5"].fillna(0) >= min_score)
]
if u23_only:
    filtered = filtered[filtered["u23_eligible"] == True]  # noqa: E712
if hide_sealed:
    filtered = filtered[filtered["sealed"] == False]  # noqa: E712
if season_filter == "In season uniquement":
    filtered = filtered[filtered["in_season"] == True]  # noqa: E712
elif season_filter == "Off season uniquement":
    filtered = filtered[filtered["in_season"] == False]  # noqa: E712

# --- Indicateurs clés ----------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Cartes affichées", len(filtered))
col2.metric("Valeur d'achat totale", f"{filtered['purchase_price_eur'].sum():.2f} €")
col3.metric("Valeur floor totale", f"{filtered['floor_price_eur'].sum():.2f} €")
plus_value = (filtered["floor_price_eur"] - filtered["purchase_price_eur"]).sum()
col4.metric("Plus-value estimée", f"{plus_value:.2f} €")

st.caption(
    "💡 La plus-value ne tient compte que des cartes ayant à la fois un "
    "prix d'achat et un floor price connus (les cartes gagnées/craftées "
    "n'ont pas de prix d'achat, c'est normal)."
)

# --- Tableau détaillé ------------------------------------------------
st.subheader("📋 Détail des cartes")
st.caption("🟥 Les lignes en rouge pâle sont des cartes actuellement dans un coffre (non utilisables en composition).")

main_columns = [
    "player_name",
    "position",
    "club",
    "league",
    "rarity",
    "avg_score_l5",
    "avg_score_l10",
    "avg_score_l40",
    "acquisition_type",
    "purchase_price_eur",
    "purchase_date",
    "floor_price_eur",
    "birth_date",
    "u23_eligible",
    "sealed",
]
main_table = filtered.sort_values("avg_score_l5", ascending=False)[main_columns]
st.dataframe(
    main_table.style.apply(highlight_sealed, axis=1),
    use_container_width=True,
    hide_index=True,
    column_config={
        "league": "Championnat",
        "purchase_price_eur": st.column_config.NumberColumn("Prix d'achat", format="%.2f €"),
        "floor_price_eur": st.column_config.NumberColumn("Floor price", format="%.2f €"),
        "avg_score_l5": st.column_config.NumberColumn("Score moyen (L5)", format="%.1f"),
        "avg_score_l10": st.column_config.NumberColumn("Score moyen (L10)", format="%.1f"),
        "avg_score_l40": st.column_config.NumberColumn("Score moyen (L40)", format="%.1f"),
        "sealed": "En coffre 🔒",
    },
)

# --- Prochaine game week -------------------------------------------
st.subheader(f"🗓 Cartes dont la game week ferme dans les {days_ahead} prochains jours")

now = pd.Timestamp.now(tz="UTC")
cutoff = now + pd.Timedelta(days=days_ahead)
playing_soon = filtered[
    filtered["next_gameweek_deadline"].notna()
    & (filtered["next_gameweek_deadline"] >= now)
    & (filtered["next_gameweek_deadline"] <= cutoff)
    & filtered["next_game_date"].notna()
].sort_values("next_gameweek_deadline")

st.caption(
    "💡 Basé sur la deadline de composition de la prochaine game week "
    "Sorare à laquelle chaque carte est éligible. Seules les cartes dont "
    "le match précis dans cette game week est confirmé par Sorare sont "
    "affichées ici."
)

if playing_soon.empty:
    st.info("Aucune carte de la sélection n'a de deadline dans cette fenêtre.")
else:
    display_df = playing_soon.copy()
    display_df["next_game_date"] = (
        display_df["next_game_date"].dt.tz_convert("Europe/Paris").dt.strftime("%d/%m/%Y %H:%M")
    )
    display_df["next_gameweek_deadline"] = (
        display_df["next_gameweek_deadline"]
        .dt.tz_convert("Europe/Paris")
        .dt.strftime("%d/%m/%Y %H:%M")
    )
    st.dataframe(
        display_df[
            [
                "player_name",
                "position",
                "club",
                "league",
                "next_gameweek_name",
                "next_gameweek_deadline",
                "next_game_matchup",
                "next_game_date",
                "avg_score_l5",
                "avg_score_l10",
                "avg_score_l40",
                "rarity",
                "sealed",
            ]
        ].style.apply(highlight_sealed, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            "league": "Championnat",
            "next_game_date": "Date du match",
            "next_game_matchup": "Match",
            "next_gameweek_name": "Game week Sorare",
            "next_gameweek_deadline": "Deadline composition",
            "avg_score_l5": st.column_config.NumberColumn("Score moyen (L5)", format="%.1f"),
            "avg_score_l10": st.column_config.NumberColumn("Score moyen (L10)", format="%.1f"),
            "avg_score_l40": st.column_config.NumberColumn("Score moyen (L40)", format="%.1f"),
            "sealed": "En coffre 🔒",
        },
    )

# --- Meilleur onze suggéré ------------------------------------------
st.subheader("🏆 Meilleures cartes par poste (dans la sélection filtrée)")

if filtered.empty:
    st.info("Aucune carte ne correspond aux filtres actuels.")
else:
    best = filtered.copy()
    best["eligible_leagues"] = best.apply(eligible_leagues, axis=1)
    for position in best["position"].dropna().unique():
        st.markdown(f"**{position}**")
        top = (
            best[best["position"] == position]
            .sort_values("avg_score_l5", ascending=False)
            .head(3)
        )
        st.dataframe(
            top[
                [
                    "player_name",
                    "club",
                    "league",
                    "rarity",
                    "avg_score_l5",
                    "avg_score_l10",
                    "avg_score_l40",
                    "eligible_leagues",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "league": "Championnat",
                "avg_score_l5": st.column_config.NumberColumn("Score moyen (L5)", format="%.1f"),
                "avg_score_l10": st.column_config.NumberColumn("Score moyen (L10)", format="%.1f"),
                "avg_score_l40": st.column_config.NumberColumn("Score moyen (L40)", format="%.1f"),
            },
        )

# --- À venir -------------------------------------------------------------
with st.expander("🔜 Prochainement"):
    st.markdown(
        "- Suggestion de composition optimale selon les compétitions "
        "disponibles\n"
        "- Alertes sur les cartes avec une forte plus-value potentielle"
    )