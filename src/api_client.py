"""Client GraphQL minimaliste pour l'API Sorare."""

import requests

GRAPHQL_URL = "https://api.sorare.com/graphql"

# Doit être IDENTIQUE à la valeur "aud" utilisée lors du signIn (voir auth.py)
APP_AUDIENCE = "sorare-analyzer"


class SorareAPIError(Exception):
    pass


class SorareClient:
    def __init__(self, jwt_token: str):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_token}",
            # Requis par Sorare en plus du Bearer token, sinon erreur "wrong aud"
            "JWT-AUD": APP_AUDIENCE,
        }

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """Exécute une requête ou mutation GraphQL et retourne le champ `data`."""
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers=self.headers,
        )

        # Sorare peut renvoyer un code 422 (ou autre) avec le détail de
        # l'erreur GraphQL dans le corps JSON : on l'affiche avant de
        # lever une exception HTTP générique qui masquerait ce détail.
        if not resp.ok:
            try:
                error_body = resp.json()
            except ValueError:
                error_body = resp.text
            raise SorareAPIError(f"HTTP {resp.status_code} : {error_body}")

        payload = resp.json()

        if "errors" in payload:
            raise SorareAPIError(payload["errors"])

        return payload["data"]

