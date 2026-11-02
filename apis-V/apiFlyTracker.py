#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import requests
from branca.colormap import LinearColormap

# ==========================================
# CARREGAMENTO ROBUSTO DO .ENV
# ==========================================
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    print("AVISO: A biblioteca 'python-dotenv' nao esta instalada. Rode: pip install python-dotenv\n")

# ==========================================
# CONFIGURAÇÕES
# ==========================================
def limpar_chave(valor):
    if not valor: return None
    return valor.strip().strip("'\"")

CARTO_API_KEY = limpar_chave(os.getenv("CARTO_API_KEY"))

API = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
BBOX_BR = {"lamin": -34.0, "lamax": 5.5, "lomin": -74.0, "lomax": -34.0}
SAIDA = Path("saida_voos")
HISTORICO = SAIDA / "historico.csv"

CALLSIGN_COMERCIAL = re.compile(r"^[A-Z]{3}\d{1,4}[A-Z]{0,2}$")

GRUPOS = {
    "helicopteros": ("Helicopteros", "#d62728"),
    "comerciais": ("Comerciais", "#1f77b4"),
    "geral": ("Aviação geral / outras", "#2ca02c"),
    "leves": ("Planadores, ultraleves e drones", "#ff7f0e"),
    "sem_info": ("Sem categoria", "#7f7f7f"),
}

# ==========================================
# CLIENTE OPENSKY
# ==========================================
class OpenSkyAPI:
    def __init__(self):
        self.cid, self.secret = self._credenciais()
        self.token, self.exp = None, 0.0
        self.sess = requests.Session()

    @staticmethod
    def _credenciais():
        cid = limpar_chave(os.getenv("OPENSKY_CLIENT_ID"))
        sec = limpar_chave(os.getenv("OPENSKY_CLIENT_SECRET"))
        
        arq = Path(__file__).parent / "credentials.json"
        if not (cid and sec) and arq.exists():
            try:
                d = json.loads(arq.read_text(encoding="utf-8"))
                cid = d.get("clientId") or d.get("client_id")
                sec = d.get("clientSecret") or d.get("client_secret")
            except Exception:
                pass
        return cid, sec

    @property
    def autenticado(self):
        return bool(self.cid and self.secret)

    def _headers(self):
        if not self.autenticado: return {}
        if time.time() > self.exp - 60:
            r = requests.post(TOKEN_URL, data={
                "grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret})
            if r.status_code == 200:
                j = r.json()
                self.token = j["access_token"]
                self.exp = time.time() + j.get("expires_in", 1800)
            else:
                print("Aviso: Falha ao autenticar no OpenSky. Rodando como anonimo.")
                self.cid, self.secret = None, None
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path, params=None, exige_auth=False):
        if exige_auth and not self.autenticado:
            print("\n[ERRO] Este modo exige conta OpenSky.")
            return None
        
        r = self.sess.get(API + path, params=params, headers=self._headers(), timeout=60)
        
        restante = r.headers.get("X-Rate-Limit-Remaining")
        if restante: print(f"   [Creditos restantes hoje: {restante}]")
        
        if r.status_code == 429:
            print("\n[ERRO] Limite diario de creditos atingido.")
            return None
        if r.status_code == 404: return None
        if r.status_code in (401, 403):
            print("\n[ERRO] Acesso negado. Verifique suas credenciais OAuth2.")
            return None
        
        r.raise_for_status()
        return r.json()

# ==========================================
# AUXILIARES DO MAPA
# ==========================================
def criar_mapa(location=[-14.2, -51.9], zoom_start=4):
    m = folium.Map(location=location, zoom_start=zoom_start, control_scale=True)

    # Camada 1: CartoDB (Tenta usar a chave se ela existir)
    if CARTO_API_KEY:
        # Removido o {r} da URL para evitar conflito com a API Key
        carto_url = f"https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}.png?api_key={CARTO_API_KEY}"
        folium.TileLayer(
            tiles=carto_url,
            attr='© OpenStreetMap © CARTO', 
            name='CartoDB Positron (API Key)', 
            control=True
        ).add_to(m)
    
    # Camada 2: Esri Light Gray (Plano B infalível e gratuito)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri", 
        name="Esri Light Gray (Gratuito)", 
        control=True
    ).add_to(m)
    
    return m

