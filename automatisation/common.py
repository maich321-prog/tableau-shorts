"""Outils communs : config, connexion à l'API YouTube pour une chaîne."""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
TOKENS = HERE / "tokens"
SECRET = HERE / "client_secret.json"

# upload = publier ; force-ssl = lire/répondre aux commentaires ; readonly = lire la chaîne
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def load_config():
    return json.loads((HERE / "config.json").read_text(encoding="utf-8"))


def channel(key):
    cfg = load_config()
    if key not in cfg["channels"]:
        sys.exit(f"Chaîne inconnue : {key}. Choix : {', '.join(cfg['channels'])}")
    return cfg["channels"][key]


def token_path(key):
    return TOKENS / f"token-{key}.json"


def get_service(key):
    """Retourne un client YouTube connecté à la chaîne `key` (token déjà créé par auth.py)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    tp = token_path(key)
    if not tp.exists():
        sys.exit(f"Pas encore autorisé pour « {key} ». Lance d'abord : python auth.py {key}")
    creds = Credentials.from_authorized_user_file(str(tp))  # garde les droits du token
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            tp.write_text(creds.to_json(), encoding="utf-8")
        else:
            sys.exit(f"Autorisation expirée pour « {key} ». Relance : python auth.py {key}")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path, default=None):
    path = pathlib.Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
