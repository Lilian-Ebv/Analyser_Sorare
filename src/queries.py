"""
Requêtes GraphQL réutilisables.

Astuce : vous pouvez tester et adapter ces requêtes directement dans le
GraphQL playground de Sorare (accessible depuis leur doc développeur) avant
de les copier ici — ça évite les allers-retours en aveugle.
"""

# Récupère toutes les cartes footballs d'un utilisateur, avec les infos
# nécessaires pour l'analyse : joueur, poste, club, rareté, dernières perfs.
GET_CURRENT_USER = """
query GetCurrentUser {
  currentUser {
    slug
    nickname
  }
}
"""

GET_USER_CARDS = """
query GetUserCards($slug: String!, $cursor: String, $rarities: [Rarity!]) {
  user(slug: $slug) {
    slug
    cards(first: 100, after: $cursor, rarities: $rarities) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        slug
        rarityTyped
        seasonYear
        anyPositions
        sealed
        inSeasonEligible
        # Moyennes de la carte sur différentes fenêtres
        avgScoreL5: averageScore(type: LAST_FIVE_SO5_AVERAGE_SCORE)
        avgScoreL10: averageScore(type: LAST_TEN_PLAYED_SO5_AVERAGE_SCORE)
        avgScoreL40: averageScore(type: LAST_FORTY_SO5_AVERAGE_SCORE)
        # Prix plancher actuel du marché pour ce joueur/rareté/saison
        publicMinPrices {
          referenceCurrency
          eurCents
        }
        # Game weeks / compétitions Sorare à venir pour lesquelles cette
        # carte précise est éligible, avec la deadline de composition.
        eligibleUpcomingLeagueTracks {
          slug
          displayName
          entrySo5Leaderboard {
            so5Fixture {
              displayName
              cutOffDate
              endDate
            }
          }
        }
        # Replis si publicMinPrices est vide (peu d'activité récente) :
        # prix de la carte équivalente la moins chère en vente, d'abord sur
        # la même saison, puis toutes saisons confondues.
        lowestPriceCard {
          liveSingleSaleOffer {
            senderSide {
              amounts { eurCents }
              anyCards { slug }
            }
            receiverSide {
              amounts { eurCents }
              anyCards { slug }
            }
          }
        }
        lowestPriceCardAnySeason {
          liveSingleSaleOffer {
            senderSide {
              amounts { eurCents }
              anyCards { slug }
            }
            receiverSide {
              amounts { eurCents }
              anyCards { slug }
            }
          }
        }
        # Historique de propriété : on filtre côté Python l'entrée qui vous
        # concerne pour en tirer votre prix d'achat.
        ownershipHistory {
          from
          transferType
          amounts {
            referenceCurrency
            eurCents
          }
          user {
            slug
          }
        }
        anyPlayer {
          slug
          displayName
          activeClub {
            name
            domesticLeague {
              name
            }
          }
          # Prochain match éligible aux compétitions Sorare (So5)
          nextGame(so5FixtureEligible: true) {
            date
            competition {
              name
            }
            homeTeam {
              name
            }
            awayTeam {
              name
            }
          }
          # birthDate n'existe que sur le type concret Player, pas sur
          # l'interface AnyPlayerInterface, d'où ce fragment inline.
          ... on Player {
            birthDate
          }
        }
        # `cards` renvoie l'interface AnyCardInterface : u23Eligible et
        # positionTyped ne sont disponibles que sur le type concret Card
        # (cartes football), d'où ce fragment inline.
        ... on Card {
          u23Eligible
          positionTyped
        }
      }
    }
  }
}
"""

# Recherche de cartes par nom de joueur, avec filtre "en vente uniquement".
SEARCH_PLAYER_CARDS = """
query SearchPlayerCards($query: String!, $onSaleOnly: Boolean) {
  searchCards(query: $query, onSaleOnly: $onSaleOnly, pageSize: 25) {
    nbHits
    hits {
      slug
      rarity
      season
      sale {
        price
        type
      }
      card {
        anyPlayer {
          displayName
          activeClub {
            name
          }
        }
        # Repli si `sale` est vide (cas des enchères groupées / packs, où
        # le prix n'est pas rattaché à une seule carte individuelle).
        # `open` permet d'ignorer les enchères déjà terminées : ce champ
        # renvoie la DERNIÈRE enchère dont la carte a fait partie, pas
        # forcément une enchère en cours.
        latestEnglishAuction {
          open
          currentPrice
          currency
          endDate
          bundledAnyCards {
            anyPlayer {
              displayName
            }
          }
        }
      }
    }
  }
}
"""

# Récupère les prochaines game weeks / compétitions disponibles et leurs
# fenêtres de composition (deadline).
GET_UPCOMING_LEAGUES = """
query GetUpcomingLeagues {
  footballLeagues: leaderboards {
    nodes {
      slug
      name
      startDate
      endDate
    }
  }
}
"""