"""Linha de comandos do radar.

  python -m radar recolher off [--categorias en:chocolates ...] [--paginas 10]
  python -m radar recolher lojas [--lista data/fontes/lojas.csv]
  python -m radar recolher csv FICHEIRO.csv
  python -m radar recolher precos [--dias 400]   # Open Prices, para os produtos já no histórico
  python -m radar detetar          # escreve data/eventos.json e site/radar.html
  python -m radar exemplo          # corre tudo sobre dados fictícios -> site/radar-exemplo.html
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from . import report
from .detect import detect
from .sources import csvfile, lojas, off, openprices
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar", description="Radar de shrinkflation e skimpflation")
    ap.add_argument("--dados", type=Path, default=ROOT / "data", help="pasta do histórico")
    ap.add_argument("--data", default=date.today().isoformat(), help="data da observação (AAAA-MM-DD)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("recolher", help="recolher observações de uma fonte")
    rsub = rec.add_subparsers(dest="fonte", required=True)
    r_off = rsub.add_parser("off", help="Open Food Facts, produtos vendidos em Portugal")
    r_off.add_argument("--categorias", nargs="*", default=off.DEFAULT_CATEGORIES)
    r_off.add_argument("--paginas", type=int, default=10)
    r_lojas = rsub.add_parser("lojas", help="páginas de produto de lojas online (JSON-LD)")
    r_lojas.add_argument("--lista", type=Path, default=ROOT / "data/fontes/lojas.csv")
    r_csv = rsub.add_parser("csv", help="observações num CSV (manuais ou de parceiros)")
    r_csv.add_argument("ficheiro", type=Path)
    r_precos = rsub.add_parser("precos", help="preços colaborativos do Open Prices (lojas em Portugal)")
    r_precos.add_argument("--dias", type=int, default=400, help="recolher preços dos últimos N dias")

    det = sub.add_parser("detetar", help="detetar casos e gerar a página")
    det.add_argument("--pagina", type=Path, default=ROOT / "site/radar.html")

    sub.add_parser("exemplo", help="demonstração com dados fictícios")
    args = ap.parse_args(argv)

    if args.cmd == "exemplo":
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add(csvfile.read(ROOT / "data/exemplo/observacoes.csv"))
            events = detect(store.history(), store.seen())
            report.write(events, Path(tmp), ROOT / "site/radar-exemplo.html", example=True)
        _print(events)
        return 0

    store = Store(args.dados)
    price_store = openprices.PriceStore(args.dados)
    if args.cmd == "recolher":
        if args.fonte == "precos":
            since = (date.fromisoformat(args.data) - timedelta(days=args.dias)).isoformat()
            points = openprices.fetch({o.ean for o in store.history()}, since)
            print(f"{len(points)} preços em lojas portuguesas, {price_store.add(points)} novos gravados")
            return 0
        if args.fonte == "off":
            obs, failed = off.collect(args.categorias, args.data, max_pages=args.paginas)
            if failed and len(failed) == len(args.categorias):
                print("Open Food Facts indisponível para todas as categorias", file=sys.stderr)
                return 1
        elif args.fonte == "lojas":
            obs, skipped = lojas.collect(args.lista, args.data)
            for line in skipped:
                print("ignorado:", line, file=sys.stderr)
        else:
            obs = csvfile.read(args.ficheiro)
        print(f"{len(obs)} observações, {store.add(obs)} com alterações gravadas")
        return 0

    events = detect(store.history(), store.seen(), price_store.load())
    report.write(events, args.dados, args.pagina)
    _print(events)
    return 0


def _print(events) -> None:
    print(f"{len(events)} casos")
    for e in events:
        pct = f"+{e.change_pct:.1f}%" if e.change_pct is not None else "receita"
        print(f"  {pct:>9}  {e.kind:<17} {e.brand} · {e.name}: {e.summary}")


if __name__ == "__main__":
    raise SystemExit(main())
