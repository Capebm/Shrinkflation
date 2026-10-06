# Termómetro Partido? · Radar da Reduflação

Dois trabalhos sobre preços em Portugal.

## 1. Avaliação da «inflação real»

`site/index.html` verifica, alegação a alegação, um episódio do podcast Bitcoin Talks que defende uma inflação «real» de 9–10%. As fontes são o INE, o Eurostat, o BCE e o Banco de Portugal. Abre diretamente num browser.

## 2. Radar de shrinkflation e skimpflation

Pacote Python `radar/`, sem dependências externas (Python 3.11 ou superior). Deteta:

| Tipo | Regra |
|---|---|
| `encolhimento` | A quantidade líquida desce e o preço por unidade sobe mais de 3% (ou, sem preço, a subida implícita a preço igual) |
| `troca_codigo` | Um código de barras desaparece e surge outro da mesma marca, com nome semelhante e quantidade menor |
| `receita_quid` | A % declarada do ingrediente principal (QUID, Reg. UE 1169/2011, art. 22) desce 2 p.p. ou mais |
| `receita_nutricao` | A proteína desce 10% ou mais (e pelo menos 0,5 g/100 g) |

Não são alertas: subir o preço sem mexer na embalagem, ou reduzir a embalagem com descida proporcional do preço.

### Fontes

- **Open Food Facts** (`recolher off`): produtos vendidos em Portugal, com quantidade, ingredientes e tabela nutricional (licença ODbL). Não tem preços.
- **Lojas online** (`recolher lojas`): páginas de produto listadas em `data/fontes/lojas.csv` (`retalhista,url`), lidas através do JSON-LD `Product` do schema.org. Respeita o robots.txt e faz uma pausa de 3 s entre pedidos. **Ainda não foi testado contra as lojas portuguesas**: páginas montadas só no browser ou protegidas contra robôs são ignoradas e aparecem no registo.
- **CSV** (`recolher csv FICHEIRO`): talões, fotos de prateleira, casos da DECO ou dados de parceiros. Colunas: `data,retalhista,ean,marca,nome,quantidade,preco,url,ingredientes,proteina`.

### Utilização

```bash
python -m radar exemplo                    # demonstração com dados fictícios -> site/radar-exemplo.html
python -m radar recolher off --paginas 10  # Open Food Facts
python -m radar recolher lojas
python -m radar recolher csv talões.csv
python -m radar detetar                    # data/eventos.json + site/radar.html
python -m unittest discover -s tests -t .
```

As opções globais vêm antes do comando: `python -m radar --data 2026-10-06 recolher off`.

### Dados

- `data/historico.jsonl`: uma observação por linha, gravada só quando algo mudou, para o histórico caber no git.
- `data/vistos.json`: primeira e última data em que cada produto foi visto, usada para detetar trocas de código.
- `data/eventos.json`: os casos detetados.

### Recolha automática

`.github/workflows/radar.yml` corre às segundas-feiras: testa, recolhe, deteta e faz commit dos resultados. O GitHub só corre ações agendadas no branch por omissão, por isso o agendamento começa depois do merge. Antes disso pode correr-se à mão em *Actions → Radar semanal → Run workflow*.

### Cuidados

Os casos automáticos não estão confirmados por uma pessoa. Antes de publicar, confirme no rótulo, guarde a prova e dê às marcas direito de resposta.
