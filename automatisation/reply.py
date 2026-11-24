"""Répondre aux commentaires d'un Short (courtes réponses variées, en anglais, avec emojis).

Usage :
  python reply.py malik <video_id>            (répond pour de vrai)
  python reply.py malik <video_id> --dry-run  (affiche seulement ce qu'il répondrait)

Règles (RÈGLE N°1 + accord de Moha) :
- seulement sur nos chaînes, seulement les commentaires principaux (jamais les réponses),
  jamais deux fois au même commentaire (vérifié aussi sur YouTube) ;
- pas de réponse aux insultes, sujets sensibles, liens : ils sont listés pour Moha ;
- les plus likés d'abord ; au maximum `max_replies_per_channel_per_run` réponses
  (une réponse coûte 50 unités de quota sur 10 000 par jour).
"""
import argparse

from common import HERE, channel, get_service, load_config, read_json, write_json
from logic import needs_review, pick_reply
from votes import fetch_comments


def already_replied(yt, comment_id, channel_id):
    """Vrai si la chaîne a déjà répondu sous ce commentaire principal (marche aussi depuis GitHub, sans mémoire)."""
    token = None
    while True:
        r = yt.comments().list(part="snippet", parentId=comment_id, maxResults=100, pageToken=token).execute()
        for it in r.get("items", []):
            if (it["snippet"].get("authorChannelId") or {}).get("value") == channel_id:
                return True
        token = r.get("nextPageToken")
        if not token:
            return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("channel")
    p.add_argument("video_id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max", type=int)
    a = p.parse_args()
    ch = channel(a.channel)
    cfg = load_config()
    limit = a.max or cfg["quota"]["max_replies_per_channel_per_run"]

    done_path = HERE / "replied.json"
    done = set(read_json(done_path, []))

    yt = get_service(a.channel)
    comments = fetch_comments(yt, a.video_id)
    todo, skipped = [], []
    for c in sorted(comments, key=lambda c: c["likes"], reverse=True):
        if c["id"] in done or c["author_id"] == ch["id"]:
            continue
        if c.get("reply_count") and already_replied(yt, c["id"], ch["id"]):
            done.add(c["id"])
            continue
        reason = needs_review(c["text"])
        if reason:
            skipped.append((c, reason))
            continue
        todo.append(c)

    sent = 0
    for c in todo[:limit]:
        msg = pick_reply(c["id"], c["text"])
        print(f"{'(test) ' if a.dry_run else ''}↳ « {c['text'][:60]} »  →  {msg}")
        if not a.dry_run:
            yt.comments().insert(part="snippet", body={"snippet": {"parentId": c["id"], "textOriginal": msg}}).execute()
            done.add(c["id"])
            sent += 1
    if not a.dry_run:
        write_json(done_path, sorted(done))
    print(f"\n{ch['name']} : {sent} réponse(s) envoyée(s), {max(0, len(todo) - limit)} en attente (limite), "
          f"{len(skipped)} mis de côté pour Moha.")
    for c, r in skipped:
        print(f"  ⚠ [{r}] {c['author']}: {c['text'][:80]}")


if __name__ == "__main__":
    main()
