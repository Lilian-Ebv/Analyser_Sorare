"""
Récupération des watchlists Sorare (joueurs suivis, pas forcément possédés)
et calcul de leur floor price Limited in-season, en réutilisant le même
mécanisme que pour vos propres cartes (voir `src/floor_price.py`).
"""

import pandas as pd

from src.api_client import SorareClient
from src.queries import GET_MY_WATCHLISTS, GET_WATCHLIST_PLAYERS


def fetch_watchlists(
    client: SorareClient, sport: str = "FOOTBALL", filter: str = "ALL_WATCHLISTS"
) -> list[dict]:
    """
    Liste les watchlists du compte connecté (id, slug, title, totalPlayersCount).
    `filter="ALL_WATCHLISTS"` inclut vos listes créées ET celles que vous
    suivez (voir GET_MY_WATCHLISTS).
    """
    data = client.execute(GET_MY_WATCHLISTS, {"sport": sport, "filter": filter})
    return (data.get("currentUser") or {}).get("myWatchlists") or []


def fetch_watchlist_players(client: SorareClient, watchlist_id: str) -> list[dict]:
    """
    Récupère tous les joueurs d'une watchlist (pagination automatique, comme
    `main.fetch_all_cards`). Retourne une liste de dicts
    {player_name, player_slug, club, league, position}.
    """
    players = []
    cursor = None

    while True:
        data = client.execute(GET_WATCHLIST_PLAYERS, {"id": watchlist_id, "cursor": cursor})
        watchlist = (data.get("market") or {}).get("watchlist") or {}
        connection = watchlist.get("commonPlayers") or {}

        for node in connection.get("nodes") or []:
            player = node.get("anyPlayer") or {}
            positions = node.get("positions") or []
            players.append(
                {
                    "player_name": player.get("displayName"),
                    "player_slug": player.get("slug"),
                    "club": (player.get("activeClub") or {}).get("name"),
                    "league": ((player.get("activeClub") or {}).get("domesticLeague") or {}).get(
                        "name"
                    ),
                    "position": positions[0] if positions else None,
                }
            )

        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return players


def fetch_all_watched_players(
    client: SorareClient, sport: str = "FOOTBALL", filter: str = "ALL_WATCHLISTS"
) -> pd.DataFrame:
    """
    Récupère tous les joueurs de toutes vos watchlists, dédupliqués par
    `player_slug` (un même joueur peut apparaître dans plusieurs listes) ;
    la colonne `watchlists` liste alors les noms de listes concernées.

    DataFrame vide si aucune watchlist ou aucun joueur suivi.
    """
    watchlists = fetch_watchlists(client, sport=sport, filter=filter)

    rows_by_slug: dict[str, dict] = {}
    for wl in watchlists:
        for player in fetch_watchlist_players(client, wl["id"]):
            slug = player.get("player_slug")
            if not slug:
                continue
            if slug not in rows_by_slug:
                rows_by_slug[slug] = {**player, "watchlists": []}
            rows_by_slug[slug]["watchlists"].append(wl.get("title") or wl.get("slug"))

    rows = []
    for row in rows_by_slug.values():
        row = dict(row)
        row["watchlists"] = ", ".join(sorted(set(row["watchlists"])))
        rows.append(row)

    return pd.DataFrame(rows)


def _strict_limited_in_season_price(player_name: str, floor_data: dict) -> float | None:
    """
    Prix le plus bas parmi les annonces Limited ET in-season UNIQUEMENT pour
    ce joueur — aucun repli sur une autre rareté ou sur du hors-saison.

    Volontairement plus strict que `compute_floor_price` (utilisé pour vos
    propres cartes) : celle-ci a un "dernier repli" qui, faute d'annonce
    in-season, renvoie le prix hors-saison le plus bas de la même rareté.
    Ce comportement est correct pour vos cartes (une carte a une saison
    précise, un prix approximatif vaut mieux que rien), mais ne convient pas
    ici : la demande explicite est "seulement... In season", et un joueur de
    watchlist sans aucune annonce Limited in-season doit donc afficher un
    prix inconnu (None) plutôt qu'un prix hors-saison potentiellement trompeur.
    """
    entries = floor_data.get(player_name, [])
    in_season_limited_prices = [p for (r, _s, p, ise) in entries if r == "limited" and ise]
    return min(in_season_limited_prices) if in_season_limited_prices else None


def compute_watched_floor_prices(df: pd.DataFrame, floor_data: dict) -> pd.DataFrame:
    """
    Ajoute `floor_price_eur` à chaque ligne, en ne retenant QUE le floor
    price Limited in-season (comme demandé : pas les autres raretés, pas
    les cartes hors saison — voir `_strict_limited_in_season_price`).
    """
    df = df.copy()
    if df.empty:
        df["floor_price_eur"] = pd.Series(dtype="float64")
        return df

    df["floor_price_eur"] = df["player_name"].apply(
        lambda name: _strict_limited_in_season_price(name, floor_data)
    )
    return df
