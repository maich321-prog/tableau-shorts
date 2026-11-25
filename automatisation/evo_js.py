"""Graphiques d'évolution (JS dans la page) : axe gradué fixe, gain depuis le début de la période."""

EVO_JS = r"""
<script>
(function(){
const H = JSON.parse(document.getElementById('hist-data').textContent); // [[t_ms, vues, abonnés, likes, coms], ...]
const M = [["Vues",1],["Abonnés",2],["J'aime",3],["Commentaires",4]];
const R = {"12h":"12 h","1j":"1 jour","7j":"7 jours","15j":"15 jours","30j":"30 jours"};
let cur = "1j";
try { const s = localStorage.getItem("evo-range"); if (R[s]) cur = s; } catch(e) {}
const fmt = n => Math.round(n).toLocaleString("fr-FR");
const pad = n => String(n).padStart(2,"0");
function bounds(r){
  const now = new Date(), d0 = new Date(now); d0.setHours(0,0,0,0);
  if (r === "12h") { const s = new Date(d0); if (now.getHours() >= 12) s.setHours(12); const e = new Date(s); e.setHours(s.getHours()+12); return [s,e,2,"h"]; }
  if (r === "1j") { const e = new Date(d0); e.setDate(e.getDate()+1); return [d0,e,3,"h"]; }
  const n = parseInt(r), s = new Date(d0); s.setDate(s.getDate()-(n-1)); const e = new Date(d0); e.setDate(e.getDate()+1);
  return [s,e, n===7?1:(n===15?2:5), "d"];
}
function ticks(s,e,step,unit){
  const out = [], t = new Date(s);
  while (t.getTime() <= e.getTime()) {
    const isEnd = t.getTime() === e.getTime();
    out.push([t.getTime(), unit==="h" ? (isEnd && t.getHours()===0 ? "24h" : pad(t.getHours())+"h") : pad(t.getDate())+"/"+pad(t.getMonth()+1)]);
    if (unit==="h") t.setHours(t.getHours()+step); else t.setDate(t.getDate()+step);
  }
  return out;
}
function draw(){
  const [s,e,step,unit] = bounds(cur), S = s.getTime(), E = e.getTime();
  const W=600, Hh=190, L=14, Rm=14, T=10, B=26, now = Date.now();
  document.querySelectorAll(".rg button").forEach(b => b.classList.toggle("on", b.dataset.r===cur));
  const from = unit==="h" ? (s.getHours()===0 ? "minuit" : "midi") : "le " + pad(s.getDate())+"/"+pad(s.getMonth()+1);
  document.getElementById("evo-sub").textContent = "Gagné depuis " + from + " · période : " + R[cur];
  let html = "";
  for (const [lab, k] of M) {
    const before = H.filter(p => p[0] <= S), inside = H.filter(p => p[0] > S && p[0] <= E);
    const base = before.length ? before[before.length-1][k] : (inside.length ? inside[0][k] : 0);
    const pts = [];
    if (before.length) pts.push([S, 0]);
    for (const p of inside) pts.push([p[0], p[k]-base]);
    const last = H.length ? H[H.length-1][k] : 0;
    const gain = pts.length ? pts[pts.length-1][1] : 0;
    let lo = Math.min(0, ...pts.map(p=>p[1])), hi = Math.max(1, ...pts.map(p=>p[1]));
    hi = hi + (hi-lo)*0.15;
    const X = t => L + (W-L-Rm)*(t-S)/(E-S), Y = v => T + (Hh-T-B)*(1-(v-lo)/(hi-lo));
    let g = "";
    for (const [t,txt] of ticks(s,e,step,unit)) {
      const x = X(t).toFixed(1);
      g += `<line x1="${x}" x2="${x}" y1="${T}" y2="${Hh-B}" stroke="#ffffff" stroke-opacity=".07"/>`;
      const anchor = t===S ? "start" : (t===E ? "end" : "middle");
      g += `<text x="${x}" y="${Hh-8}" text-anchor="${anchor}" class="tk">${txt}</text>`;
    }
    g += `<line x1="${L}" x2="${W-Rm}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="#ffffff" stroke-opacity=".18"/>`;
    if (now > S && now < E) g += `<line x1="${X(now).toFixed(1)}" x2="${X(now).toFixed(1)}" y1="${T}" y2="${Hh-B}" stroke="#4ade80" stroke-opacity=".5" stroke-dasharray="3 4"/>`;
    if (pts.length >= 2) {
      const line = pts.map(p => X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join(" ");
      const a = `${X(pts[0][0]).toFixed(1)},${Y(0).toFixed(1)} ${line} ${X(pts[pts.length-1][0]).toFixed(1)},${Y(0).toFixed(1)}`;
      g += `<polygon points="${a}" fill="url(#ga)"/><polyline points="${line}" fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
      const lp = pts[pts.length-1];
      g += `<circle cx="${X(lp[0]).toFixed(1)}" cy="${Y(lp[1]).toFixed(1)}" r="5" fill="#fff"/>`;
    } else {
      g += `<text x="${W/2}" y="${(Hh-B)/2+T}" text-anchor="middle" class="tk">pas encore assez de points sur cette période</text>`;
    }
    const cls = gain >= 0 ? "up" : "down";
    html += `<div class="chart"><div class="ch-h"><span>${lab}</span><b>${fmt(last)}</b><em class="${cls}">${gain>=0?"+":"−"}${fmt(Math.abs(gain))}</em></div>`
      + `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" role="img" aria-label="${lab} : ${gain>=0?"+":"−"}${fmt(Math.abs(gain))} sur ${R[cur]}">`
      + `<defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".2"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>${g}</svg></div>`;
  }
  document.getElementById("charts").innerHTML = html;
}
document.querySelectorAll(".rg button").forEach(b => b.addEventListener("click", () => {
  cur = b.dataset.r; try { localStorage.setItem("evo-range", cur); } catch(e) {} draw();
}));
draw();
})();
</script>
"""
