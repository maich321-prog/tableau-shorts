"""Tableau de bord des 4 chaînes → Tableau-de-bord.html (à la racine du projet).

Usage : python stats.py          (lit l'API, écrit la page, l'ouvre)
        python stats.py --no-open
Coût : quelques unités de quota seulement (lecture).
"""
import base64
import datetime as dt
import html
import pathlib
import re
import sys
import webbrowser
from zoneinfo import ZoneInfo

from common import HERE, ROOT, TOKENS, get_service, load_config
from logic import tally
from votes import fetch_comments
from evo_js import EVO_JS

LOOK = {
    "malik": {"c": "#ff7a1a", "c2": "#e63946", "logo": "chaines/fight-for-mama/logo.png", "days": 30},
    "jace": {"c": "#22c55e", "c2": "#0ea5a4", "logo": "chaines/25k-or-nothing/logo.png", "days": 60},
    "kai": {"c": "#a855f7", "c2": "#6366f1", "logo": "chaines/zero-to-million-kai/logo.png", "days": 90},
    "villes": {"c": "#3b82f6", "c2": "#06b6d4", "logo": "chaines/strange-rule-towns/logo.png", "days": 0},
}
NO_VOTE = {"villes"}
BXL = ZoneInfo("Europe/Brussels")
e = html.escape


def n(x):
    x = int(x or 0)
    if x >= 1_000_000:
        return f"{x/1_000_000:.1f}".rstrip("0").rstrip(".") + " M"
    if x >= 10_000:
        return f"{x/1000:.1f}".rstrip("0").rstrip(".") + " k"
    return f"{x:,}".replace(",", " ")


def local(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BXL)


def retention(key):
    """Rétention par vidéo (YouTube Analytics). Les chiffres arrivent avec 1 à 2 jours de retard."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(str(TOKENS / f"token-{key}.json"))
        ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        r = ya.reports().query(ids="channel==MINE", startDate="2026-11-01", endDate=dt.date.today().isoformat(),
                               metrics="views,averageViewDuration,averageViewPercentage", dimensions="video",
                               sort="-views", maxResults=200).execute()
        return {row[0]: {"v": row[1], "dur": row[2], "pct": row[3]} for row in r.get("rows", [])}
    except Exception as ex:
        print(f"[{key}] rétention indisponible : {str(ex)[:120]}")
        return {}


def choices(day):
    """Textes des choix A et B, lus dans episodes/jour-N.json."""
    f = HERE / "episodes" / f"jour-{day}.json"
    out = {}
    if day and f.exists():
        import json
        for k, ep in json.loads(f.read_text(encoding="utf-8")).items():
            a = re.search(r"^A\)\s*(.+)$", ep.get("description", ""), re.M)
            b = re.search(r"^B\)\s*(.+)$", ep.get("description", ""), re.M)
            if a and b:
                out[k] = (a.group(1).strip(), b.group(1).strip())
    return out


def goal(x):
    g = 1000
    while x >= g:
        g *= 10
    return g


def collect(key, ch, ours):
    yt = get_service(key)
    c = yt.channels().list(part="statistics,snippet", id=ch["id"]).execute()["items"][0]
    st = c["statistics"]
    items = yt.playlistItems().list(part="contentDetails", playlistId="UU" + ch["id"][2:], maxResults=50).execute().get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    vids = []
    if ids:
        for v in yt.videos().list(part="snippet,statistics,status", id=",".join(ids)).execute().get("items", []):
            s, sn, stt = v.get("statistics", {}), v["snippet"], v["status"]
            m = re.search(r"Day\s+(\d+)", sn["title"], re.I)
            vids.append({
                "id": v["id"], "title": sn["title"], "day": int(m.group(1)) if m else None,
                "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)), "privacy": stt["privacyStatus"],
                "publishAt": stt.get("publishAt"), "published": sn["publishedAt"],
            })
    ret = retention(key)
    for v in vids:
        v["ret"] = ret.get(v["id"])
    vids.sort(key=lambda v: v["publishAt"] or v["published"], reverse=True)
    rv = sum(r["v"] for r in ret.values())
    ret_pct = sum(r["pct"] * r["v"] for r in ret.values()) / rv if rv else None
    vote = None
    pub = [v for v in vids if v["privacy"] == "public"]
    if key not in NO_VOTE and pub:
        coms = [x for x in fetch_comments(yt, pub[0]["id"]) if x["author_id"] not in ours]
        vote = {**tally(coms), "day": pub[0]["day"], "choices": choices(pub[0]["day"]).get(key)}
    return {
        "key": key, "name": ch["name"], "handle": ch["handle"],
        "subs": int(st.get("subscriberCount", 0)), "views": max(int(st.get("viewCount", 0)), sum(v["views"] for v in vids)),
        "videos": vids, "vote": vote, "ret": ret_pct,
        "likes": sum(v["likes"] for v in vids), "comments": sum(v["comments"] for v in vids),
        "public": len(pub), "scheduled": sum(1 for v in vids if v["privacy"] != "public" and v["publishAt"]),
    }


HIST = HERE / "historique.json"
METRICS = [("views", "Vues"), ("subs", "Abonnés"), ("likes", "J'aime"), ("comments", "Commentaires")]


def update_history(data):
    """Ajoute un point (chaque mise à jour) dans historique.json et renvoie tout l'historique."""
    import json
    hist = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    now = dt.datetime.now(dt.timezone.utc)
    point = {"t": now.isoformat(timespec="minutes"),
             "ch": {d["key"]: {k: d[k] for k, _ in METRICS} for d in data}}
    if hist and (now - dt.datetime.fromisoformat(hist[-1]["t"])).total_seconds() < 600:
        hist[-1] = point  # deux mises à jour très proches : on garde la dernière
    else:
        hist.append(point)
    hist = hist[-5000:]
    HIST.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    return hist


