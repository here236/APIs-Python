import calendar
import time
from collections import Counter

import pandas as pd
import plotly.express as px
import requests

BASE = "https://dadosabertos.camara.leg.br/api/v2"
HEADERS = {"Accept": "application/json"}  # garante que a API devolve JSON

TEMA = "saúde"                 # tema do desafio 1 (ex: "educação")
ANO = 2025                     # uso 2025 porque 2026 ainda não acabou
TIPOS = ["PL", "PLP", "PEC"]   # só esses tipos, senão vem requerimento demais
MAX_PROPOSICOES = 200          # limite pra não demorar (None = pega tudo)
TOP_N = 15                     # quantos deputados aparecem no ranking
VOTACOES_POR_MES = 10          # quantas votações do plenário olho por mês


def get_json(url, params=None):
    # tenta 3 vezes, porque a API às vezes falha do nada
    for tentativa in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  deu erro ({tentativa}/3): {e}")
            time.sleep(2)
    return {}  # se falhou 3 vezes, devolve vazio pra não quebrar o código


def get_todas_paginas(url, params, limite=None):
    # a API entrega no máximo 100 itens por página,
    # então vou pedindo pagina 1, 2, 3... até vir vazio
    resultado = []
    pagina = 1
    while True:
        p = dict(params, pagina=pagina, itens=100)
        print(f"    página {pagina}...")
        dados = get_json(url, p).get("dados", [])
        if not dados:
            break
        resultado += dados
        if limite and len(resultado) >= limite:
            return resultado[:limite]
        pagina += 1
    return resultado


def desafio1():
    print(f"\n[Desafio 1] Proposições sobre '{TEMA}' em {ANO}...")

    params = {
        "keywords": TEMA,
        "ano": ANO,
        "siglaTipo": TIPOS,
        "ordenarPor": "id",  # ordem fixa pra paginação não embaralhar
        "ordem": "ASC",
    }
    proposicoes = get_todas_paginas(f"{BASE}/proposicoes", params, MAX_PROPOSICOES)
    print(f"  achei {len(proposicoes)} proposições, buscando os autores...")

    # a lista de proposições não traz o autor,
    # então tenho que pedir os autores de cada uma separado
    contagem = Counter()
    for i, prop in enumerate(proposicoes, 1):
        autores = get_json(f"{BASE}/proposicoes/{prop['id']}/autores").get("dados", [])
        for a in autores:
            uri = a.get("uri") or ""
            # só conta se for deputado (tem autor que é comissão, senador etc)
            if "/deputados/" in uri:
                contagem[a.get("nome", "?")] += 1
        if i % 25 == 0:
            print(f"  {i}/{len(proposicoes)}")

    if not contagem:
        print("  não achei nenhum deputado :(")
        return

    # monta o DataFrame com o top N
    df = pd.DataFrame(contagem.most_common(TOP_N), columns=["deputado", "proposicoes"])
    print(df.to_string(index=False))

    # ordena crescente pro maior ficar no topo do gráfico horizontal
    df = df.sort_values("proposicoes")

    fig = px.bar(
        df,
        x="proposicoes",
        y="deputado",
        orientation="h",
        title=f"Deputados com mais proposições sobre '{TEMA}' em {ANO}",
        labels={"proposicoes": "Nº de proposições", "deputado": "Deputado"},
    )
    fig.write_html("desafio1_ranking.html")
    fig.show()


def desafio2():
    print(f"\n[Desafio 2] Participação em votações por partido em {ANO}...")

    nomes_meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                   "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    linhas = []
    votacoes_por_mes = {}  # guarda quantas votações analisei em cada mês

    for mes in range(1, 13):
        # descobre o último dia do mês (28, 30, 31...)
        ultimo_dia = calendar.monthrange(ANO, mes)[1]
        params = {
            "dataInicio": f"{ANO}-{mes:02d}-01",
            "dataFim": f"{ANO}-{mes:02d}-{ultimo_dia:02d}",
            "idOrgao": 180,  # 180 = Plenário, evita baixar votação de comissão
        }
        votacoes = get_todas_paginas(f"{BASE}/votacoes", params)

        # filtro só o plenário (PLEN), que é onde tem voto nominal
        plenario = [v for v in votacoes if v.get("siglaOrgao") == "PLEN"]
        plenario = plenario[:VOTACOES_POR_MES]

        contagem = Counter()
        com_votos = 0
        for v in plenario:
            votos = get_json(f"{BASE}/votacoes/{v['id']}/votos").get("dados", [])
            if not votos:
                continue  # votação simbólica não tem voto nominal, pula
            com_votos += 1
            for voto in votos:
                # JSON aninhado: os dados do deputado ficam dentro de "deputado_"
                partido = (voto.get("deputado_") or {}).get("siglaPartido")
                if partido:
                    contagem[partido] += 1

        votacoes_por_mes[mes] = com_votos
        print(f"  {nomes_meses[mes - 1]}: {com_votos} votações nominais")

        for partido, qtd in contagem.items():
            # média de deputados do partido votando por votação
            # (divido pelas votações pra meses diferentes ficarem comparáveis)
            linhas.append({"partido": partido, "mes": mes, "media": qtd / com_votos})

    if not linhas:
        print("  não achei nenhum voto nominal :(")
        return

    # transforma em tabela: linhas = partido, colunas = mês
    df = pd.DataFrame(linhas)
    tabela = df.pivot_table(index="partido", columns="mes", values="media", fill_value=0)
    tabela = tabela.reindex(columns=range(1, 13), fill_value=0)  # garante os 12 meses
    tabela.columns = nomes_meses
    # partidos mais ativos em cima
    tabela = tabela.loc[tabela.sum(axis=1).sort_values(ascending=False).index]

    # mês com mais e menos atividade
    mais = max(votacoes_por_mes, key=votacoes_por_mes.get)
    menos = min(votacoes_por_mes, key=votacoes_por_mes.get)
    print(f"  mês mais ativo: {nomes_meses[mais - 1]} ({votacoes_por_mes[mais]} votações)")
    print(f"  mês menos ativo: {nomes_meses[menos - 1]} ({votacoes_por_mes[menos]} votações)")

    fig = px.imshow(
        tabela,
        aspect="auto",
        color_continuous_scale="YlOrRd",
        labels={"x": "Mês", "y": "Partido", "color": "Deputados votando / votação"},
        title=f"Participação em votações nominais do Plenário por partido ({ANO})",
    )
    fig.write_html("desafio2_heatmap.html")
    fig.show()


if __name__ == "__main__":
    desafio1()
    desafio2()
    print("\nPronto! Gráficos salvos em desafio1_ranking.html e desafio2_heatmap.html")