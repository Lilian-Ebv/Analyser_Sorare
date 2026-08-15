"""
Calcule un floor price fiable pour chaque joueur en réutilisant le même
mécanisme que la recherche marché de l'app (searchCards + sale.price),
qui s'est montré plus fiable que les champs lowestPriceCard/
lowestPriceCardAnySeason de l'API (montants souvent manquants).

Un appel API est fait par joueur UNIQUE (pas par carte), pour limiter le
nombre de requêtes.
"""

import time

from src.api_client import SorareClient
from src.queries import PLAYER_FLOOR_SEARCH


def fetch_floor_prices_by_player(
    client: SorareClient,
    players: list[tuple[str, str]],
    delay_seconds: float = 0.2,
) -> dict[str, list[tuple[str, str, float]]]:
    """
    Pour chaque joueur (nom affiché, slug), retourne la liste des
    (rareté, saison, prix en EUR) de ses cartes en vente à prix connu.

    `players` est une liste de tuples (player_name, player_slug) : le nom
    sert de terme de recherche (texte libre), le slug sert à vérifier que
    chaque résultat correspond bien au bon joueur et pas à un homonyme
    (la recherche par nom seul peut être ambiguë).

    Clé du dict retourné : player_name (tel que fourni).
    """
    results: dict[str, list[tuple[str, str, float]]] = {}
    error_count = 0

    for i, (name, expected_slug) in enumerate(players):
        try:
            data = client.execute(PLAYER_FLOOR_SEARCH, {"query": name})
        except Exception as e:
            error_count += 1
            if error_count <= 3:
                print(f"   ⚠️  Erreur floor price pour '{name}' : {e}")
            results[name] = []
            continue

        entries = []
        for hit in data["searchCards"]["hits"]:
            hit_slug = ((hit.get("card") or {}).get("anyPlayer") or {}).get("slug")
            if expected_slug and hit_slug != expected_slug:
                # Homonyme ou joueur différent : on ignore ce résultat.
                continue
            price_cents = (hit.get("sale") or {}).get("price")
            if price_cents is not None:
                entries.append((hit.get("rarity"), hit.get("season"), price_cents / 100))
        results[name] = entries

        if delay_seconds:
            time.sleep(delay_seconds)

        if (i + 1) % 50 == 0:
            print(f"   ... {i + 1}/{len(players)} joueurs traités")

    if error_count:
        print(f"   ⚠️  {error_count}/{len(players)} recherches ont échoué.")

    return results


def compute_floor_price(
    player_name: str,
    rarity: str,
    season: str,
    in_season: bool,
    floor_data: dict[str, list[tuple[str, str, float]]],
) -> float | None:
    """
    Détermine le floor price d'une carte à partir des résultats de
    `fetch_floor_prices_by_player`.

    - Carte "in season" : priorité au prix le plus bas de la MÊME saison ;
      repli toutes saisons si aucune carte de cette saison n'est en vente.
    - Carte "off season" : toutes les éditions font partie du même pool de
      marché, donc on prend directement le prix le plus bas toutes saisons
      confondues.
    """
    entries = floor_data.get(player_name, [])
    same_rarity = [(s, p) for (r, s, p) in entries if r == rarity]
    if not same_rarity:
        return None

    any_season_price = min(p for _, p in same_rarity)

    if not in_season:
        return any_season_price

    same_season_prices = [p for s, p in same_rarity if str(s) == str(season)]
    if same_season_prices:
        return min(same_season_prices)

    return any_season_price