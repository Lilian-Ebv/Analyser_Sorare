"""
Logique d'analyse des cartes.

⚠️ Les règles d'éligibilité par compétition (rareté requise, âge, ancienneté
de la carte...) évoluent régulièrement côté Sorare. La fonction
`eligible_leagues` ci-dessous donne une base de règles courantes à titre
indicatif — pensez à les vérifier/ajuster depuis la page des compétitions
en cours sur sorare.com avant de vous y fier pour composer vos équipes.
"""

from datetime import datetime, timezone

import pandas as pd

from src.floor_price import amount_to_eur


ACQUISITION_LABELS = {
    "INSTANT_BUY": "Achat (instant buy)",
    "SINGLE_BUY_OFFER": "Achat (offre)",
    "SINGLE_SALE_OFFER": "Achat (offre)",
    "DIRECT_OFFER": "Achat (offre directe)",
    "ENGLISH_AUCTION": "Achat (enchère)",
    "BUNDLED_ENGLISH_AUCTION": "Achat (enchère groupée)",
    "REWARD": "Récompense",
    "SHARDS": "Craft (shards)",
    "MINT": "Mint",
    "PACK": "Pack",
    "REFERRAL": "Parrainage",
    "TRANSFER": "Transfert (don/reçu)",
    "DEPOSIT": "Dépôt blockchain",
    "WITHDRAWAL": "Retrait blockchain",
    "LOAN": "Prêt",
}

# transferTypes pour lesquels un prix d'achat a vraiment un sens
PURCHASE_TRANSFER_TYPES = {
    "INSTANT_BUY",
    "SINGLE_BUY_OFFER",
    "SINGLE_SALE_OFFER",
    "DIRECT_OFFER",
    "ENGLISH_AUCTION",
    "BUNDLED_ENGLISH_AUCTION",
}


def _cents_to_eur(monetary_amount: dict | None) -> float | None:
    """Convertit un objet MonetaryAmount (eurCents) en euros, ou None si absent."""
    if not monetary_amount or monetary_amount.get("eurCents") is None:
        return None
    return monetary_amount["eurCents"] / 100


def _extract_floor_price_eur(card: dict) -> float | None:
    """
    Prix plancher direct depuis Sorare (`publicMinPrices`), quand disponible.

    Ce champ est vide pour beaucoup de cartes (peu d'activité récente sur
    ce joueur/rareté/saison précis) : dans ce cas, le vrai floor price est
    calculé séparément via une recherche par joueur (voir
    `src/floor_price.py`, appelé depuis `main.py`), car les champs
    `lowestPriceCard`/`lowestPriceCardAnySeason` de l'API se sont montrés
    peu fiables (montants manquants).
    """
    return _cents_to_eur(card.get("publicMinPrices"))


