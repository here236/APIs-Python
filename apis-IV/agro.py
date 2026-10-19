#!/usr/bin/env python3
"""
Monitor de Indicadores Agropecuários e Climáticos
=================================================
Cruza produção agrícola municipal/estadual (IBGE, PAM - tabela 5457 do SIDRA,
via API de Agregados) com séries climáticas mensais (precipitação e temperatura).

Uso:
    python monitor_agro.py                       # modo interativo
    python monitor_agro.py --uf MT --cultura soja --anos 15
    python monitor_agro.py --uf PR --cultura milho --meses 1 2 3 4 --modo grafico
    python monitor_agro.py --cultura soja --modo mapa

Saídas (pasta ./saida): HTML interativos (Plotly) + PNG estático (matplotlib).
"""
import argparse
import calendar
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

IBGE = "https://servicodados.ibge.gov.br/api/v3"
NASA_POWER = "https://power.larc.nasa.gov/api/temporal/monthly/point"
TABELA_PAM = 5457          # PAM - Produção Agrícola Municipal (1974-...)
CLASSIF_PRODUTO = "782"    # classificação "Produto das lavouras"
VARIAVEIS = {"112": "rendimento_kg_ha", "214": "producao_t", "216": "area_colhida_ha"}

CACHE_DIR = Path(".cache_agro")
CACHE_DIR.mkdir(exist_ok=True)

# código IBGE: (sigla, lat, lon) — centroide aproximado de cada UF
UFS = {
    11: ("RO", -10.83, -63.34), 12: ("AC", -9.02, -70.81), 13: ("AM", -3.47, -65.10),
    14: ("RR", 2.05, -61.40), 15: ("PA", -3.79, -52.48), 16: ("AP", 1.41, -51.77),
    17: ("TO", -10.18, -48.33), 21: ("MA", -5.42, -45.44), 22: ("PI", -7.72, -42.73),
    23: ("CE", -5.20, -39.53), 24: ("RN", -5.81, -36.59), 25: ("PB", -7.12, -36.72),
    26: ("PE", -8.38, -37.86), 27: ("AL", -9.62, -36.82), 28: ("SE", -10.57, -37.45),
    29: ("BA", -12.96, -41.70), 31: ("MG", -18.46, -44.20), 32: ("ES", -19.57, -40.67),
    33: ("RJ", -22.25, -42.66), 35: ("SP", -22.19, -48.79), 41: ("PR", -24.89, -51.55),
    42: ("SC", -27.45, -50.95), 43: ("RS", -29.75, -53.25), 50: ("MS", -20.51, -54.54),
    51: ("MT", -12.64, -55.42), 52: ("GO", -15.98, -49.86), 53: ("DF", -15.83, -47.86),
}
SIGLA_PARA_COD = {v[0]: k for k, v in UFS.items()}


# ----------------------------------------------------------------- utilidades
def norm(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt.lower())
                   if unicodedata.category(c) != "Mn")