def icone_aviao(rumo, cor):
    r = 0 if pd.isna(rumo) else float(rumo)
    svg = (f'<svg width="22" height="22" viewBox="0 0 20 20" style="transform:rotate({r:.0f}deg)">'
           f'<path d="M10 1 L16 18 L10 14 L4 18 Z" fill="{cor}" stroke="#222" stroke-width="1"/></svg>')
    return folium.DivIcon(html=svg, icon_size=(22, 22), icon_anchor=(11, 11))

def classificar(categoria, callsign):
    cat = int(categoria) if categoria and pd.notna(categoria) else 0
    cs = (callsign or "").strip().upper()
    if cat == 8: return "helicopteros"
    if cat in (9, 10, 11, 12, 14): return "leves"
    if CALLSIGN_COMERCIAL.match(cs) and cat in (0, 1, 3, 4, 5, 6, 7): return "comerciais"
    if cat >= 2: return "geral"
    return "sem_info"

# ==========================================
# MÓDULOS
# ==========================================
def modo_ao_vivo(api, args):
    SAIDA.mkdir(exist_ok=True)
    destino = SAIDA / "mapa_ao_vivo.html"
    intervalo = max(args.loop, 60) if args.loop else None

    while True:
        print("Consultando posições atuais...")
        j = api.get("/states/all", {**BBOX_BR, "extended": 1})
        if not j: break
            
        t = j.get("time", int(time.time()))
        estados = j.get("states") or []
        
        if not estados:
            print("Nenhuma aeronave encontrada.")
            df = pd.DataFrame()
        else:
            cols = ["icao24", "callsign", "pais", "t_pos", "t_contato", "lon", "lat", "alt_baro", 
                    "no_solo", "vel_ms", "rumo", "vrate", "sensores", "alt_geo", "squawk", "spi", "fonte", "categoria"]
            df = pd.DataFrame(estados, columns=cols)
            df = df.dropna(subset=["lat", "lon"])
            df["callsign"] = df["callsign"].fillna("").str.strip()
            
            if not args.incluir_solo: 
                df = df[df["no_solo"] != True]
            
            df["grupo"] = [classificar(c, cs) for c, cs in zip(df["categoria"], df["callsign"])]
            
            if args.gravar:
                novo = not HISTORICO.exists()
                with open(HISTORICO, "a", newline="", encoding="utf-8") as f:
                    df[["icao24", "callsign", "lat", "lon", "alt_baro", "rumo", "t_pos"]].to_csv(f, header=novo, index=False)

        m = criar_mapa()
        
        # Adiciona os grupos de aeronaves
        for chave, (nome, cor) in GRUPOS.items():
            sub = df[df["grupo"] == chave] if not df.empty else pd.DataFrame()
            if sub.empty: continue
            
            camada = folium.FeatureGroup(name=f"{nome} ({len(sub)})", show=(args.apenas == chave if args.apenas else True))
            for r in sub.itertuples():
                alt = f"{r.alt_baro:,.0f} m" if pd.notna(r.alt_baro) else "—"
                vel = f"{r.vel_ms*3.6:,.0f} km/h" if pd.notna(r.vel_ms) else "—"
                popup = f"<b>{r.callsign or 'Sem Callsign'}</b><br>ICAO: {r.icao24}<br>Alt: {alt}<br>Vel: {vel}<br>País: {r.pais}"
                folium.Marker([r.lat, r.lon], icon=icone_aviao(r.rumo, cor), tooltip=r.callsign or r.icao24,
                              popup=folium.Popup(popup, max_width=250)).add_to(camada)
            camada.add_to(m)

        # Controle de Camadas (Permite alternar entre Carto e Esri)
        folium.LayerControl(collapsed=False).add_to(m)
        
        m.save(destino)
        print(f"Mapa salvo: {destino} ({len(df)} aeronaves)")
        
        if intervalo is None:
            webbrowser.open(destino.resolve().as_uri())
            break
            
        print(f"Aguardando {intervalo}s...")
        time.sleep(intervalo)

