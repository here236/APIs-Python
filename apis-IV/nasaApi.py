#para rodar use: python -m streamlit run nasaApi.py

import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from bs4 import BeautifulSoup
from datetime import date, timedelta

# chave da NASA (usada so nos asteroides)
chave_api = 'COLOQUE_SUA_CHAVE'

st.title('Dashboard de Exploracao Espacial')

aba1, aba2, aba3, aba4 = st.tabs(['Asteroides', 'APOD', 'Exoplanetas', 'Eventos naturais'])

# ABA 1: ASTEROIDES
with aba1:
    st.header('Asteroides proximos da Terra')
    st.write('Escolha um intervalo de no maximo 7 dias')

    hoje = date.today()
    intervalo = st.date_input('Intervalo de datas', value=(hoje - timedelta(days=6), hoje))

    # so continua quando o usuario escolher as duas datas
    if len(intervalo) == 2:
        data_inicio = intervalo[0]
        data_fim = intervalo[1]

        if (data_fim - data_inicio).days > 6:
            st.warning('O intervalo maximo e de 7 dias')
        else:
            url_neo = 'https://api.nasa.gov/neo/rest/v1/feed'
            parametros = {
                'start_date': str(data_inicio),
                'end_date': str(data_fim),
                'api_key': chave_api
            }
            resposta = requests.get(url_neo, params=parametros)

            if resposta.status_code == 200:
                dados = resposta.json()

                # lista vazia que vai receber os asteroides
                lista = []

                # o JSON vem agrupado por data, entao usamos dois for
                for dia in dados['near_earth_objects']:
                    for asteroide in dados['near_earth_objects'][dia]:
                        aproximacao = asteroide['close_approach_data'][0]

                        lista.append({
                            'nome': asteroide['name'],
                            'data': dia,
                            'diametro_km': asteroide['estimated_diameter']['kilometers']['estimated_diameter_max'],
                            'distancia_km': float(aproximacao['miss_distance']['kilometers']),
                            'velocidade_km_s': float(aproximacao['relative_velocity']['kilometers_per_second']),
                            'perigoso': asteroide['is_potentially_hazardous_asteroid']
                        })

                df_asteroides = pd.DataFrame(lista)

                # grafico de dispersao com escala logaritmica no eixo X
                grafico = px.scatter(
                    df_asteroides,
                    x='distancia_km',
                    y='velocidade_km_s',
                    size='diametro_km',
                    color='perigoso',
                    hover_name='nome',
                    log_x=True,
                    title='Distancia x Velocidade dos asteroides'
                )
                st.plotly_chart(grafico)
            else:
                st.error('Erro na requisicao: ' + str(resposta.status_code))

# ABA 2: APOD
with aba2:
    st.header('Imagem Astronomica do Dia')

    url_apod = 'https://science.nasa.gov/wp-json/wp/v2/apod-basic'
    parametros = {
        'per_page': 1,
        'page': 1
    }
    resposta = requests.get(url_apod, params=parametros)

    if resposta.status_code == 200:
        dados = resposta.json()
        apod = dados[0]

        titulo = apod['title']

        # tirando as tags HTML da explicacao
        soup = BeautifulSoup(apod['explanation'], 'html.parser')
        explicacao = soup.get_text()
        explicacao = explicacao.replace('Explanation:', '')

        # a frase final sempre comeca com "Tomorrow", entao cortamos a partir dela
        posicao = explicacao.find('Tomorrow')
        if posicao != -1:
            explicacao = explicacao[:posicao]

        st.subheader(titulo)
        st.write(apod['date'])

        # o APOD do dia pode ser imagem ou video
        if apod['media_type'] == 'image':
            st.image(apod['url'])
        else:
            st.video(apod['url'])

        st.write(explicacao)
    else:
        st.error('Erro na requisicao: ' + str(resposta.status_code))

# ABA 3: EXOPLANETAS
with aba3:
    st.header('Exoplanetas por metodo de descoberta')

    url_exo = 'https://exoplanetarchive.ipac.caltech.edu/TAP/sync'
    consulta = 'select discoverymethod, count(*) as total from pscomppars group by discoverymethod order by total desc'
    parametros = {
        'query': consulta,
        'format': 'json'
    }
    resposta = requests.get(url_exo, params=parametros)

    if resposta.status_code == 200:
        dados = resposta.json()
        df_exo = pd.DataFrame(dados)

        grafico = px.bar(
            df_exo,
            x='discoverymethod',
            y='total',
            text='total',
            log_y=True,
            title='Exoplanetas por metodo de descoberta'
        )
        st.plotly_chart(grafico)
    else:
        st.error('Erro na requisicao: ' + str(resposta.status_code))

# ABA 4: EVENTOS NATURAIS
with aba4:
    st.header('Eventos naturais das ultimas 48 horas')

    url_eonet = 'https://eonet.gsfc.nasa.gov/api/v3/events'
    parametros = {
        'days': 2
    }
    resposta = requests.get(url_eonet, params=parametros)

    if resposta.status_code == 200:
        dados = resposta.json()

        lista = []
        for evento in dados['events']:
            # pegamos a posicao mais recente do evento
            local = evento['geometry'][-1]

            # so pontos [longitude, latitude] (alguns eventos vem como area)
            if local['type'] == 'Point':
                lista.append({
                    'evento': evento['title'],
                    'categoria': evento['categories'][0]['title'],
                    'longitude': local['coordinates'][0],
                    'latitude': local['coordinates'][1]
                })

        df_eventos = pd.DataFrame(lista)

        mapa = px.scatter_geo(
            df_eventos,
            lat='latitude',
            lon='longitude',
            color='categoria',
            hover_name='evento',
            title='Eventos naturais (EONET)'
        )
        st.plotly_chart(mapa)
    else:
        st.error('Erro na requisicao: ' + str(resposta.status_code))
