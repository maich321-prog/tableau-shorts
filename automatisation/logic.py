"""Logique pure (sans internet) : lire un vote dans un commentaire, filtrer, choisir une réponse.
Testée par test_logic.py.
"""
import hashlib
import re

# ---------- Filtre RÈGLE N°1 / insultes / sujets sensibles ----------
# Un commentaire qui contient un de ces mots n'est NI compté comme réponse libre retenue,
# NI répondu automatiquement : il est mis de côté pour Moha.
FLAG_WORDS = [
    # insultes
    "fuck", "shit", "bitch", "bastard", "idiot", "stupid", "retard", "dumb", "loser", "kys", "kill yourself",
    "whore", "slut", "nigg", "fag", "cunt", "dick", "pussy",
    # haram comme « solution » (RÈGLE N°1, point 4)
    "bet ", "betting", "casino", "gamble", "gambling", "lottery", "loan", "interest rate", "steal", "rob ",
    "robbery", "drug", "weed", "alcohol", "beer", "vodka", "drunk", "girlfriend", "date her", "sex", "nude",
    "crypto signal", "scam",
    # religion / sujets sensibles → Moha décide
    "allah", "god", "jesus", "islam", "muslim", "christian", "jew", "religion", "haram", "halal",
    "politic", "israel", "palestin", "war", "suicide", "self harm",
]

URL_RE = re.compile(r"https?://|www\.", re.I)
# Racines à repérer en début de mot (nigg…, politic…, palestin…, drug…, gambl…)
PREFIXES = {"nigg", "fag", "politic", "palestin", "drug", "gambl", "muslim", "christian"}
_FLAG_RES = [(w.strip(), re.compile(r"\b" + re.escape(w.strip()) + (r"" if w.strip() in PREFIXES else r"\b"), re.I))
             for w in FLAG_WORDS]


def needs_review(text):
    if URL_RE.search(text):
        return "lien"
    for w, rx in _FLAG_RES:
        if rx.search(text):
            return w
    return None


# ---------- Lecture d'un vote A/B ----------
# On compte A ou B seulement quand c'est clair : « A », « B!! », « option A », « team b 🔥 »,
# « I vote A », « A) », « 🅰️ ». Le mot anglais « a » au milieu d'une phrase ne compte pas.
_EMOJI = {"🅰": "A", "🅱": "B"}
_LEAD = r"(?:option|vote|voting|team|choice|choose|pick|go(?:ing)?\s+(?:with|for)|i\s+(?:pick|choose|vote(?:\s+for)?|say))"
_PATTERNS = [
    re.compile(r"^\W*([AB])\W*$", re.I),                                  # « A » / « b!! »
    re.compile(rf"\b{_LEAD}\s*[:\-]?\s*([AB])\b", re.I),                  # « option A », « I vote b »
    re.compile(r"(?:^|\s)([AB])\s*[\)\]:!]", ),                             # « A) » « B! » (majuscule)
    re.compile(r"(?:^|\s)([AB])(?=\s|$|[?!.,;])"),                          # « A » isolé en MAJUSCULE
]


def parse_vote(text):
    """Retourne 'A', 'B' ou None (pas clair / les deux)."""
    for e, v in _EMOJI.items():
        if e in text:
            other = "B" if v == "A" else "A"
            if any(o in text for o, w in _EMOJI.items() if w == other):
                return None
            return v
    found = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(1).upper())
    if len(found) == 1:
        return found.pop()
    return None


def tally(comments):
    """comments : liste de dicts {author_id, text, likes, published}.
    1 vote par personne (son commentaire le plus récent qui contient un vote clair)."""
    latest = {}
    for c in sorted(comments, key=lambda c: c["published"]):
        v = parse_vote(c["text"])
        if v:
            latest[c["author_id"]] = v
    a = sum(1 for v in latest.values() if v == "A")
    b = sum(1 for v in latest.values() if v == "B")
    winner = "A" if a > b else "B" if b > a else "égalité"
    return {"A": a, "B": b, "voters": len(latest), "winner": winner}


def top_free_answers(comments, n=10):
    """Vote libre : les réponses les plus likées, sans celles à vérifier (insulte, haram…)."""
    ok = [c for c in comments if not needs_review(c["text"])]
    ok.sort(key=lambda c: c["likes"], reverse=True)
    return [{"text": c["text"], "likes": c["likes"], "author": c.get("author", "")} for c in ok[:n]]


# ---------- Réponses courtes et variées (en anglais, halal, sans promesse) ----------
REPLIES_A = ["Team A 🔥", "A it is? 👀", "Bold pick! 💪", "A gang where you at? 🙌", "Solid choice 👊", "We'll see if A wins 👀🔥", "A for the win? 💯"]
REPLIES_B = ["Team B 🔥", "B it is? 👀", "Smart pick 🧠", "B gang where you at? 🙌", 
             "Big brain move 💡", "We'll see if B wins 👀🔥", "B for the win? 💯"]
REPLIES_OTHER = ["🔥🔥", "Love this 🙌", "Facts 💯", "Good one 😂", "Thanks for watching! 🙏",
                 "Stay tuned for tomorrow 👀", "Appreciate you 🙏🔥", "Great idea 💡"]


# Si l'épisode n'a pas ses propres répliques : modèles qui citent le choix (on montre qu'on sait de quoi on parle)
TEMPLATES = ["{v}? {c}… you sure? 😅", "Team {v} 🔥 {c}, let's see how that goes 👀", "{v}! {c}? Bold move 💪",
             "{c}… that's gonna be tough 😮‍💨 Team {v}?"]


def pick_reply(comment_id, text, ep=None):
    """Choisit une réponse stable (même commentaire → même réponse) mais variée d'un commentaire à l'autre.
    ep = infos de l'épisode : {"replies": {"A": [...], "B": [...]}, "choices": {"A": "...", "B": "..."}}"""
    v = parse_vote(text)
    ep = ep or {}
    if v in ("A", "B") and ep.get("replies", {}).get(v):
        pool = ep["replies"][v]
    elif v in ("A", "B") and ep.get("choices", {}).get(v):
        c = ep["choices"][v].rstrip(".")
        pool = [t.format(v=v, c=c) for t in TEMPLATES]
    else:
        pool = REPLIES_A if v == "A" else REPLIES_B if v == "B" else REPLIES_OTHER
    h = int(hashlib.sha1(comment_id.encode()).hexdigest(), 16)
    return pool[h % len(pool)]