def get_json(url: str, params: dict | None = None):
    """GET com cache em disco (evita bater nas APIs a cada execução)."""
    chave = hashlib.md5((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    arq = CACHE_DIR / f"{chave}.json"
    if arq.exists():
        return json.loads(arq.read_text())
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    dados = r.json()
    arq.write_text(json.dumps(dados))
    return dados


# ----------------------------------------------------------------------- IBGE
def resolver_cultura(nome: str) -> tuple[str, str]:
    """Descobre o id da categoria da cultura consultando os metadados da tabela."""
    meta = get_json(f"{IBGE}/agregados/{TABELA_PAM}/metadados")
    classif = next(c for c in meta["classificacoes"] if c["id"] == CLASSIF_PRODUTO)
    alvo = norm(nome)
    cands = [c for c in classif["categorias"] if alvo in norm(c["nome"])]
    if not cands:
        sys.exit(f"Cultura '{nome}' não encontrada na tabela {TABELA_PAM}.")
    cands.sort(key=lambda c: (not norm(c["nome"]).startswith(alvo), len(c["nome"])))
    return str(cands[0]["id"]), cands[0]["nome"]


def buscar_pam(cat_id: str, n_anos: int) -> pd.DataFrame:
    """Produção, área colhida e rendimento por UF nos últimos n anos."""
    vars_ = "|".join(VARIAVEIS)
    url = (f"{IBGE}/agregados/{TABELA_PAM}/periodos/-{n_anos}/variaveis/{vars_}"
           f"?localidades=N3[all]&classificacao={CLASSIF_PRODUTO}[{cat_id}]")
    dados = get_json(url)
    linhas = []
    for var in dados:
        for res in var["resultados"]:
            for s in res["series"]:
                for ano, val in s["serie"].items():
                    linhas.append({"var": var["id"], "cod": int(s["localidade"]["id"]),
                                   "ano": int(ano), "valor": val})
    df = pd.DataFrame(linhas)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")  # "-", "...", "X" -> NaN
    return (df.pivot_table(index=["cod", "ano"], columns="var", values="valor")
              .rename(columns=VARIAVEIS).reset_index())


def buscar_malha_ufs() -> dict:
    return get_json(f"{IBGE}/malhas/paises/BR",
                    {"formato": "application/vnd.geo+json",
                     "qualidade": "minima", "intrarregiao": "UF"})


# ---------------------------------------------------------------------- clima
def clima_anual(cod_uf: int, ano_ini: int, ano_fim: int,
                meses: list[int] | None = None) -> pd.DataFrame:
    """Precipitação acumulada (mm) e temperatura média (°C) por ano, via NASA POWER.

    Usa o centroide da UF como ponto de referência (aproximação).
    """
    _, lat, lon = UFS[cod_uf]
    j = get_json(NASA_POWER, {
        "parameters": "PRECTOTCORR,T2M", "community": "AG",
        "latitude": lat, "longitude": lon,
        "start": ano_ini, "end": ano_fim, "format": "JSON"})
    p = j["properties"]["parameter"]
    linhas = []
    for chave, chuva_dia in p["PRECTOTCORR"].items():
        ano, mes = int(chave[:4]), int(chave[4:])
        if mes == 13:                       # 13 = média anual, ignorar
            continue
        if meses and mes not in meses:
            continue
        temp = p["T2M"][chave]
        linhas.append({
            "ano": ano,
            # mm/dia -> mm/mês
            "precip_mm": chuva_dia * calendar.monthrange(ano, mes)[1] if chuva_dia > -990 else None,
            "temp_c": temp if temp > -990 else None})
    df = pd.DataFrame(linhas)
    return df.groupby("ano").agg(precip_mm=("precip_mm", "sum"),
                                 temp_c=("temp_c", "mean")).reset_index()


# ------------------------------------------------------------- Desafio 1
def grafico_comparativo(uf: str, cultura: str, n_anos: int, meses, saida: Path):
    cod = SIGLA_PARA_COD[uf]
    cat_id, nome_cultura = resolver_cultura(cultura)
    pam = buscar_pam(cat_id, n_anos)
    pam = pam[pam["cod"] == cod]
    if pam.empty:
        sys.exit(f"Sem dados de {nome_cultura} para {uf}.")
    clima = clima_anual(cod, int(pam["ano"].min()), int(pam["ano"].max()), meses)
    df = pam.merge(clima, on="ano").sort_values("ano")

    r_prod = df["precip_mm"].corr(df["producao_t"])
    r_rend = df["precip_mm"].corr(df["rendimento_kg_ha"])
    janela = f"meses {meses}" if meses else "ano todo"
    titulo = (f"{nome_cultura} em {uf} — precipitação acumulada ({janela}) × produção<br>"
              f"<sup>Pearson: chuva×produção = {r_prod:.2f} | chuva×rendimento = {r_rend:.2f}</sup>")
