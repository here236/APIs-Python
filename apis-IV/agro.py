#!/usr/bin/env python3
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
SIGLA_UF = {k: v[0] for k, v in UFS.items()}


# ----- utilidades
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


# ------ IBGE
def resolver_cultura(nome: str) -> list[tuple[str, str, str]]:
    """Lista de candidatas (id da classificação, id da categoria, nome), da melhor p/ pior.

    O id da classificação NÃO é fixo: é localizado pelo nome ("Produto das lavouras...").
    O ranking prefere o produto "principal" (ex.: "Milho (em grão)") e deixa por último
    variantes como "Milho verde", "1ª safra", "para forragem".
    """
    meta = get_json(f"{IBGE}/agregados/{TABELA_PAM}/metadados")
    classifs = meta.get("classificacoes", [])
    if not classifs:
        sys.exit(f"A tabela {TABELA_PAM} não retornou classificações. Resposta: {list(meta)}")
    classif = next((c for c in classifs if "produto" in norm(c["nome"])), None)
    if classif is None:  # fallback: a classificação com mais categorias
        classif = max(classifs, key=lambda c: len(c.get("categorias", [])))
    alvo = norm(nome)
    cands = [c for c in classif["categorias"] if alvo in norm(c["nome"])]
    if not cands:
        sys.exit(f"Cultura '{nome}' não encontrada na classificação '{classif['nome']}'.")

    def rank(c):
        n = norm(c["nome"])
        return (not n.startswith(alvo),
                any(t in n for t in ("safra", "verde", "forrag", "semente", "muda")),
                not any(t in n for t in ("em grao", "em casca", "em caroco", "herbaceo")),
                len(n))

    cands.sort(key=rank)
    return [(str(classif["id"]), str(c["id"]), c["nome"]) for c in cands]


def buscar_cultura(cultura: str, n_anos: int, cod: int | None = None):
    """Tenta as candidatas em ordem até achar uma com dados (para a UF, se informada)."""
    cands = resolver_cultura(cultura)
    print("→ Candidatas:", " | ".join(n for _, _, n in cands[:6]))
    for classif_id, cat_id, nome in cands[:6]:
        pam = buscar_pam(classif_id, cat_id, n_anos)
        sub = pam if cod is None else pam[pam["cod"] == cod]
        if not sub[["producao_t", "rendimento_kg_ha"]].dropna(how="all").empty:
            print(f"→ Usando: {nome} (id {cat_id})")
            return nome, sub
        print(f"  (sem dados para '{nome}', tentando a próxima)")
    alvo = f" em {SIGLA_UF.get(cod, cod)}" if cod else ""
    sys.exit(f"Nenhuma variante de '{cultura}' tem dados{alvo} no período.")


def buscar_pam(classif_id: str, cat_id: str, n_anos: int) -> pd.DataFrame:
    """Produção, área colhida e rendimento por UF nos últimos n anos."""
    vars_ = "|".join(VARIAVEIS)
    url = (f"{IBGE}/agregados/{TABELA_PAM}/periodos/-{n_anos}/variaveis/{vars_}"
           f"?localidades=N3[all]&classificacao={classif_id}[{cat_id}]")
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
    pam = (df.pivot_table(index=["cod", "ano"], columns="var", values="valor")
             .rename(columns=VARIAVEIS).reset_index())
    for col in VARIAVEIS.values():
        if col not in pam:
            pam[col] = float("nan")
    return pam


def buscar_malha_ufs() -> dict:
    return get_json(f"{IBGE}/malhas/paises/BR",
                    {"formato": "application/vnd.geo+json",
                     "qualidade": "minima", "intrarregiao": "UF"})


# ----clima
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


# ---Desafio 1
def grafico_comparativo(uf: str, cultura: str, n_anos: int, meses, saida: Path):
    cod = SIGLA_PARA_COD[uf]
    nome_cultura, pam = buscar_cultura(cultura, n_anos, cod)
    clima = clima_anual(cod, int(pam["ano"].min()), int(pam["ano"].max()), meses)
    df = pam.merge(clima, on="ano").sort_values("ano")

    r_prod = df["precip_mm"].corr(df["producao_t"])
    r_rend = df["precip_mm"].corr(df["rendimento_kg_ha"])
    janela = f"meses {meses}" if meses else "ano todo"
    titulo = (f"{nome_cultura} em {uf} — precipitação acumulada ({janela}) × produção<br>"
              f"<sup>Pearson: chuva×produção = {r_prod:.2f} | chuva×rendimento = {r_rend:.2f}</sup>")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=df["ano"], y=df["precip_mm"], name="Precipitação (mm)",
                marker_color="#6baed6", opacity=0.75)
    fig.add_scatter(x=df["ano"], y=df["producao_t"], name="Produção (t)",
                    mode="lines+markers", line=dict(color="#238b45", width=3),
                    secondary_y=True)
    fig.add_scatter(x=df["ano"], y=df["rendimento_kg_ha"], name="Rendimento (kg/ha)",
                    mode="lines+markers", line=dict(color="#e6550d", dash="dot"),
                    secondary_y=True, visible="legendonly")
    fig.update_layout(title=titulo, template="plotly_white", hovermode="x unified")
    fig.update_yaxes(title_text="mm", secondary_y=False)
    fig.update_yaxes(title_text="t  /  kg/ha", secondary_y=True)
    html = saida / f"comparativo_{uf}_{norm(cultura)}.html"
    fig.write_html(html)

    # versão estática: dispersão chuva × rendimento
    d = df.dropna(subset=["precip_mm", "rendimento_kg_ha"])
    fig2, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(d["precip_mm"], d["rendimento_kg_ha"], c=d["ano"], cmap="viridis", s=70)
    for _, l in d.iterrows():
        ax.annotate(int(l["ano"]), (l["precip_mm"], l["rendimento_kg_ha"]),
                    fontsize=7, xytext=(3, 3), textcoords="offset points")
    if len(d) > 2:
        a, b = pd.Series(d["precip_mm"]).pipe(lambda x: (
            (d["rendimento_kg_ha"].cov(x) / x.var()),
            d["rendimento_kg_ha"].mean() - d["rendimento_kg_ha"].cov(x) / x.var() * x.mean()))
        xs = [d["precip_mm"].min(), d["precip_mm"].max()]
        ax.plot(xs, [a * x + b for x in xs], "r--", lw=1)
    ax.set(xlabel="Precipitação acumulada (mm)", ylabel="Rendimento médio (kg/ha)",
           title=f"{nome_cultura} — {uf}  (r = {r_rend:.2f})")
    png = saida / f"dispersao_{uf}_{norm(cultura)}.png"
    fig2.tight_layout()
    fig2.savefig(png, dpi=150)
    plt.close(fig2)
    print(f"✔ {html}\n✔ {png}")
    return df


