"""Lire TOUS les commentaires d'un Short et compter le vote.

Usage :
  python votes.py malik <video_id> --jour 1            (vote A/B)
  python votes.py malik <video_id> --jour 4 --libre    (vote libre : top des réponses likées)

Résultat écrit dans votes/<chaîne>/jour-N.json (à la racine du projet).
Coût : 1 unité de quota par page de 100 commentaires.
"""
import argparse
import datetime as dt

from common import ROOT, channel, get_service, write_json
from logic import needs_review, tally, top_free_answers


def fetch_comments(yt, video_id):
    out, token = [], None
    while True:
        r = yt.commentThreads().list(part="snippet", videoId=video_id, maxResults=100,
                                     order="time", textFormat="plainText", pageToken=token).execute()
        for it in r.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            out.append({
                "id": it["snippet"]["topLevelComment"]["id"],
                "author": s.get("authorDisplayName", ""),
                "author_id": (s.get("authorChannelId") or {}).get("value", s.get("authorDisplayName", "")),
                "text": s.get("textDisplay", ""),
                "likes": s.get("likeCount", 0),
                "published": s.get("publishedAt", ""),
                "reply_count": it["snippet"].get("totalReplyCount", 0),
            })
        token = r.get("nextPageToken")
        if not token:
            return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("channel")
    p.add_argument("video_id")
    p.add_argument("--jour", type=int, required=True)
    p.add_argument("--libre", action="store_true")
    a = p.parse_args()
    ch = channel(a.channel)

    yt = get_service(a.channel)
    comments = fetch_comments(yt, a.video_id)
    # nos propres chaînes ne votent pas
    ours = {c["id"] for c in __import__("common").load_config()["channels"].values()}
    comments = [c for c in comments if c["author_id"] not in ours]
    result = {
        "channel": ch["name"], "video_id": a.video_id, "jour": a.jour,
        "read_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "total_comments": len(comments),
        "to_review": [{"author": c["author"], "text": c["text"], "reason": needs_review(c["text"])}
                      for c in comments if needs_review(c["text"])],
    }
    if a.libre:
        result["type"] = "libre"
        result["top_answers"] = top_free_answers(comments)
        print(f"{ch['name']} jour {a.jour} : {len(comments)} commentaires. Top réponses (halal à vérifier par la discussion de la chaîne) :")
        for t in result["top_answers"][:5]:
            print(f"  {t['likes']:>4} ❤  {t['text'][:80]}")
    else:
        result["type"] = "A/B"
        result.update(tally(comments))
        print(f"{ch['name']} jour {a.jour} : A = {result['A']} · B = {result['B']} "
              f"({result['voters']} votants, {len(comments)} commentaires) → gagnant : {result['winner']}")
    if result["to_review"]:
        print(f"  ⚠ {len(result['to_review'])} commentaire(s) mis de côté pour Moha (insulte / sujet sensible / lien).")

    write_json(ROOT / "votes" / a.channel / f"jour-{a.jour}.json", result)
    print(f"  → votes/{a.channel}/jour-{a.jour}.json")


if __name__ == "__main__":
    main()
