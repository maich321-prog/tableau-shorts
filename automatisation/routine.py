"""Routine du jour, en une commande, pour les 4 chaînes :
  1. trouve le dernier Short publié de chaque chaîne ;
  2. compte le vote (sauf Villes : pas de vote) → votes/<chaîne>/jour-N.json ;
  3. répond aux commentaires (sauf --sans-reponses) ;
  4. écrit un résumé dans votes/resume-<date>.md.

Usage :
  python routine.py                 (tout)
  python routine.py --test          (rien n'est envoyé, on affiche seulement)
  python routine.py --sans-reponses (seulement les votes)
"""
import argparse
import datetime as dt
import re
import subprocess
import sys

from common import HERE, ROOT, get_service, load_config, write_json
from logic import needs_review, tally, top_free_answers
from votes import fetch_comments

NO_VOTE = {"villes"}


def latest_public_video(yt, channel_id):
    uploads = "UU" + channel_id[2:]
    r = yt.playlistItems().list(part="contentDetails,snippet", playlistId=uploads, maxResults=10).execute()
    for it in r.get("items", []):
        vid = it["contentDetails"]["videoId"]
        v = yt.videos().list(part="status,snippet", id=vid).execute()["items"]
        if v and v[0]["status"]["privacyStatus"] == "public":
            return vid, v[0]["snippet"]["title"]
    return None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test", action="store_true")
    p.add_argument("--sans-reponses", action="store_true")
    a = p.parse_args()
    cfg = load_config()
    ours = {c["id"] for c in cfg["channels"].values()}
    today = dt.date.today().isoformat()
    lines = [f"# Routine du {today}", ""]

    for key, ch in cfg["channels"].items():
        yt = get_service(key)
        vid, title = latest_public_video(yt, ch["id"])
        if not vid:
            lines.append(f"- **{ch['name']}** : aucun Short public pour l'instant.")
            continue
        m = re.search(r"Day\s+(\d+)", title or "", re.I)
        jour = int(m.group(1)) if m else 0
        comments = [c for c in fetch_comments(yt, vid) if c["author_id"] not in ours]
        review = [c for c in comments if needs_review(c["text"])]
        if key in NO_VOTE:
            res = {"type": "sans vote", "top_answers": top_free_answers(comments, 5)}
            vote_txt = f"{len(comments)} commentaires"
        else:
            res = {"type": "A/B", **tally(comments), "top_answers": top_free_answers(comments, 5)}
            vote_txt = f"A = {res['A']} · B = {res['B']} → **{res['winner']}**"
        res.update(channel=ch["name"], video_id=vid, title=title, jour=jour, total_comments=len(comments),
                   to_review=[{"author": c["author"], "text": c["text"], "reason": needs_review(c["text"])} for c in review])
        if not a.test:
            write_json(ROOT / "votes" / key / f"jour-{jour}.json", res)
        lines.append(f"- **{ch['name']}** (jour {jour}) : {vote_txt} · {len(review)} à vérifier par Moha")
        for c in review[:5]:
            lines.append(f"  - ⚠ {c['author']} : {c['text'][:100]}")

        if not a.sans_reponses:
            cmd = [sys.executable, str(HERE / "reply.py"), key, vid] + (["--dry-run"] if a.test else [])
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=HERE).stdout
            last = [l for l in out.splitlines() if "réponse(s)" in l]
            lines.append(f"  - réponses : {last[0].split(':', 1)[1].strip() if last else out.strip()[-120:]}")

    text = "\n".join(lines)
    print(text)
    if not a.test:
        (ROOT / "votes").mkdir(exist_ok=True)
        (ROOT / "votes" / f"resume-{today}.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
