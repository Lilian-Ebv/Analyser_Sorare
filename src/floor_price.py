"""
Calcule un floor price fiable pour chaque joueur en réutilisant le même
mécanisme que la recherche marché de l'app (searchCards, trié par prix
croissant).

Constat empirique (après plusieurs itérations) :
- `amounts.eurCents` de `liveSingleSaleOffer` est souvent cassé (null/0)
  même pour une offre bien réelle.
- `amounts.wei` (même objet MonetaryAmount) s'est montré fiable dans ce
  cas : on l'utilise en repli, converti via le taux ETH/EUR live.
- Certains managers listent leurs cartes en USD ou en GBP plutôt qu'en EUR
  ou en ETH : dans ce cas, `eurCents` ET `wei` sont TOUS LES DEUX vides,
  et seuls `usdCents`/`gbpCents` (avec `referenceCurrency` correspondant)
  portent le vrai montant. Confirmé empiriquement (cartes Kosei Tani listées
  à 28,00 $ et 8,00 £ notamment) : sans gérer ces devises, on écartait à
  tort des ventes directes bien réelles, moins chères, du calcul du floor
  price.
- Faire confiance à l'index de recherche (`sale.price`) dès qu'une offre
  "existe" (sans pouvoir en lire le montant) laissait passer des prix non
  représentatifs : on ne garde donc QUE les candidats dont on a pu extraire
  un vrai montant (eurCents, wei, usdCents ou gbpCents), rien d'autre.

Un appel API est fait par joueur UNIQUE (pas par carte), pour limiter le
nombre de requêtes.
"""

import time

from src.api_client import SorareClient
from src.queries import GET_EXCHANGE_RATE, PLAYER_FLOOR_SEARCH

# Devises gérées pour l'instant (voir amount_to_eur). LAMPORT (Solana) existe
# côté Sorare mais son format exact n'a pas encore été observé sur une vraie
# offre : on préfère log un avertissement explicite plutôt que de deviner une
# conversion non vérifiée sur de l'argent réel.
_UNHANDLED_CURRENCIES_WARNED: set[str] = set()


def fetch_currency_rates(client: SorareClient) -> dict:
    """
    Récupère les taux de change live nécessaires pour convertir un montant
    en EUR, quelle que soit sa devise d'origine (ETH/wei, USD, GBP).

    Sorare expose la valeur de 1 ETH dans plusieurs devises au même instant
    (`ethRates`), ce qui permet de dériver des taux croisés USD->EUR et
    GBP->EUR sans requête supplémentaire : si 1 ETH = 1642,32 € = 1780,50 $,
    alors 1 $ = 1642,32 / 1780,50 €.

    Retourne un dict {"eth_eur_cents", "usd_eur_rate", "gbp_eur_rate"} ; une
    clé vaut None si le taux correspondant n'a pas pu être calculé (auquel
    cas les montants dans cette devise ne pourront pas être convertis).
    """
    try:
        data = client.execute(GET_EXCHANGE_RATE)
        eth_rates = data["config"]["exchangeRate"]["ethRates"]
    except Exception as e:
        print(f"   ⚠️  Impossible de récupérer les taux de change : {e}")
        return {"eth_eur_cents": None, "usd_eur_rate": None, "gbp_eur_rate": None}

    eur_cents = eth_rates.get("eurCents")
    usd_cents = eth_rates.get("usdCents")
    gbp_cents = eth_rates.get("gbpCents")

    return {
        "eth_eur_cents": eur_cents,
        "usd_eur_rate": (eur_cents / usd_cents) if eur_cents and usd_cents else None,
        "gbp_eur_rate": (eur_cents / gbp_cents) if eur_cents and gbp_cents else None,
    }


def amount_to_eur(amounts: dict | None, rates: dict) -> float | None:
    """
    Convertit un `MonetaryAmount` (eurCents/wei/usdCents/gbpCents) en euros,
    en cascade sur le premier champ exploitable. `rates` est le dict retourné
    par `fetch_currency_rates`.

    Partagé entre `floor_price.py` (recherche marché) et `analysis.py`
    (ventes actives de vos propres cartes) : même bug, même correctif.
    """
    if not amounts:
        return None

    eur_cents = amounts.get("eurCents")
    if eur_cents:
        return eur_cents / 100

    wei = amounts.get("wei")
    eth_eur_cents = rates.get("eth_eur_cents")
    if wei and wei != "0" and eth_eur_cents:
        return (float(wei) / 1e18) * (eth_eur_cents / 100)

    usd_cents = amounts.get("usdCents")
    usd_eur_rate = rates.get("usd_eur_rate")
    if usd_cents and usd_eur_rate:
        return (usd_cents / 100) * usd_eur_rate

    gbp_cents = amounts.get("gbpCents")
    gbp_eur_rate = rates.get("gbp_eur_rate")
    if gbp_cents and gbp_eur_rate:
        return (gbp_cents / 100) * gbp_eur_rate

    reference_currency = amounts.get("referenceCurrency")
    if reference_currency and reference_currency not in ("EUR", "WEI", "USD", "GBP"):
        # Ex: LAMPORT (Solana). Devise non gérée pour l'instant : on log une
        # seule fois par devise plutôt que de deviner une conversion, et le
        # montant reste non exploité (comportement identique à avant ce fix).
        if reference_currency not in _UNHANDLED_CURRENCIES_WARNED:
            _UNHANDLED_CURRENCIES_WARNED.add(reference_currency)
            print(
                f"   ⚠️  Devise '{reference_currency}' rencontrée mais pas encore "
                "gérée (ex: LAMPORT/Solana) : certaines annonces dans cette "
                "devise seront ignorées du floor price."
            )

    return None