def modo_trajetoria(api, args):
    icao24 = args.icao24.lower().strip()
    pts, fonte = [], ""
    print(f"Buscando trajetória para {icao24}...")
    
    try:
        j = api.get("/tracks", {"icao24": icao24, "time": 0})
        if j and j.get("path"):
            pts = [{"t": p[0], "lat": p[1], "lon": p[2], "alt": p[3]} for p in j["path"] if p[1] and p[2]]
            fonte = "OpenSky /tracks"
    except Exception as e:
        print(f"Aviso: /tracks indisponível: {e}")

    if not pts and HISTORICO.exists():
        print("Tentando plano B: histórico local...")
        df = pd.read_csv(HISTORICO)
        df = df[df["icao24"] == icao24]
        if not df.empty:
            pts = df[["t_pos", "lat", "lon", "alt_baro"]].rename(columns={"t_pos": "t", "alt_baro": "alt"}).to_dict("records")
            fonte = "Histórico Local"

    if len(pts) < 2:
        print(f"Sem dados suficientes para {icao24}.")
        return

    alts = [p["alt"] if pd.notna(p["alt"]) else 0 for p in pts]
    cmap = LinearColormap(["#2c7bb6", "#ffffbf", "#d7191c"], vmin=0, vmax=max(max(alts), 1000), caption="Altitude (m)")
    
    m = criar_mapa(location=[pts[0]["lat"], pts[0]["lon"]], zoom_start=6)
    for i in range(len(pts) - 1):
        folium.PolyLine([[pts[i]["lat"], pts[i]["lon"]], [pts[i+1]["lat"], pts[i+1]["lon"]]],
                        color=cmap((alts[i] + alts[i+1]) / 2), weight=4).add_to(m)
                        
    folium.Marker([pts[0]["lat"], pts[0]["lon"]], tooltip="Início", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker([pts[-1]["lat"], pts[-1]["lon"]], tooltip="Fim", icon=folium.Icon(color="red", icon="stop")).add_to(m)
    cmap.add_to(m)
    m.fit_bounds(m.get_bounds())

    folium.LayerControl(collapsed=False).add_to(m)

    destino = SAIDA / f"trajetoria_{icao24}.html"
    m.save(destino)
    print(f"Trajetória salva ({fonte}): {destino}")
    webbrowser.open(destino.resolve().as_uri())

def modo_aeroporto(api, args):
    icao = args.icao.upper().strip()
    dia = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=args.dias_atras)
    inicio, fim = int(dia.timestamp()), int((dia + timedelta(days=1)).timestamp())
    
    print(f"Buscando voos de {icao} em {dia:%d/%m/%Y}...")
    
    chegadas = api.get("/flights/arrival", {"airport": icao, "begin": inicio, "end": fim}, exige_auth=True)
    partidas = api.get("/flights/departure", {"airport": icao, "begin": inicio, "end": fim}, exige_auth=True)
    
    if chegadas is None or partidas is None: return
        
    chegadas = chegadas or []
    partidas = partidas or []
    
    if not chegadas and not partidas:
        print("Nenhum voo retornado. O dia atual costuma vir vazio. Tente 2 dias atrás.")
        return
        
    def processar(lista, tipo):
        if not lista: return pd.DataFrame()
        df = pd.DataFrame(lista)
        df["tipo"] = tipo
        df["hora"] = pd.to_datetime(df["lastSeen"], unit="s").dt.hour
        return df

    df_c = processar(chegadas, "Chegadas")
    df_p = processar(partidas, "Partidas")
    todos = pd.concat([df_c, df_p])

    SAIDA.mkdir(exist_ok=True)
    csv_path = SAIDA / f"voos_{icao}_{dia:%Y%m%d}.csv"
    todos.to_csv(csv_path, index=False, encoding="utf-8-sig")

    fig = px.bar(todos.groupby(["hora", "tipo"]).size().reset_index(name="qtd"), 
                 x="hora", y="qtd", color="tipo", barmode="group",
                 title=f"{icao} - Voos por Hora ({dia:%d/%m/%Y})")
    html = SAIDA / f"aeroporto_{icao}.html"
    fig.write_html(html)

    print(f"Dados salvos: {csv_path}")
    print(f"Grafico salvo: {html}")
    print(f"Chegadas: {len(df_c)} | Partidas: {len(df_p)}")
    webbrowser.open(html.resolve().as_uri())

