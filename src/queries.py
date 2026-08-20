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
        # Niveau et XP de la carte (disponibles directement sur
        # AnyCardInterface, pas besoin de fragment inline). xpNeededForNextGrade
        # vaut `null` quand la carte a atteint son niveau maximum (plus de
        # palier suivant) : XP restant = xpNeededForNextGrade - xp.
        grade
        xp
        xpNeededForCurrentGrade
        xpNeededForNextGrade
        # Moyennes de la carte sur différentes fenêtres
        avgScoreL5: averageScore(type: LAST_FIVE_SO5_AVERAGE_SCORE)
        avgScoreL10: averageScore(type: LAST_TEN_PLAYED_SO5_AVERAGE_SCORE)
        avgScoreL40: averageScore(type: LAST_FORTY_SO5_AVERAGE_SCORE)
        # Prix plancher actuel du marché pour ce joueur/rareté/saison
        publicMinPrices {
          referenceCurrency
          eurCents
        }
        # Vente directe active de CETTE carte précise (si vous l'avez mise
        # en vente à prix fixe). Même structure que dans PLAYER_FLOOR_SEARCH :
        # le côté "argent" (sans anyCards) porte le montant demandé.
        liveSingleSaleOffer {
          senderSide {
            amounts {
              eurCents
              wei
              usdCents
              gbpCents
            }
            anyCards {
              slug
            }
          }
          receiverSide {
            amounts {
              eurCents
              wei
              usdCents
              gbpCents
            }
            anyCards {
              slug
            }
          }
        }
        # Enchère active de CETTE carte précise (si vous l'avez mise aux
        # enchères). `open` distingue une enchère en cours d'une déjà
        # terminée (le champ renvoie la DERNIÈRE enchère, pas forcément en
        # cours).
        latestEnglishAuction {
          open
          currentPrice
          currency
          endDate
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

# Taux de change live pour convertir correctement les prix exprimés dans
# une devise autre que l'EUR (wei/ETH pour les enchères, mais aussi USD et
# GBP : les managers peuvent lister leurs cartes dans ces devises, auquel
# cas eurCents ET wei restent tous les deux vides sur l'offre elle-même).
# ethRates donne la valeur de 1 ETH dans plusieurs devises au même instant,
# ce qui permet de dériver des taux croisés USD->EUR et GBP->EUR
# (eurCents / usdCents, eurCents / gbpCents) sans requête supplémentaire.
GET_EXCHANGE_RATE = """
query GetExchangeRate {
  config {
    exchangeRate {
      ethRates {
        eurCents
        usdCents
        gbpCents
      }
    }
  }
}
"""

# Utilitaire de diagnostic : teste si un nom de facette donné est valide et
# retourne ses valeurs possibles (utilisé pour trouver le bon champ "club").
SEARCH_CARD_FACET_VALUES = """
query TestFacet($field: String!, $facetQuery: String!) {
  searchCardFacetValues(field: $field, facetQuery: $facetQuery, limit: 5) {
    value
    count
  }
}
"""

# Champ dédié de l'API pour le prix le plus bas d'un joueur, filtré par
# rareté ET par statut in/off season directement côté serveur — plus
# fiable que de reconstruire ça à partir de la recherche texte libre.
PLAYER_LOWEST_PRICE = """
query PlayerLowestPrice($slugs: [String!]!, $rarity: Rarity!) {
  players(slugs: $slugs) {
    slug
    inSeasonCard: lowestPriceAnyCard(inSeason: true, rarity: $rarity) {
      slug
      publicMinPrices {
        eurCents
      }
      liveSingleSaleOffer {
        senderSide {
          amounts {
            eurCents
            wei
            usdCents
            gbpCents
          }
          anyCards {
            slug
          }
        }
        receiverSide {
          amounts {
            eurCents
            wei
            usdCents
            gbpCents
          }
          anyCards {
            slug
          }
        }
      }
      latestEnglishAuction {
        open
        currentPrice
        currency
      }
    }
    offSeasonCard: lowestPriceAnyCard(inSeason: false, rarity: $rarity) {
      slug
      publicMinPrices {
        eurCents
      }
      liveSingleSaleOffer {
        senderSide {
          amounts {
            eurCents
            wei
            usdCents
            gbpCents
          }
          anyCards {
            slug
          }
        }
        receiverSide {
          amounts {
            eurCents
            wei
            usdCents
            gbpCents
          }
          anyCards {
            slug
          }
        }
      }
      latestEnglishAuction {
        open
        currentPrice
        currency
      }
    }
  }
}
"""

# Requête légère pour calculer le floor price d'un joueur en cherchant ses
# cartes en vente, toutes raretés/saisons confondues (on filtre ensuite
# côté Python selon la rareté/saison voulue).
# Triée par prix croissant pour garantir de capter le vrai minimum malgré la
# limite de pageSize. Le slug du joueur est récupéré pour éviter de mélanger
# des homonymes (recherche texte ambiguë sur juste le nom affiché).
# `liveSingleSaleOffer` sert à vérifier que l'annonce est encore active :
# `sale.price` (index de recherche) peut être périmé (annonce déjà vendue).
# Seules les ventes directes comptent pour le floor price (pas les
# enchères, dont le prix affiché n'est pas un achat garanti).
PLAYER_FLOOR_SEARCH = """
query PlayerFloorSearch($query: String!) {
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
              eurCents
              wei
              usdCents
              gbpCents
            }
            anyCards {
              slug
            }
          }
          receiverSide {
            amounts {
              eurCents
              wei
              usdCents
              gbpCents
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

# Recherche de cartes par nom de joueur, avec filtre "en vente uniquement".
SEARCH_PLAYER_CARDS = """
query SearchPlayerCards($query: String!, $onSaleOnly: Boolean) {
  searchCards(query: $query, onSaleOnly: $onSaleOnly, pageSize: 100) {
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
        # u23Eligible n'existe que sur le type concret Card (football), pas
        # sur l'interface AnyCardInterface — même fragment inline que pour
        # vos propres cartes (voir GET_USER_CARDS).
        ... on Card {
          u23Eligible
        }
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

# Liste des watchlists du compte connecté. `filter: ALL_WATCHLISTS` inclut
# aussi bien les listes que vous avez créées que celles que vous suivez
# (créées par d'autres managers) — c'est ce qui apparaît sous "Watchlists"
# dans l'interface Sorare. `totalPlayersCount` sert juste d'info affichée
# à l'utilisateur : les joueurs eux-mêmes sont récupérés séparément via
# GET_WATCHLIST_PLAYERS (paginé, une watchlist peut contenir beaucoup de
# joueurs).
#
# IMPORTANT : `myWatchlists` est un champ de `CurrentUser`, PAS de la racine
# `Query` (vérifié en comparant avec le schéma réellement servi par l'API,
# téléchargé via `curl https://api.sorare.com/graphql/schema` — le dump
# schema.graphql du projet laissait à tort penser qu'il était à la racine).
# Doit donc être imbriqué dans `currentUser { ... }`, sinon l'API répond
# "Field 'myWatchlists' doesn't exist on type 'Query'".
GET_MY_WATCHLISTS = """
query GetMyWatchlists($sport: Sport!, $filter: WatchlistFilter) {
  currentUser {
    myWatchlists(sport: $sport, filter: $filter) {
      id
      slug
      title
      totalPlayersCount
    }
  }
}
"""

# Joueurs d'une watchlist précise, paginé. `positions` vient directement de
# CommonPlayer (pas besoin du fragment inline `... on Card` utilisé pour vos
# propres cartes, puisqu'il n'y a pas de carte concrète ici : juste le
# joueur suivi).
#
# IMPORTANT (2e essai) : `market.watchlist(id: ...)` renvoie "not found" pour
# une watchlist PRIVÉE (confirmé en pratique : erreur NOT_FOUND alors que le
# même id sort bien de currentUser.myWatchlists juste avant) — ce champ
# semble scopé aux watchlists visibles côté "market" (publiques), pas aux
# vôtres. On utilise à la place `node(id: ID!): Node`, le point d'entrée
# Relay générique de l'API (présent sur Query, vérifié dans le schéma) qui
# récupère n'importe quel objet par son id global selon les droits du
# viewer connecté — Watchlist implémente bien l'interface `Node`, donc ce
# chemin doit fonctionner pour vos propres listes, publiques ou non.
GET_WATCHLIST_PLAYERS = """
query GetWatchlistPlayers($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on Watchlist {
      commonPlayers(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          positions
          anyPlayer {
            slug
            displayName
            activeClub {
              name
              domesticLeague {
                name
              }
            }
            # u23Eligible n'existe que sur le type concret Player (football),
            # pas sur l'interface AnyPlayerInterface — même fragment inline
            # que pour vos propres cartes (voir GET_USER_CARDS, birthDate).
            ... on Player {
              u23Eligible
            }
          }
        }
      }
    }
  }
}
"""