def _live_offer_amount_eur(card: dict, rates: dict) -> float | None:
    """
    Extrait le montant (en EUR) de `liveSingleSaleOffer`, si lisible.
    Une offre a deux "côtés" (senderSide/receiverSide) : l'un contient la
    carte, l'autre le montant demandé. On identifie le côté "argent" comme
    celui qui ne contient pas de carte, puis on délègue la conversion
    (eurCents -> wei -> usdCents -> gbpCents) à `amount_to_eur`.

    Retourne None si l'offre est absente ou si aucun montant n'est
    exploitable dans une devise gérée.
    """
    offer = card.get("liveSingleSaleOffer")
    if not offer:
        return None
    for side_key in ("receiverSide", "senderSide"):
        side = offer.get(side_key) or {}
        if not side.get("anyCards"):
            amount = amount_to_eur(side.get("amounts"), rates)
            if amount is not None:
                return amount
    return None


def _resolve_confirmed_price(card: dict, index_price_eur: float, rates: dict) -> float | None:
    """
    Détermine le prix "confirmé" d'un candidat, uniquement à partir d'une
    VENTE DIRECTE (`liveSingleSaleOffer`) — pas d'enchère. Le prix affiché
    d'une enchère en cours n'est pas un prix d'achat garanti (il faut
    remporter l'enchère), donc on ne le compte pas comme un floor price
    fiable, même s'il peut sembler plus bas.
    """
    return _live_offer_amount_eur(card, rates)


def fetch_floor_prices_by_player(
    client: SorareClient,
    players: list[tuple[str, str]],
    rates: dict | None = None,
    delay_seconds: float = 0.2,
) -> dict[str, list[tuple[str, str, float, bool]]]:
    """
    Pour chaque joueur (nom affiché, slug), retourne la liste des
    (rareté, saison, prix confirmé en EUR) de ses cartes en vente.

    `players` est une liste de tuples (player_name, player_slug) : le nom
    sert de terme de recherche (texte libre), le slug sert à vérifier que
    chaque résultat correspond bien au bon joueur et pas à un homonyme
    (la recherche par nom seul peut être ambiguë).

    `rates` : dict retourné par `fetch_currency_rates`, nécessaire pour
    convertir un prix exprimé en wei (ETH), USD ou GBP. Sans lui (None),
    seuls les montants déjà en `eurCents` seront exploités.

    Toujours interrogé en direct sur l'API (pas de cache avec délai ici) :
    les floor prices doivent refléter le marché au moment exact du fetch.

    Clé du dict retourné : player_name (tel que fourni).
    """
    rates = rates or {}
    results: dict[str, list[tuple[str, str, float, bool]]] = {}
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
            card = hit.get("card") or {}
            hit_slug = (card.get("anyPlayer") or {}).get("slug")
            if expected_slug and hit_slug != expected_slug:
                # Homonyme ou joueur différent : on ignore ce résultat.
                continue

            index_price_cents = (hit.get("sale") or {}).get("price")
            index_price_eur = index_price_cents / 100 if index_price_cents is not None else None
            if index_price_eur is None:
                continue

            confirmed_price = _resolve_confirmed_price(card, index_price_eur, rates)
            if confirmed_price is not None:
                entries.append(
                    (
                        hit.get("rarity"),
                        hit.get("season"),
                        confirmed_price,
                        card.get("inSeasonEligible", False),
                    )
                )

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
    floor_data: dict[str, list[tuple[str, str, float, bool]]],
) -> float | None:
    """
    Détermine le floor price d'une carte à partir des résultats de
    `fetch_floor_prices_by_player`.

    - Carte "in season" : priorité au prix le plus bas parmi les annonces
      elles-mêmes in-season ET de la MÊME année d'édition ; repli sur les
      annonces in-season toutes années confondues si aucune de la même
      année n'est trouvée.
    - Carte "off season" : toutes les éditions HORS SAISON font partie du
      même pool de marché (mais pas les éditions encore in season, dont le
      prix suit une autre dynamique) : on prend le prix le plus bas parmi
      les annonces elles-mêmes hors saison, toutes années confondues.
    """
    entries = floor_data.get(player_name, [])
    same_rarity = [(s, p, ise) for (r, s, p, ise) in entries if r == rarity]
    if not same_rarity:
        return None

    if not in_season:
        off_season_prices = [p for _, p, ise in same_rarity if not ise]
        if off_season_prices:
            return min(off_season_prices)
        # Repli si aucune annonce hors-saison trouvée : toutes années.
        return min(p for _, p, _ in same_rarity)

    # Priorité : annonces elles-mêmes in-season, même année d'édition.
    same_season_in_season_prices = [
        p for s, p, ise in same_rarity if str(s) == str(season) and ise
    ]
    if same_season_in_season_prices:
        return min(same_season_in_season_prices)

    # Repli : annonces in-season, toutes années.
    any_season_in_season_prices = [p for _, p, ise in same_rarity if ise]
    if any_season_in_season_prices:
        return min(any_season_in_season_prices)

    # Dernier repli : aucune annonce in-season trouvée, toutes confondues.
    return min(p for _, p, _ in same_rarity)