def hist_json(hist):
    """Historique compact pour la page : [temps_ms, vues, abonnés, likes, commentaires] (total des chaînes)."""
    import json
    rows = []
    for h in hist or []:
        t = int(dt.datetime.fromisoformat(h["t"]).timestamp() * 1000)
        rows.append([t] + [sum(v.get(k, 0) for v in h["ch"].values()) for k, _ in METRICS])
    return json.dumps(rows, separators=(",", ":"))


def chart(hist, metric, label, order):
    """Petit graphique SVG : total (blanc) + une ligne par chaîne (sa couleur)."""
    W, H, P = 600, 170, 6
    if len(hist) < 2:
        return (f'<div class="chart"><div class="ch-h"><span>{label}</span></div>'
                '<div class="muted" style="padding:30px 0;text-align:center">Le graphique se remplit à chaque mise à jour ⏳</div></div>')
    ts = [dt.datetime.fromisoformat(h["t"]).timestamp() for h in hist]
    t0, t1 = ts[0], ts[-1] or ts[0] + 1
    tot = [sum(v.get(metric, 0) for v in h["ch"].values()) for h in hist]
    lo, hi = min(tot), max(tot)
    pad = max((hi - lo) * 0.15, 1)
    lo, hi = max(0, lo - pad), hi + pad  # zoom sur la courbe : on voit bien la progression
    def xy(i, v):
        x = P + (W - 2 * P) * ((ts[i] - t0) / ((t1 - t0) or 1))
        y = H - P - (H - 2 * P) * ((v - lo) / ((hi - lo) or 1))
        return f"{x:.1f},{y:.1f}"
    lines = []
    tl = " ".join(xy(i, v) for i, v in enumerate(tot))
    area = f'{P},{H - P} {tl} {W - P},{H - P}'
    gid = f"g{metric}"
    diff = tot[-1] - tot[0]
    sign = "+" if diff >= 0 else "−"
    d0 = dt.datetime.fromtimestamp(t0, BXL)
    d1 = dt.datetime.fromtimestamp(t1, BXL)
    return (f'<div class="chart"><div class="ch-h"><span>{label}</span><b>{n(tot[-1])}</b>'
            f'<em class="{"up" if diff >= 0 else "down"}">{sign}{n(abs(diff))}</em></div>'
            f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="Évolution : {label}">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".18"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#{gid})"/>{"".join(lines)}'
            f'<polyline points="{tl}" fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round"/></svg>'
            f'<div class="ch-x"><span>{d0:%d/%m %Hh%M}</span><span>{d1:%d/%m %Hh%M}</span></div></div>')


