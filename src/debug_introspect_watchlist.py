"""
Diagnostic : l'API a répondu "Field 'myWatchlists' doesn't exist on type
'Query'" alors que ce champ est bien présent dans schema.graphql (dump local,
possiblement périmé ou incomplet). Ce script interroge l'API EN DIRECT via
introspection GraphQL pour lister les vrais champs disponibles aujourd'hui
sur Query, afin de retrouver le nom exact (ou la structure) à utiliser pour
les watchlists.

Usage :
    python -m src.debug_introspect_watchlist
"""

import os

from dotenv import load_dotenv

from src.api_client import SorareClient
from src.auth import sign_in

load_dotenv()

INTROSPECT_QUERY_FIELDS = """
query IntrospectQueryFields {
  __type(name: "Query") {
    fields {
      name
    }
  }
}
"""

INTROSPECT_TYPE = """
query IntrospectType($name: String!) {
  __type(name: $name) {
    name
    kind
    fields {
      name
      args {
        name
        type {
          name
          kind
          ofType {
            name
          }
        }
      }
    }
  }
}
"""


def main():
    email = os.environ["SORARE_EMAIL"]
    password = os.environ["SORARE_PASSWORD"]
    jwt_token = sign_in(email, password)
    client = SorareClient(jwt_token)

    print("📡 Récupération de la liste réelle des champs sur Query...")
    data = client.execute(INTROSPECT_QUERY_FIELDS)
    all_fields = [f["name"] for f in data["__type"]["fields"]]
    print(f"→ {len(all_fields)} champs au total sur Query.\n")

    keywords = ["watch", "atch", "follow", "favorite", "favourite"]
    matches = sorted(
        {f for f in all_fields if any(k in f.lower() for k in keywords)}
    )
    if matches:
        print("Champs correspondant à 'watch/follow/favorite' :")
        for m in matches:
            print(f"  - {m}")
    else:
        print(
            "⚠️  Aucun champ contenant 'watch', 'follow' ou 'favorite' trouvé "
            "sur Query. Les watchlists ne sont peut-être pas exposées via "
            "l'API pour ce compte, ou portent un nom totalement différent."
        )

    print("\n📡 Détail du type CurrentUser (au cas où les watchlists y seraient "
          "rattachées plutôt que sur Query directement)...")
    cu = client.execute(INTROSPECT_TYPE, {"name": "CurrentUser"})
    if cu.get("__type"):
        cu_fields = [f["name"] for f in cu["__type"]["fields"]]
        cu_matches = sorted(
            {f for f in cu_fields if any(k in f.lower() for k in keywords)}
        )
        if cu_matches:
            print("Champs correspondants sur CurrentUser :")
            for m in cu_matches:
                print(f"  - {m}")
        else:
            print("Aucun champ 'watch/follow/favorite' trouvé sur CurrentUser non plus.")
    else:
        print("Type 'CurrentUser' introuvable via introspection.")


if __name__ == "__main__":
    main()
