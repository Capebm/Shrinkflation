"""Write data/eventos.json and a self-contained HTML page with the radar feed."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from .detect import KIND_LABELS, Event

PAGE = """<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,500..800&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
/* Layout: summary strip, filter chips, then one row per event with the size change drawn as two bars. */
:root{--bg:#F3F6F7;--surface:#FFFFFF;--fg:#15202B;--muted:#56656F;--rule:#D3DCE1;--accent:#0E5A6E;--hot:#B3261E;--hot-soft:#F7E3E1;--mid:#9A6200;--mid-soft:#F6EBD6;--accent-soft:#DDECF0;
--display:"Archivo","Arial Narrow",system-ui,sans-serif;--body:"Source Serif 4",Georgia,serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0E151A;--surface:#151F26;--fg:#E3EAEE;--muted:#97A7B2;--rule:#27343D;--accent:#62B6CC;--hot:#F07A70;--hot-soft:#3A1E1C;--mid:#E2AB4B;--mid-soft:#352A14;--accent-soft:#16323B;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0E151A;--surface:#151F26;--fg:#E3EAEE;--muted:#97A7B2;--rule:#27343D;--accent:#62B6CC;--hot:#F07A70;--hot-soft:#3A1E1C;--mid:#E2AB4B;--mid-soft:#352A14;--accent-soft:#16323B;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--body);line-height:1.55}
.wrap{max-width:62rem;margin:0 auto;padding-inline:clamp(16px,4vw,40px);padding-block:2rem 3rem}
h1{font-family:var(--display);font-weight:800;font-stretch:72%;font-size:clamp(2rem,6vw,3.4rem);line-height:1.05;margin:.3rem 0 .6rem;text-wrap:balance}
.eyebrow{font-family:var(--mono);font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.banner{background:var(--mid-soft);border-left:3px solid var(--mid);padding:.7rem 1rem;margin:1rem 0}
.stats{display:flex;flex-wrap:wrap;gap:2rem;border-top:2px solid var(--fg);border-bottom:1px solid var(--rule);padding:.9rem 0;margin:1.2rem 0}
.stat b{display:block;font-family:var(--mono);font-size:1.6rem;font-weight:500}
.stat span{font-family:var(--mono);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}
.filters button{font-family:var(--mono);font-size:.78rem;padding:.35rem .7rem;border:1px solid var(--rule);background:var(--surface);color:var(--fg);border-radius:3px;cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ev{display:grid;grid-template-columns:6.5rem minmax(0,1fr) 9rem;gap:1rem;padding:1rem 0;border-bottom:1px solid var(--rule);align-items:start}
.pct{font-family:var(--mono);font-size:1.5rem;font-weight:500;color:var(--hot)}
.pct small{display:block;font-size:.68rem;color:var(--muted);font-weight:400;line-height:1.3}
.kind{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:var(--accent)}
.name{font-family:var(--display);font-stretch:88%;font-weight:700;font-size:1.1rem;margin:.15rem 0}
.sum{font-size:.95rem}
.meta{font-family:var(--mono);font-size:.75rem;color:var(--muted);margin-top:.3rem;word-break:break-all}
.meta a{color:var(--accent)}
.bars{display:grid;gap:.3rem;font-family:var(--mono);font-size:.7rem;color:var(--muted)}
.bar{height:.6rem;background:var(--accent)}
.bar.after{background:var(--hot)}
.empty{padding:2rem 0;color:var(--muted)}
@media (max-width:620px){.ev{grid-template-columns:5rem minmax(0,1fr)}.bars{grid-column:1/-1}}
</style>
</head>
<body>
<main class="wrap">
<div class="eyebrow">Radar de shrinkflation · Portugal</div>
<h1>__TITLE__</h1>
__BANNER__
<p>Produtos cuja embalagem encolheu ou cuja receita piorou, detetados automaticamente a partir de observações semanais. A percentagem é a subida efetiva do preço por unidade: medida quando a fonte tem preço, ou implícita (preço igual) quando não tem.</p>
<div class="stats" id="stats"></div>
<div class="filters" id="filters" role="group" aria-label="Filtrar por tipo"></div>
<div id="list"></div>
<p class="meta">Gerado em __DATE__ · <a href="index.html">Avaliação da «inflação real»</a> · Os casos automáticos não estão confirmados por uma pessoa; confirme no rótulo antes de citar.</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
  var events=JSON.parse(document.getElementById('data').textContent);
  var labels=__LABELS__;
  var fmt=function(x){return x.toFixed(1).replace('.',',')};
  var active='todos';
  function stats(){
    var s=document.getElementById('stats'),shr=events.filter(function(e){return e.change_pct!=null});
    var avg=shr.length?shr.reduce(function(a,e){return a+e.change_pct},0)/shr.length:0;
    var brands={};events.forEach(function(e){brands[e.brand]=1});
    s.innerHTML='<div class="stat"><b>'+events.length+'</b><span>casos</span></div>'+
      '<div class="stat"><b>'+Object.keys(brands).length+'</b><span>marcas</span></div>'+
      '<div class="stat"><b>'+(shr.length?'+'+fmt(avg)+'%':'–')+'</b><span>subida média por unidade</span></div>';
  }
  function filters(){
    var f=document.getElementById('filters'),kinds=['todos'].concat(Object.keys(labels));
    f.innerHTML='';
    kinds.forEach(function(k){
      var n=k==='todos'?events.length:events.filter(function(e){return e.kind===k}).length;
      if(k!=='todos'&&!n)return;
      var b=document.createElement('button');b.type='button';
      b.textContent=(k==='todos'?'Todos':labels[k])+' ('+n+')';
      b.setAttribute('aria-pressed',String(k===active));
      b.addEventListener('click',function(){active=k;filters();list()});f.appendChild(b);
    });
  }
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}
  function list(){
    var l=document.getElementById('list');l.innerHTML='';
    var rows=events.filter(function(e){return active==='todos'||e.kind===active});
    if(!rows.length){l.innerHTML='<p class="empty">Ainda não há casos. A primeira comparação aparece depois de duas recolhas semanais.</p>';return}
    rows.forEach(function(e){
      var d=document.createElement('div');d.className='ev';
      var pct=e.change_pct!=null?'+'+fmt(e.change_pct)+'%<small>'+(e.price_known?'preço por unidade':'implícito, preço igual')+'</small>':'<small>receita</small>';
      var bars='';
      if(e.details&&e.details.qty_before){var r=e.details.qty_after/e.details.qty_before;
        bars='<div class="bars"><span>antes '+e.details.qty_before+' '+e.details.unit+'</span><div class="bar" style="width:100%"></div>'+
             '<span>depois '+e.details.qty_after+' '+e.details.unit+'</span><div class="bar after" style="width:'+(r*100).toFixed(1)+'%"></div></div>';}
      var where=e.retailer?esc(e.retailer):(e.source==='off'?'Open Food Facts':esc(e.source));
      var codes=e.ean_before===e.ean_after?'EAN '+esc(e.ean_after):'EAN '+esc(e.ean_before)+' → '+esc(e.ean_after);
      var link=e.url&&/^https?:/.test(e.url)?' · <a href="'+esc(e.url)+'" target="_blank" rel="noopener">fonte</a>':'';
      d.innerHTML='<div class="pct">'+pct+'</div><div><div class="kind">'+esc(e.label)+'</div><div class="name">'+esc(e.brand)+' · '+esc(e.name)+'</div>'+
        '<div class="sum">'+esc(e.summary)+'</div><div class="meta">'+where+' · '+esc(e.date_before)+' → '+esc(e.date_after)+' · '+codes+link+'</div></div>'+bars;
      l.appendChild(d);
    });
  }
  stats();filters();list();
})();
</script>
</body>
</html>
"""

EXAMPLE_BANNER = ('<div class="banner"><strong>Dados fictícios.</strong> Esta página mostra o radar a funcionar '
                  'com produtos inventados («Marca Exemplo»). Não descreve nenhum produto real.</div>')


def write(events: list[Event], data_dir: Path, page_path: Path, *, example: bool = False) -> None:
    payload = [e.to_dict() for e in events]
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "eventos.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    title = "Radar de Exemplo" if example else "Radar da Reduflação"
    page = (PAGE.replace("__TITLE__", html.escape(title))
                .replace("__BANNER__", EXAMPLE_BANNER if example else "")
                .replace("__DATE__", date.today().isoformat())
                .replace("__LABELS__", json.dumps(KIND_LABELS, ensure_ascii=False))
                .replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")))
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page, encoding="utf-8")