# ==========================================
# MENU INTERATIVO
# ==========================================
def menu_interativo(api):
    print("\n" + "="*40)
    print("RASTREADOR DE VOOS OPENSKY BRASIL")
    print("="*40)
    print("1. Mapa ao vivo (Aeronaves no Brasil)")
    print("2. Trajetória de uma aeronave (ICAO24)")
    print("3. Chegadas/Partidas de um aeroporto")
    print("4. Sair")
    
    opcao = input("\nEscolha uma opção (1-4): ").strip()

    class Args: pass
    args = Args()

    if opcao == "1":
        print("\n--- CONFIGURAÇÃO DO MAPA AO VIVO ---")
        filtro = input("Filtrar por categoria? (0=Todos, 1=Helicopteros, 2=Comerciais, 3=Aviação Geral): ").strip()
        args.apenas = {"1": "helicopteros", "2": "comerciais", "3": "geral"}.get(filtro, None)
        
        solo = input("Incluir aeronaves no solo? (s/N): ").strip().lower()
        args.incluir_solo = (solo == 's')
        
        loop = input("Atualizar automaticamente a cada N segundos? (Deixe vazio para apenas 1 vez): ").strip()
        args.loop = int(loop) if loop.isdigit() else None
        
        gravar = input("Gravar histórico em CSV para plano B? (s/N): ").strip().lower()
        args.gravar = (gravar == 's')
        
        modo_ao_vivo(api, args)
        
    elif opcao == "2":
        print("\n--- CONFIGURAÇÃO DE TRAJETÓRIA ---")
        args.icao24 = input("Digite o código ICAO24 (ex: e48a2b): ").strip()
        if args.icao24: modo_trajetoria(api, args)
            
    elif opcao == "3":
        print("\n--- CONFIGURAÇÃO DE AEROPORTO ---")
        args.icao = input("Digite o código ICAO do aeroporto (ex: SBGR): ").strip()
        dias = input("Quantos dias atrás? (Padrão 1 = ontem): ").strip()
        args.dias_atras = int(dias) if dias.isdigit() else 1
        if args.icao: modo_aeroporto(api, args)
            
    elif opcao == "4":
        print("Saindo...")
        sys.exit(0)

# ==========================================
# MAIN
# ==========================================
def main():
    if len(sys.argv) == 1:
        api = OpenSkyAPI()
        
        print("\n--- DIAGNÓSTICO DE CREDENCIAIS ---")
        if api.autenticado: print(f"OpenSky: OK (ID: {api.cid[:5]}...)")
        else: print("OpenSky: FALTANDO (Modos 2 e 3 vao falhar)")
            
        if CARTO_API_KEY:
            mascarada = f"{CARTO_API_KEY[:5]}...{CARTO_API_KEY[-5:]}" if len(CARTO_API_KEY) > 10 else "Curta demais"
            print(f"Carto:   OK (Chave lida: {mascarada})")
        else:
            print("Carto:   FALTANDO (Usando Esri)")
        print("----------------------------------\n")
        
        while True:
            try:
                menu_interativo(api)
                input("\nPressione Enter para voltar ao menu...")
            except KeyboardInterrupt:
                print("\nSaindo...")
                break
        return

    ap = argparse.ArgumentParser(description="Rastreador OpenSky Brasil")
    sub = ap.add_subparsers(dest="modo", required=True)

    v = sub.add_parser("ao-vivo")
    v.add_argument("--apenas", choices=list(GRUPOS), help="Filtrar por categoria")
    v.add_argument("--incluir-solo", action="store_true")
    v.add_argument("--loop", type=int)
    v.add_argument("--gravar", action="store_true")

    t = sub.add_parser("trajetoria")
    t.add_argument("icao24")

    p = sub.add_parser("aeroporto")
    p.add_argument("icao")
    p.add_argument("--dias-atras", type=int, default=1)

    args = ap.parse_args()

    api = OpenSkyAPI()
    try:
        if args.modo == "ao-vivo": modo_ao_vivo(api, args)
        elif args.modo == "trajetoria": modo_trajetoria(api, args)
        elif args.modo == "aeroporto": modo_aeroporto(api, args)
    except KeyboardInterrupt:
        print("\nEncerrado.")

if __name__ == "__main__":
    main()