# -----Desafio 2
def mapa_calor(cultura: str, n_anos: int, meses, saida: Path):
    nome_cultura, pam = buscar_cultura(cultura, n_anos)
    prod = (pam.groupby("cod")["rendimento_kg_ha"].mean().dropna()
               .rename("rendimento").reset_index())
    ano_ini, ano_fim = int(pam["ano"].min()), int(pam["ano"].max())

    linhas = []
    for cod in prod["cod"]:
        c = clima_anual(int(cod), ano_ini, ano_fim, meses)
        sigla, lat, lon = UFS[int(cod)]
        linhas.append({"cod": int(cod), "uf": sigla, "lat": lat, "lon": lon,
                       "precip_mm": c["precip_mm"].mean(), "temp_c": c["temp_c"].mean()})
    df = prod.merge(pd.DataFrame(linhas), on="cod")
    df["codarea"] = df["cod"].astype(str)

    geo = buscar_malha_ufs()
    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        geojson=geo, locations=df["codarea"], z=df["rendimento"],
        featureidkey="properties.codarea", colorscale="YlGn",
        colorbar=dict(title="Rendimento<br>(kg/ha)", x=1.0), marker_line_width=0.5,
        text=df["uf"],
        hovertemplate="<b>%{text}</b><br>Rendimento: %{z:.0f} kg/ha<extra></extra>"))
    fig.add_trace(go.Scattergeo(
        lon=df["lon"], lat=df["lat"], mode="markers+text", text=df["uf"],
        textposition="middle center", textfont=dict(size=9),
        marker=dict(size=df["precip_mm"] / df["precip_mm"].max() * 38 + 8,
                    color=df["precip_mm"], colorscale="Blues", opacity=0.55,
                    line=dict(width=1, color="#08306b"),
                    colorbar=dict(title="Precip.<br>média (mm)", x=1.12)),
        customdata=df[["precip_mm", "temp_c"]],
        hovertemplate=("<b>%{text}</b><br>Precip.: %{customdata[0]:.0f} mm"
                       "<br>Temp.: %{customdata[1]:.1f} °C<extra></extra>"),
        showlegend=False))
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        title=f"{nome_cultura}: rendimento médio ({ano_ini}–{ano_fim}) "
              f"e precipitação (círculos)", margin=dict(l=0, r=0, t=60, b=0))
    html = saida / f"mapa_{norm(cultura)}.html"
    fig.write_html(html)
    print(f"✔ {html}")
    return df


# --------CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", help="Sigla do estado (ex.: MT)")
    ap.add_argument("--cultura", help="Ex.: soja, milho, trigo, arroz, feijão")
    ap.add_argument("--anos", type=int, default=15, help="Últimos N anos (padrão 15)")
    ap.add_argument("--meses", type=int, nargs="*",
                    help="Meses do ano a considerar no acumulado (ex.: 1 2 3 4)")
    ap.add_argument("--modo", choices=["grafico", "mapa", "ambos"], default="ambos")
    ap.add_argument("--saida", default="saida")
    a = ap.parse_args()

    cultura = a.cultura or input("Cultura (ex.: soja, milho): ").strip()
    uf = (a.uf or (input("UF (ex.: MT): ").strip() if a.modo != "mapa" else "")).upper()
    if a.modo != "mapa" and uf not in SIGLA_PARA_COD:
        sys.exit(f"UF inválida: {uf}. Opções: {', '.join(sorted(SIGLA_PARA_COD))}")

    saida = Path(a.saida)
    saida.mkdir(exist_ok=True)
    if a.modo in ("grafico", "ambos"):
        grafico_comparativo(uf, cultura, a.anos, a.meses, saida)
    if a.modo in ("mapa", "ambos"):
        mapa_calor(cultura, a.anos, a.meses, saida)


if __name__ == "__main__":
    main()