def vote_html(v, color):
    if not v:
        return '<div class="vote muted">Pas de vote sur cette chaîne : commentaires libres.</div>'
    a, b = v["A"], v["B"]
    tot = a + b
    ch = v.get("choices") or ("", "")
    rows = []
    for L, cnt, txt in (("A", a, ch[0]), ("B", b, ch[1])):
        pct = round(100 * cnt / tot) if tot else 0
        win = tot and cnt == max(a, b) and a != b
        rows.append(f"""<div class="opt{' win' if win else ''}">
        <div class="ot"><span class="L">{L}</span><span class="tx">{e(txt) or 'Choix ' + L}</span><b>{cnt}</b></div>
        <div class="bar thin"><i style="width:{pct}%;background:{color}"></i></div>
        <div class="op">{pct} %{' · en tête 🏆' if win else ''}</div></div>""")
    return f"""<div class="vote">
      <div class="vh"><span>🗳️ Vote du jour {v['day'] or '?'}</span><b>{tot} vote{'s' if tot != 1 else ''}</b></div>
      {''.join(rows)}
    </div>"""


def video_rows(vids):
    if not vids:
        return '<div class="muted">Aucun Short pour l\'instant.</div>'
    out = []
    for v in vids[:8]:
        if v["privacy"] == "public":
            tag = f'<span class="tag on">en ligne · {local(v["published"]):%d/%m}</span>'
        elif v["publishAt"]:
            tag = f'<span class="tag soon">programmé · {local(v["publishAt"]):%d/%m %Hh%M}</span>'
        else:
            tag = '<span class="tag off">privé</span>'
        label = f"Jour {v['day']}" if v["day"] else "Épisode"
        out.append(f"""<a class="vid" href="https://youtube.com/shorts/{v['id']}" target="_blank">
        <div class="vt"><b>{label}</b>{tag}</div>
        <div class="vn">{e(v['title'])}</div>
        <div class="vs"><span>👁 {n(v['views'])}</span><span>👍 {n(v['likes'])}</span><span>💬 {n(v['comments'])}</span>{f"<span>⏱ {v['ret']['pct']:.0f} %</span>" if v.get('ret') else ''}</div></a>""")
    return "\n".join(out)


def monet(d, color):
    """Objectif monétisation (pubs) de la chaîne : 1 000 abonnés + vues Shorts des 90 derniers jours."""
    today = dt.datetime.now(dt.timezone.utc)
    goal_v = 10_000_000 if today < dt.datetime(2027, 2, 1, tzinfo=dt.timezone.utc) else 20_000_000
    v90 = sum(v["views"] for v in d["videos"]
              if (today - dt.datetime.fromisoformat((v["publishAt"] or v["published"]).replace("Z", "+00:00"))).days < 90
              and v["privacy"] == "public")
    rows = []
    for lab, val, goal_ in (("Abonnés", d["subs"], 1000), ("Vues Shorts (90 j)", v90, goal_v)):
        pct = min(100, 100 * val / goal_)
        ok = " ✅" if val >= goal_ else ""
        rows.append(f'<div class="mo"><div class="ph"><span>{lab}</span><b>{n(val)} <small>/ {n(goal_)}{ok}</small></b></div>'
                    f'<div class="bar thin"><i style="width:{pct:.2f}%;min-width:4px;background:{color}"></i></div>'
                    f'<div class="op">{pct:.2f} %</div></div>')
    note = "" if goal_v == 20_000_000 else '<div class="op">⚠ 20 M vues dès le 01/02/2027</div>'
    return f'<div class="vote"><div class="ph"><span>💰 Objectif monétisation</span></div>{"".join(rows)}{note}</div>'