def _single_sale_offer_amount_eur(card: dict, rates: dict) -> float | None:
    """
    Montant (EUR) de la vente directe active de la carte (`liveSingleSaleOffer`),
    si lisible. Même logique que `floor_price._live_offer_amount_eur` : le
    côté "argent" de l'offre est celui qui ne contient pas de carte ; la
    conversion (eurCents -> wei -> usdCents -> gbpCents) est déléguée à
    `floor_price.amount_to_eur` pour rester cohérente avec le calcul du
    floor price (certains managers listent en USD/GBP, pas seulement EUR/ETH).
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


def _open_auction_amount_eur(card: dict, rates: dict) -> float | None:
    """
    Prix actuel (EUR) de l'enchère active de la carte, si elle est ouverte.
    `latestEnglishAuction` porte un montant + devise unique (pas un
    MonetaryAmount multi-devises comme les ventes directes), donc la
    conversion est gérée ici directement plutôt que via `amount_to_eur`.
    """
    auction = card.get("latestEnglishAuction") or {}
    if not auction.get("open"):
        return None
    current_price = auction.get("currentPrice")
    currency = auction.get("currency")
    if current_price is None or currency is None:
        return None

    if currency == "EUR":
        return float(current_price) / 100
    if currency == "WEI":
        eth_eur_cents = rates.get("eth_eur_cents")
        return (float(current_price) / 1e18) * (eth_eur_cents / 100) if eth_eur_cents else None
    if currency == "USD":
        usd_eur_rate = rates.get("usd_eur_rate")
        return (float(current_price) / 100) * usd_eur_rate if usd_eur_rate else None
    if currency == "GBP":
        gbp_eur_rate = rates.get("gbp_eur_rate")
        return (float(current_price) / 100) * gbp_eur_rate if gbp_eur_rate else None

    # Devise non gérée (ex: LAMPORT/Solana) : voir le même garde-fou dans
    # floor_price.amount_to_eur.
    return None


def _extract_active_sale(
    card: dict, rates: dict | None
) -> tuple[float | None, str | None, str | None]:
    """
    Retourne (prix demandé en EUR, type de vente, date de fin d'enchère) pour
    une carte que VOUS avez actuellement mise en vente, sinon (None, None, None).

    Priorité à la vente directe (prix garanti) ; sinon, prix live de
    l'enchère en cours si vous en avez ouvert une.
    """
    rates = rates or {}
    sale_price = _single_sale_offer_amount_eur(card, rates)
    if sale_price is not None:
        return sale_price, "Vente directe", None

    auction = card.get("latestEnglishAuction") or {}
    if auction.get("open"):
        price = _open_auction_amount_eur(card, rates)
        if price is not None:
            return price, "Enchère", auction.get("endDate")

    return None, None, None


def _extract_acquisition(card: dict, my_slug: str) -> tuple[float | None, str | None, str | None]:
    """
    Cherche dans l'historique de propriété de la carte l'entrée qui
    correspond à votre acquisition, et retourne
    (prix en EUR ou None, date, type d'acquisition lisible).

    S'il y a plusieurs entrées vous concernant (carte revendue puis
    rachetée), on garde la plus récente. Le prix n'est renseigné que si
    l'acquisition est un vrai achat (REWARD/SHARDS/MINT/PACK n'ont pas de
    prix d'achat monétaire, c'est normal, pas une donnée manquante).
    """
    history = card.get("ownershipHistory") or []
    my_entries = [
        entry
        for entry in history
        if (entry.get("user") or {}).get("slug") == my_slug
    ]
    if not my_entries:
        return None, None, None

    latest = max(my_entries, key=lambda e: e.get("from") or "")
    transfer_type = latest.get("transferType")
    acquisition_label = ACQUISITION_LABELS.get(transfer_type, transfer_type)

    price = _cents_to_eur(latest.get("amounts")) if transfer_type in PURCHASE_TRANSFER_TYPES else None

    return price, latest.get("from"), acquisition_label


def _parse_iso(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_next_gameweek(card: dict) -> tuple[str | None, str | None, str | None]:
    """
    Parmi les game weeks Sorare (So5) auxquelles cette carte est éligible,
    retourne celle dont la deadline de composition (cutOffDate) est la plus
    proche : (nom, deadline ISO, date de fin ISO).
    """
    tracks = card.get("eligibleUpcomingLeagueTracks") or []
    now = datetime.now(timezone.utc)
    candidates = []
    for track in tracks:
        leaderboard = track.get("entrySo5Leaderboard") or {}
        fixture = leaderboard.get("so5Fixture") or {}
        cutoff = fixture.get("cutOffDate")
        cutoff_dt = _parse_iso(cutoff)
        if not cutoff_dt:
            continue

        # `eligibleUpcomingLeagueTracks` inclut aussi des game weeks déjà
        # verrouillées (deadline passée, matchs pas encore joués) : on ne
        # garde que celles où on peut encore composer.
        if cutoff_dt <= now:
            continue

        candidates.append((cutoff, fixture.get("displayName"), fixture.get("endDate")))

    if not candidates:
        return None, None, None

    candidates.sort(key=lambda c: c[0])
    cutoff, name, end_date = candidates[0]
    return name, cutoff, end_date


def _extract_next_game(player: dict) -> tuple[str | None, str | None, str | None]:
    """
    Retourne (date ISO, compétition, libellé "Domicile vs Extérieur") du
    prochain match éligible aux compétitions Sorare pour ce joueur.
    """
    game = player.get("nextGame")
    if not game:
        return None, None, None

    competition = (game.get("competition") or {}).get("name")
    home = (game.get("homeTeam") or {}).get("name")
    away = (game.get("awayTeam") or {}).get("name")
    matchup = f"{home} vs {away}" if home and away else None

    return game.get("date"), competition, matchup


def cards_to_dataframe(
    card_nodes: list[dict],
    my_slug: str,
    rarities: list[str] | None = None,
    rates: dict | None = None,
) -> pd.DataFrame:
    """
    Transforme la liste brute de cartes (JSON GraphQL) en DataFrame pandas.

    `rarities` : si fourni (ex: ["limited"]), ne garde que les cartes de ces
    raretés. Laissez à None pour garder toutes les cartes.

    `rates` : dict retourné par `floor_price.fetch_currency_rates`, nécessaire
    pour convertir en euros le prix d'une éventuelle vente/enchère active
    exprimée en wei (ETH), USD ou GBP (`sale_price_eur`). Sans lui, seules
    les ventes déjà en EUR seront détectées.
    """
    rows = []
    for card in card_nodes:
        if rarities and card["rarityTyped"] not in rarities:
            continue

        player = card["anyPlayer"]
        # positionTyped (fragment Card) est plus précis ; anyPositions
        # (disponible pour toutes les cartes) sert de repli.
        position = card.get("positionTyped") or next(iter(card.get("anyPositions") or []), None)

        purchase_price_eur, purchase_date, acquisition_type = _extract_acquisition(card, my_slug)
        floor_price_eur = _extract_floor_price_eur(card)
        sale_price_eur, sale_type, sale_end_date = _extract_active_sale(card, rates)
        next_game_date, next_game_competition, next_game_matchup = _extract_next_game(player)
        next_gameweek_name, next_gameweek_deadline, next_gameweek_end = _extract_next_gameweek(card)

        # Le match "brut" le plus proche peut appartenir à une game week déjà
        # verrouillée (différente de celle affichée). On ne garde le
        # match/date affichés que s'ils tombent bien dans la fenêtre
        # [deadline → fin] de la game week retournée, pour éviter d'associer
        # un match à la mauvaise game week.
        game_dt = _parse_iso(next_game_date)
        cutoff_dt = _parse_iso(next_gameweek_deadline)
        end_dt = _parse_iso(next_gameweek_end)
        if game_dt and cutoff_dt and not (cutoff_dt <= game_dt and (end_dt is None or game_dt <= end_dt)):
            next_game_date, next_game_competition, next_game_matchup = None, None, None

        rows.append(
            {
                "card_slug": card["slug"],
                "rarity": card["rarityTyped"],
                "season": card.get("seasonYear"),
                "position": position,
                "u23_eligible": card.get("u23Eligible", False),
                "sealed": card.get("sealed", False),
                "in_season": card.get("inSeasonEligible", False),
                "player_name": player["displayName"],
                "player_slug": player.get("slug"),
                "birth_date": player.get("birthDate"),
                "club": player["activeClub"]["name"] if player.get("activeClub") else None,
                "league": (
                    (player.get("activeClub") or {}).get("domesticLeague") or {}
                ).get("name"),
                "avg_score_l5": card.get("avgScoreL5"),
                "avg_score_l10": card.get("avgScoreL10"),
                "avg_score_l40": card.get("avgScoreL40"),
                "acquisition_type": acquisition_type,
                "purchase_price_eur": purchase_price_eur,
                "purchase_date": purchase_date,
                "floor_price_eur": floor_price_eur,
                "sale_price_eur": sale_price_eur,
                "sale_type": sale_type,
                "sale_end_date": sale_end_date,
                "next_game_date": next_game_date,
                "next_game_competition": next_game_competition,
                "next_game_matchup": next_game_matchup,
                "next_gameweek_name": next_gameweek_name,
                "next_gameweek_deadline": next_gameweek_deadline,
                "next_gameweek_end": next_gameweek_end,
            }
        )
    return pd.DataFrame(rows)


def eligible_leagues(row: pd.Series) -> list[str]:
    """
    Retourne la liste des types de compétitions dans lesquelles cette carte
    est probablement jouable, selon sa rareté (règles indicatives).
    """
    leagues = []
    rarity = str(row["rarity"]).lower()

    if rarity == "limited":
        leagues.append("Champion / Limited League")
    if rarity in ("rare", "super_rare"):
        leagues.append("Rare League")
    if rarity == "super_rare":
        leagues.append("Super Rare League")
    if rarity == "unique":
        leagues.append("Unique League")
    if row.get("u23_eligible"):
        leagues.append("Rookie / U23 League")

    return leagues or ["Aucune compétition standard identifiée"]


def rank_best_lineup(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """
    Classe les cartes par forme récente (moyenne des 5 derniers matchs)
    et retourne les meilleures, par poste.
    """
    df = df.copy()
    df["eligible_leagues"] = df.apply(eligible_leagues, axis=1)

    ranked = (
        df.sort_values("avg_score_l5", ascending=False)
        .groupby("position", group_keys=False)
        .head(top_n)
    )
    return ranked[
        ["player_name", "position", "club", "rarity", "avg_score_l5", "eligible_leagues"]
    ]