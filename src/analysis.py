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


def _extract_offer_price_eur(offer: dict | None) -> float | None:
    """
    Extrait le prix (en EUR) d'une offre de vente (TokenOffer).

    Une offre a deux "côtés" (senderSide / receiverSide) : l'un contient la
    carte, l'autre le montant demandé. On identifie le côté "argent" comme
    celui qui ne contient pas de carte, pour rester robuste peu importe le
    sens exact de la relation sender/receiver.
    """
    if not offer:
        return None
    for side_key in ("receiverSide", "senderSide"):
        side = offer.get(side_key) or {}
        if not side.get("anyCards"):
            price = _cents_to_eur(side.get("amounts"))
            if price is not None:
                return price
    return None


def _extract_floor_price_eur(card: dict) -> float | None:
    """
    Détermine un prix plancher en cascade :
    1. publicMinPrices (prix calculé par Sorare pour ce joueur/rareté/saison)
    2. Prix de la carte équivalente la moins chère en vente, même saison
    3. Idem, toutes saisons confondues
    """
    direct = _cents_to_eur(card.get("publicMinPrices"))
    if direct is not None:
        return direct

    same_season = card.get("lowestPriceCard") or {}
    price = _extract_offer_price_eur(same_season.get("liveSingleSaleOffer"))
    if price is not None:
        return price

    any_season = card.get("lowestPriceCardAnySeason") or {}
    return _extract_offer_price_eur(any_season.get("liveSingleSaleOffer"))


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
) -> pd.DataFrame:
    """
    Transforme la liste brute de cartes (JSON GraphQL) en DataFrame pandas.

    `rarities` : si fourni (ex: ["limited"]), ne garde que les cartes de ces
    raretés. Laissez à None pour garder toutes les cartes.
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