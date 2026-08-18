"""
Diagnostic : pour les offres dont `eurCents` ET `wei` sont vides
(cas vus avec debug_live_offer_raw), on soupçonne que l'offre est en fait
libellée dans une AUTRE devise que EUR/ETH (USD ou LAMPORT/Solana), champs
qu'on ne demande jamais dans les requêtes actuelles (PLAYER_FLOOR_SEARCH
etc. ne récupèrent que `eurCents` et `wei` sur `amounts`).

Ce script relance une requête ad-hoc qui demande EN PLUS `referenceCurrency`,
`usdCents`, `gbpCents` et `lamport` sur les mêmes offres, pour confirmer
l'hypothèse.

Usage :
    python -m src.debug_live_offer_currency "Kosei Tani" --max-index-price 20
"""

import json
import os
import sys

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in
from src.floor_price import fetch_currency_rates

load_dotenv()

PLAYER_FLOOR_SEARCH_FULL_CURRENCY = """
query PlayerFloorSearchFullCurrency($query: String!) {
  searchCards(
    query: $query
    onSaleOnly: true
    pageSize: 100
    sorts: [{ field: "price", direction: ASC }]
  ) {
    hits {
      slug
      rarity
      season
      sale {
        price
      }
      card {
        anyPlayer {
          slug
        }
        inSeasonEligible
        liveSingleSaleOffer {
          senderSide {
            amounts {
              referenceCurrency
              eurCents
              gbpCents
              usdCents
              wei
              lamport
            }
            anyCards {
              slug
            }
          }
          receiverSide {
            amounts {
              referenceCurrency
              eurCents
              gbpCents
              usdCents
              wei
              lamport
            }
            anyCards {
              slug
            }
          }
        }
      }
    }
  }
}
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "Pedri"

    max_index_price = None
    if "--max-index-price" in sys.argv:
        idx = sys.argv.index("--max-index-price")
        max_index_price = float(sys.argv[idx + 1])

    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    rates = fetch_currency_rates(client)
    print(f"Taux de change : {rates}\n")

    data = client.execute(PLAYER_FLOOR_SEARCH_FULL_CURRENCY, {"query": name})
    hits = data["searchCards"]["hits"]

    shown = 0
    for hit in hits:
        card = hit.get("card") or {}
        offer = card.get("liveSingleSaleOffer")
        if offer is None:
            continue

        index_price = (hit.get("sale") or {}).get("price")
        index_price_eur = index_price / 100 if index_price is not None else None
        if max_index_price is not None and (
            index_price_eur is None or index_price_eur > max_index_price
        ):
            continue

        receiver_amounts = (offer.get("receiverSide") or {}).get("amounts") or {}
        sender_amounts = (offer.get("senderSide") or {}).get("amounts") or {}
        # On ne réaffiche que les cas où EUR et wei sont vides des deux côtés
        # (ceux qu'on n'arrivait pas à convertir jusqu'ici).
        both_empty = all(
            not amounts.get("eurCents") and (not amounts.get("wei") or amounts.get("wei") == "0")
            for amounts in (receiver_amounts, sender_amounts)
        )
        if not both_empty:
            continue

        shown += 1
        print("=" * 70)
        print(
            f"rarity={hit.get('rarity')} season={hit.get('season')} "
            f"in_season={card.get('inSeasonEligible')} "
            f"index_price={index_price_eur}€ card_slug={hit.get('slug')}"
        )
        print("liveSingleSaleOffer (avec toutes les devises) :")
        print(json.dumps(offer, indent=2, ensure_ascii=False))
        print()

    if shown == 0:
        print("Aucune offre correspondante trouvée avec ces critères.")
    else:
        print(f"\n{shown} offre(s) affichée(s) ci-dessus.")


if __name__ == "__main__":
    main()
