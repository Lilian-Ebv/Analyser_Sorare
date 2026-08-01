"""
Authentification à l'API Sorare.

Flux :
1. On récupère le "salt" bcrypt associé à l'email via une requête GET.
2. On hash le mot de passe côté client avec ce salt (bcrypt).
3. On envoie une mutation GraphQL `signIn` avec l'email + le mot de passe hashé
   pour récupérer un token JWT.
4. Ce JWT est ensuite utilisé dans le header Authorization de toutes les
   requêtes suivantes.
"""

import bcrypt
import requests

BASE_URL = "https://api.sorare.com"
GRAPHQL_URL = f"{BASE_URL}/graphql"

# "aud" (audience) : identifiant libre de votre application.
# Sorare l'utilise pour segmenter les tokens JWT émis.
APP_AUDIENCE = "sorare-analyzer"


class SorareAuthError(Exception):
    pass


def _get_salt(email: str) -> str:
    """Récupère le salt bcrypt associé à un compte Sorare."""
    resp = requests.get(f"{BASE_URL}/api/v1/users/{email}")
    resp.raise_for_status()
    data = resp.json()
    if "salt" not in data:
        raise SorareAuthError(f"Impossible de récupérer le salt : {data}")
    return data["salt"]


def _hash_password(password: str, salt: str) -> str:
    """Hash le mot de passe avec bcrypt en utilisant le salt fourni par Sorare."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt.encode("utf-8"))
    return hashed.decode("utf-8")


_SIGN_IN_MUTATION = """
mutation SignInMutation($input: signInInput!, $aud: String!) {
  signIn(input: $input) {
    currentUser {
      slug
      nickname
    }
    jwtToken(aud: $aud) {
      token
      expiredAt
    }
    otpSessionChallenge
    errors {
      message
    }
  }
}
"""


def _call_sign_in(input_payload: dict) -> dict:
    """Appelle la mutation signIn et retourne le bloc `signIn` de la réponse."""
    resp = requests.post(
        GRAPHQL_URL,
        json={
            "query": _SIGN_IN_MUTATION,
            "variables": {"input": input_payload, "aud": APP_AUDIENCE},
        },
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    payload = resp.json()

    sign_in_data = payload.get("data", {}).get("signIn")
    if not sign_in_data:
        raise SorareAuthError(f"Réponse inattendue : {payload}")

    return sign_in_data


def start_sign_in(email: str, password: str) -> tuple[str | None, str | None]:
    """
    Première étape de connexion : email + mot de passe.

    Retourne (jwt_token, otp_session_challenge) :
    - Si la 2FA n'est pas activée : (jwt_token, None)
    - Si la 2FA est activée : (None, otp_session_challenge) — il faut alors
      appeler `complete_sign_in()` avec le code à 6 chiffres.
    """
    salt = _get_salt(email)
    hashed_password = _hash_password(password, salt)

    sign_in_data = _call_sign_in({"email": email, "password": hashed_password})

    otp_session_challenge = sign_in_data.get("otpSessionChallenge")
    errors = sign_in_data.get("errors")

    # Sorare renvoie parfois un "otpSessionChallenge" ET un message d'erreur
    # "2fa_missing" en même temps sur ce premier appel : ce n'est pas un
    # vrai échec, c'est juste l'API qui signale qu'il faut continuer avec
    # le code OTP. On ne traite les erreurs comme bloquantes que si aucun
    # otpSessionChallenge n'a été fourni.
    if errors and not otp_session_challenge:
        raise SorareAuthError(f"Échec de l'authentification : {errors}")

    if otp_session_challenge:
        return None, otp_session_challenge

    jwt_token = sign_in_data.get("jwtToken", {}).get("token")
    if not jwt_token:
        raise SorareAuthError(f"Aucun token JWT retourné : {sign_in_data}")

    return jwt_token, None


def complete_sign_in(otp_session_challenge: str, otp_code: str) -> str:
    """Deuxième étape (si 2FA) : valide le code à 6 chiffres et retourne le JWT."""
    sign_in_data = _call_sign_in(
        {"otpSessionChallenge": otp_session_challenge, "otpAttempt": otp_code}
    )

    errors = sign_in_data.get("errors")
    if errors:
        raise SorareAuthError(f"Code 2FA invalide : {errors}")

    jwt_token = sign_in_data.get("jwtToken", {}).get("token")
    if not jwt_token:
        raise SorareAuthError(f"Aucun token JWT retourné : {sign_in_data}")

    return jwt_token


def sign_in(email: str, password: str, otp_code: str | None = None) -> str:
    """
    Authentifie l'utilisateur (usage terminal/CLI) et retourne un token JWT.

    Si le compte a la 2FA activée et qu'aucun `otp_code` n'est fourni, le
    code est demandé interactivement via input(). Pour un usage non
    interactif (ex: Streamlit), préférez `start_sign_in()` +
    `complete_sign_in()` directement.
    """
    jwt_token, otp_session_challenge = start_sign_in(email, password)

    if otp_session_challenge:
        if not otp_code:
            otp_code = input("🔐 Code 2FA (6 chiffres) : ").strip()
        jwt_token = complete_sign_in(otp_session_challenge, otp_code)

    print("✅ Connecté à Sorare")
    return jwt_token