def column(d):
    lk = LOOK[d["key"]]
    days = lk["days"]
    last_day = max([v["day"] for v in d["videos"] if v["day"] and v["privacy"] == "public"], default=0)
    prog = (f'<div class="prog"><div class="ph"><span>Progression</span><b>Jour {last_day}/{days}</b></div>'
            f'<div class="bar thin"><i style="width:{100*last_day/days:.1f}%;background:linear-gradient(90deg,{lk["c"]},{lk["c2"]})"></i></div></div>'
            if days else f'<div class="prog"><div class="ph"><span>Villes visitées</span><b>{d["public"]}</b></div></div>')
    logo = ROOT / lk["logo"]
    src = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo.exists() else ""
    return f"""<section class="col" style="--c:{lk['c']};--c2:{lk['c2']}">
  <header>
    <img src="{src}" alt="">
    <div><h2>{e(d['name'])}</h2><a href="https://youtube.com/{e(d['handle'])}" target="_blank">{e(d['handle'])}</a></div>
  </header>
  <div class="big"><span>Abonnés</span><b>{n(d['subs'])}</b></div>
  <div class="tiles">
    <div><span>Vues</span><b>{n(d['views'])}</b></div>
    <div><span>J'aime</span><b>{n(d['likes'])}</b></div>
    <div><span>Commentaires</span><b>{n(d['comments'])}</b></div>
    <div><span>Rétention moy.</span><b>{f"{d['ret']:.0f} %" if d['ret'] is not None else '<small>dans 1-2 j</small>'}</b></div>
  </div>
  {monet(d, lk['c'])}
  {prog}
  {vote_html(d['vote'], lk['c'])}
  <h3>Shorts</h3>
  <div class="vids">{video_rows(d['videos'])}</div>
</section>"""


