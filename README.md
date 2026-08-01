# Sorare Analyzer

Petit outil personnel pour analyser vos cartes Sorare (football) : récupération
via l'API GraphQL officielle, classement par forme récente, et identification
des compétitions dans lesquelles chaque carte est jouable.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate  # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
```

Puis éditez `.env` avec votre email, mot de passe et pseudo (slug) Sorare.

⚠️ **Sécurité** : ne partagez jamais ce fichier `.env` et ajoutez-le à votre
`.gitignore` si vous versionnez le projet.

## ⚠️ Authentification à deux facteurs (2FA)

Si votre compte a la 2FA activée (recommandé sur Sorare !), la mutation
`signIn` retournera une erreur demandant un `otpAttempt`. Dans ce cas, il
faudra adapter `src/auth.py` pour :
1. Détecter l'erreur `otp_required` dans la réponse.
2. Redemander le code depuis votre app d'authentification.
3. Relancer `signIn` avec ce code en plus dans les `variables`.

C'est documenté dans la doc officielle (section Authentication) —
dites-moi si vous voulez que je l'implémente directement.

## Utilisation

```bash
python -m src.main
```

Le script :
1. Se connecte à votre compte Sorare et récupère un token JWT.
2. Télécharge toutes vos cartes football (avec pagination automatique).
3. Affiche un classement des meilleures cartes par poste, basé sur la
   moyenne des 5 derniers matchs de chaque joueur.
4. Exporte le détail complet dans `mes_cartes.csv`.

## Structure du projet

```
sorare-analyzer/
├── src/
│   ├── auth.py         # Authentification (salt + bcrypt + JWT)
│   ├── api_client.py   # Client GraphQL générique
│   ├── queries.py      # Requêtes GraphQL (cartes, compétitions...)
│   ├── analysis.py     # Logique de classement / éligibilité
│   └── main.py         # Script principal
├── requirements.txt
└── .env.example
```

## Pour aller plus loin

Quelques pistes d'évolution naturelles :
- **Interface graphique** : `streamlit run app.py` pour un dashboard cliquable
  plutôt qu'un script en ligne de commande.
- **Alertes automatiques** : cron job qui vous envoie un mail/notif avant
  chaque deadline de composition si une carte performante est sur le banc.
- **Historique de performance** : stocker les résultats dans une base SQLite
  au fil des game weeks pour suivre l'évolution de vos joueurs dans le temps.
- **Prix du marché** : croiser vos cartes avec les prix de vente actuels
  (champ `onSaleFor` dans l'API) pour repérer les opportunités.

## Ressources

- Documentation officielle : https://github.com/sorare/api
- Playground GraphQL : section "Docs" sur le playground de l'API Sorare
