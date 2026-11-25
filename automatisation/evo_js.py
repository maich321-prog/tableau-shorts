"""Graphiques d'évolution (JS dans la page).
- « Normal » (par défaut) : du premier au dernier point, valeurs totales, zoom sur la courbe.
- 12h / 1j / 7j / 15j / 30j : axe gradué fixe, courbe = gain depuis le début de la période.
Chaque graphique a sa propre échelle (graduations « rondes » adaptées : vues, abonnés, likes, commentaires).
"""

EVO_JS = r"""
<script>
(function(){
const H = JSON.parse(document.getElementById('hist-data').textContent); // [[t_ms, vues, abonnés, likes, coms], ...]
const M = [["Vues",1],["Abonnés",2],["J'aime",3],["Commentaires",4]];
const R = {"normal":"depuis le début","12h":"12 h","1j":"1 jour","7j":"7 jours","15j":"15 jours","30j":"30 jours"};
let cur = "normal";
try { const s = localStorage.getItem("evo-range2"); if (R[s]) cur = s; } catch(e) {}
const fmt = n => Math.round(n).toLocaleString("fr-FR");
const short = n => Math.abs(n) >= 1e6 ? (n/1e6).toLocaleString("fr-FR",{maximumFractionDigits:1})+" M" : Math.abs(n) >= 1e4 ? Math.round(n/1e3)+" k" : fmt(n);
const pad = n => String(n).padStart(2,"0");
function niceStep(range){ // pas « rond » : 1, 2, 5, 10, 20, 50...
  const raw = Math.max(range, 1) / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return Math.max(1, (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p);
}
function bounds(r){
  const now = new Date(), d0 = new Date(now); d0.setHours(0,0,0,0);
  if (r === "normal") {
    const S = H.length ? H[0][0] : now.getTime() - 3600e3, E = Math.max(H.length ? H[H.length-1][0] : now.getTime(), S + 3600e3);
    const span = (E - S) / 3600e3;
    return [new Date(S), new Date(E), span <= 36 ? Math.max(1, Math.ceil(span/6)) : Math.max(1, Math.ceil(span/24/6)), span <= 36 ? "h" : "d", true];
  }
  if (r === "12h") { const s = new Date(d0); if (now.getHours() >= 12) s.setHours(12); const e = new Date(s); e.setHours(s.getHours()+12); return [s,e,2,"h",false]; }
  if (r === "1j") { const e = new Date(d0); e.setDate(e.getDate()+1); return [d0,e,3,"h",false]; }
  const n = parseInt(r), s = new Date(d0); s.setDate(s.getDate()-(n-1)); const e = new Date(d0); e.setDate(e.getDate()+1);
  return [s,e, n===7?1:(n===15?2:5), "d", false];
}
function ticks(s,e,step,unit,auto){
  const out = [], t = new Date(s);
  if (auto) { if (unit==="h") t.setMinutes(0,0,0), t.setHours(t.getHours()+1); else t.setHours(0,0,0,0), t.setDate(t.getDate()+1); }
  while (t.getTime() <= e.getTime()) {
    const isEnd = t.getTime() === e.getTime() && !auto;
    let txt = unit==="h" ? (isEnd && t.getHours()===0 ? "24h" : pad(t.getHours())+"h") : pad(t.getDate())+"/"+pad(t.getMonth()+1);
    if (auto && unit==="h" && t.getHours()===0) txt = pad(t.getDate())+"/"+pad(t.getMonth()+1);
    out.push([t.getTime(), txt]);
    if (unit==="h") t.setHours(t.getHours()+step); else t.setDate(t.getDate()+step);
  }
  return out;
}
function draw(){
  const [s,e,step,unit,auto] = bounds(cur), S = s.getTime(), E = e.getTime();
  const W=600, Hh=200, L=46, Rm=14, T=12, B=26, now = Date.now();
  document.querySelectorAll(".rg button").forEach(b => b.classList.toggle("on", b.dataset.r===cur));
  const from = auto ? "le début du suivi" : unit==="h" ? (s.getHours()===0 ? "minuit" : "midi") : "le " + pad(s.getDate())+"/"+pad(s.getMonth()+1);
  document.getElementById("evo-sub").textContent = (auto ? "Totaux, " : "Gagné depuis " + from + " · ") + "période : " + R[cur];
  let html = "";
  for (const [lab, k] of M) {
    let pts = [], base = 0;
    if (auto) {
      pts = H.map(p => [p[0], p[k]]);
      base = pts.length ? pts[0][1] : 0;
    } else {
      const before = H.filter(p => p[0] <= S), inside = H.filter(p => p[0] > S && p[0] <= E);
      base = before.length ? before[before.length-1][k] : (inside.length ? inside[0][k] : 0);
      if (before.length) pts.push([S, 0]);
      for (const p of inside) pts.push([p[0], p[k]-base]);
    }
    const last = H.length ? H[H.length-1][k] : 0;
    const gain = pts.length ? (auto ? pts[pts.length-1][1] - pts[0][1] : pts[pts.length-1][1]) : 0;
    // échelle propre à CE graphique : on zoome sur ses valeurs, graduations rondes
    const vals = pts.map(p => p[1]);
    let vmin = vals.length ? Math.min(...vals) : 0, vmax = vals.length ? Math.max(...vals) : 1;
    if (!auto) vmin = Math.min(0, vmin);
    const st = niceStep(vmax - vmin);
    let lo = Math.floor(vmin / st) * st, hi = Math.ceil(vmax / st) * st;
    if (vmax === vmin) { lo = vmin - st; hi = vmax + st; }  // valeur qui ne bouge pas : ligne au milieu
    if (hi === lo) hi = lo + st;
    if (hi - vmax < st * 0.15) hi += st;
    if (auto && lo < 0) lo = 0;
    const X = t => L + (W-L-Rm)*(t-S)/((E-S)||1), Y = v => T + (Hh-T-B)*(1-(v-lo)/((hi-lo)||1));
    let g = "";
    for (let v = lo; v <= hi + 1e-9; v += st) {
      const y = Y(v).toFixed(1);
      g += `<line x1="${L}" x2="${W-Rm}" y1="${y}" y2="${y}" stroke="#ffffff" stroke-opacity="${v===0 && !auto ? .22 : .07}"/>`;
      g += `<text x="${L-8}" y="${(+y+4).toFixed(1)}" text-anchor="end" class="tk">${auto ? short(v) : (v>0?"+":"")+short(v)}</text>`;
    }
    for (const [t,txt] of ticks(s,e,step,unit,auto)) {
      const x = X(t).toFixed(1);
      g += `<line x1="${x}" x2="${x}" y1="${T}" y2="${Hh-B}" stroke="#ffffff" stroke-opacity=".05"/>`;
      const anchor = t===S ? "start" : (t===E ? "end" : "middle");
      g += `<text x="${x}" y="${Hh-8}" text-anchor="${anchor}" class="tk">${txt}</text>`;
    }
    if (!auto && now > S && now < E) g += `<line x1="${X(now).toFixed(1)}" x2="${X(now).toFixed(1)}" y1="${T}" y2="${Hh-B}" stroke="#4ade80" stroke-opacity=".55" stroke-dasharray="3 4"/>`;
    if (pts.length >= 2) {
      const line = pts.map(p => X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join(" ");
      const yb = Y(lo).toFixed(1);
      const a = `${X(pts[0][0]).toFixed(1)},${yb} ${line} ${X(pts[pts.length-1][0]).toFixed(1)},${yb}`;
      g += `<polygon points="${a}" fill="url(#ga)"/><polyline points="${line}" fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
      const lp = pts[pts.length-1];
      g += `<circle cx="${X(lp[0]).toFixed(1)}" cy="${Y(lp[1]).toFixed(1)}" r="5" fill="#fff"/>`;
    } else {
      g += `<text x="${(L+W-Rm)/2}" y="${(Hh-B)/2+T}" text-anchor="middle" class="tk">pas encore assez de points sur cette période</text>`;
    }
    const cls = gain >= 0 ? "up" : "down";
    html += `<div class="chart"><div class="ch-h"><span>${lab}</span><b>${fmt(last)}</b><em class="${cls}">${gain>=0?"+":"−"}${fmt(Math.abs(gain))}</em></div>`
      + `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" role="img" aria-label="${lab} : ${gain>=0?"+":"−"}${fmt(Math.abs(gain))}, ${R[cur]}">`
      + `<defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".2"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>${g}</svg></div>`;
  }
  document.getElementById("charts").innerHTML = html;
}
document.querySelectorAll(".rg button").forEach(b => b.addEventListener("click", () => {
  cur = b.dataset.r; try { localStorage.setItem("evo-range2", cur); } catch(e) {} draw();
}));
draw();
})();
</script>
"""