def page(data, hist=None):
    T = {k: sum(d[k] for d in data) for k in ("subs", "views", "likes", "comments", "public", "scheduled")}
    share = "".join(
        f'<div class="sh"><span>{e(d["name"])}</span><div class="bar thin"><i style="width:{min(100, 100*d["views"]/goal(d["views"])):.1f}%;background:{LOOK[d["key"]]["c"]}"></i></div><b>{n(d["views"])} <small>/ {n(goal(d["views"]))}</small></b></div>'
        for d in data)
    now = dt.datetime.now(BXL)
    if "--out" in sys.argv:  # en ligne : GitHub démarre avec quelques minutes de retard → on affiche le créneau (h00 / h30)
        now = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Tableau de bord</title>
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#0b0d12">
<meta name="apple-mobile-web-app-title" content="Mes Shorts">
<meta name="apple-mobile-web-app-capable" content="yes">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0b0d12;--card:#141821;--card2:#1b2030;--line:#262c3d;--txt:#eef1f7;--mut:#8a93a8}}
*{{box-sizing:border-box;margin:0}}
body{{background:radial-gradient(1200px 600px at 10% -10%,#1d2340 0,transparent 60%),var(--bg);color:var(--txt);font-family:Inter,system-ui,sans-serif;padding:28px 16px 60px;min-height:100vh}}
.wrap{{max-width:1500px;margin:auto}}
.top{{display:flex;justify-content:space-between;align-items:end;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
h1{{font-size:28px;font-weight:800;letter-spacing:-.5px}} .upd{{color:var(--mut);font-size:13px}}
.total{{background:linear-gradient(135deg,#1a1f33,#151926);border:1px solid var(--line);border-radius:22px;padding:22px;display:grid;grid-template-columns:1.2fr 1fr;gap:24px;margin-bottom:22px}}
.total h2{{font-size:13px;text-transform:uppercase;letter-spacing:2px;color:var(--mut);margin-bottom:14px}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.kpis div{{background:#0f1320;border:1px solid var(--line);border-radius:14px;padding:14px}}
.kpis span,.tiles span,.big span{{display:block;color:var(--mut);font-size:12px;margin-bottom:4px}}
.kpis b{{font-size:26px;font-weight:800}}
.kpis .hero{{grid-column:span 3;background:linear-gradient(90deg,#ff7a1a22,#22c55e22,#a855f722,#3b82f622)}} .kpis .hero b{{font-size:40px}}
.sh{{display:grid;grid-template-columns:150px 1fr 105px;align-items:center;gap:10px;margin:10px 0;font-size:14px}} .sh b{{text-align:right}}
.cols{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.cols>*,.total>*{{min-width:0}}
.col{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--c);border-radius:20px;padding:18px;display:flex;flex-direction:column;gap:14px}}
.col header{{display:flex;gap:12px;align-items:center}}
.col header img{{width:54px;height:54px;border-radius:50%;border:2px solid var(--c)}}
.col h2{{font-size:17px;font-weight:800}} .col header a{{color:var(--mut);font-size:13px;text-decoration:none}}
.big{{background:linear-gradient(135deg,var(--c),var(--c2));border-radius:16px;padding:14px 16px}}
.big span{{color:#fff;opacity:.85}} .big b{{font-size:34px;font-weight:800}}
.tiles{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.tiles div{{background:var(--card2);border-radius:12px;padding:10px 12px}} .tiles b{{font-size:20px}} small{{font-size:11px;color:var(--mut);font-weight:600}}
.bar{{height:12px;background:#0f1320;border-radius:99px;overflow:hidden}} .bar.thin{{height:8px}} .bar i{{display:block;height:100%;border-radius:99px}}
.ph,.vh,.ab{{display:flex;justify-content:space-between;font-size:13px;color:var(--mut);margin-bottom:6px}} .ph b,.vh b{{color:var(--txt)}}
.vote{{background:var(--card2);border-radius:14px;padding:12px}} .ab{{margin:6px 0 0}} .ab .win{{color:var(--c);font-weight:800}}
.muted{{color:var(--mut);font-size:13px}}
.opt{{margin-top:10px}} .ot{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.ot .L{{flex:none;width:24px;height:24px;border-radius:7px;background:#0f1320;display:grid;place-items:center;font-weight:800;font-size:13px}}
.ot .tx{{flex:1;font-size:13px;color:var(--mut);line-height:1.25}} .ot b{{font-size:22px;font-weight:800}}
.opt.win .L{{background:var(--c);color:#fff}} .opt.win .tx{{color:var(--txt)}}
.op{{font-size:11px;color:var(--mut);margin-top:4px}}
.mo{{margin-top:8px}}
h3{{font-size:12px;text-transform:uppercase;letter-spacing:2px;color:var(--mut)}}
.vids{{display:flex;flex-direction:column;gap:8px}}
.vid{{display:block;background:var(--card2);border-radius:12px;padding:10px 12px;color:inherit;text-decoration:none;border:1px solid transparent;transition:.15s}}
.vid:hover{{border-color:var(--c)}}
.vt{{display:flex;justify-content:space-between;align-items:center;font-size:13px}}
.vn{{font-size:12px;color:var(--mut);margin:4px 0 6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.vs{{display:flex;gap:12px;font-size:13px}}
.tag{{font-size:11px;padding:2px 8px;border-radius:99px}} .tag.on{{background:#16a34a33;color:#4ade80}} .tag.soon{{background:#f59e0b33;color:#fbbf24}} .tag.off{{background:#64748b33;color:#94a3b8}}
.evo{{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:20px;margin-bottom:22px}}
.evo-h{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px}}
.leg{{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--mut)}} .leg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
.charts{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}
.chart{{background:#0f1320;border:1px solid var(--line);border-radius:14px;padding:12px 14px}}
.ch-h{{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}} .ch-h span{{color:var(--mut);font-size:13px;flex:1}} .ch-h b{{font-size:22px}}
.ch-h em{{font-style:normal;font-size:12px;font-weight:700;padding:2px 8px;border-radius:99px}} .ch-h .up{{background:#16a34a33;color:#4ade80}} .ch-h .down{{background:#ef444433;color:#f87171}}
.chart svg{{width:100%;height:190px;display:block;overflow:visible}} .chart svg .tk{{font-size:11px;fill:#8a93a8}}
.rg{{display:flex;gap:6px;flex-wrap:wrap}} .rg button{{background:#0f1320;color:var(--mut);border:1px solid var(--line);border-radius:99px;padding:6px 12px;font:600 13px Inter,system-ui,sans-serif;cursor:pointer}} .rg button.on{{background:#fff;color:#0b0d12;border-color:#fff}}
.ch-x{{display:flex;justify-content:space-between;font-size:11px;color:var(--mut);margin-top:4px}}
@media(max-width:760px){{.charts{{grid-template-columns:1fr}}}}
@media(max-width:1200px){{.cols{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:760px){{.cols,.total{{grid-template-columns:1fr}} .kpis{{grid-template-columns:1fr 1fr}} .kpis .hero{{grid-column:span 2}} .sh{{grid-template-columns:110px 1fr 56px}}}}
</style></head><body><div class="wrap">
<div class="top"><h1>📊 Tableau de bord · 4 chaînes</h1><div class="upd">Mis à jour le {now:%d/%m/%Y à %Hh%M}</div></div>
<div class="total">
  <div><h2>Total des 4 chaînes</h2><div class="kpis">
    <div class="hero"><span>Abonnés au total</span><b>{n(T['subs'])}</b></div>
    <div><span>Vues</span><b>{n(T['views'])}</b></div>
    <div><span>J'aime</span><b>{n(T['likes'])}</b></div>
    <div><span>Commentaires</span><b>{n(T['comments'])}</b></div>
  </div></div>
  <div><h2>Objectif de vues par chaîne</h2>{share}
    <div class="muted" style="margin-top:14px">{T['public']} Shorts en ligne{f" · {T['scheduled']} programmés" if T['scheduled'] else ''}</div></div>
</div>
<div class="evo"><div class="evo-h"><div><h2>Évolution · total des 4 chaînes</h2><div class="leg" id="evo-sub"></div></div>
<div class="rg">{''.join(f'<button data-r="{r}">{r}</button>' for r in ("12h", "1j", "7j", "15j", "30j"))}</div></div>
<div class="charts" id="charts"></div></div>
<script type="application/json" id="hist-data">{hist_json(hist)}</script>{EVO_JS}
<div class="cols">{''.join(column(d) for d in data)}</div>
</div></body></html>"""


def main():
    cfg = load_config()
    ours = {c["id"] for c in cfg["channels"].values()}
    data = [collect(k, ch, ours) for k, ch in cfg["channels"].items()]
    # chaîne la plus populaire d'abord : vues, puis abonnés, puis likes
    data.sort(key=lambda d: (d["views"], d["subs"], d["likes"]), reverse=True)
    hist = update_history(data)
    if "--out" in sys.argv:  # mode en ligne (GitHub) : un seul fichier, pas de navigateur
        out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(data, hist), encoding="utf-8")
        print(f"OK : {out}")
        return
    out = ROOT / "Tableau-de-bord.html"
    out.write_text(page(data, hist), encoding="utf-8")
    desk = ROOT.parent / "Tableau-de-bord.html"  # copie sur le Bureau
    desk.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"OK : {out}")
    if "--no-open" not in sys.argv:
        webbrowser.open(desk.as_uri())


if __name__ == "__main__":
    main()
