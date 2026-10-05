import requests
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

api_key = ""

url = "https://api.balldontlie.io/v1/stats"

headers = {
    "Authorization": api_key
}

parametros = {
    "seasons[]": 2025,
    "per_page": 100
}

resposta = requests.get(
    url,
    headers = headers,
    params = parametros
)

print("status:", resposta.status_code)
print(resposta.text)

dados = resposta.json()

estatisticas = dados["data"]

for jogador in estatisticas:

    nome = jogador["player"]["first_name"]
    sobrenome = jogador["player"]["last_name"]
    pontos = jogador["pts"]
    rebotes = jogador["reb"]
    assistencias = jogador["ast"]

    print(nome, sobrenome)
    print("Pontos:", pontos)
    print("Rebotes:", rebotes)
    print("Assistências:", assistencias)
    print("------------------------")

lista = []

for jogador in estatisticas:

    nome = jogador["player"]["first_name"] + " " + jogador["player"]["last_name"]

    pontos = jogador["pts"]
    rebotes = jogador["reb"]
    assistencias = jogador["ast"]

    lista.append({
        "nome": nome,
        "pontos": pontos,
        "rebotes": rebotes,
        "assistencias": assistencias
    })

df = pd.DataFrame(lista)

print("\nTABELA:")
print(df)

media_pontos = df["pontos"].mean()
media_rebotes = df["rebotes"].mean()
media_assistencias = df["assistencias"].mean()

print("\nMÉDIAS")

print("Média de pontos:", media_pontos)
print("Média de rebotes:", media_rebotes)
print("Média de assistências:", media_assistencias)

ranking = df.sort_values(
    "pontos",
    ascending=False
)

print("\nRANKING DE PONTOS:")

print(ranking[["nome", "pontos"]].head(10))

jogador1 = df[df["nome"].str.contains("Stephen Curry")]

jogador2 = df[df["nome"].str.contains("LeBron James")]


if len(jogador1) > 0 and len(jogador2) > 0:

    nome1 = jogador1.iloc[0]["nome"]
    nome2 = jogador2.iloc[0]["nome"]

    pontos1 = jogador1.iloc[0]["pontos"]
    pontos2 = jogador2.iloc[0]["pontos"]

    dados_grafico = pd.DataFrame({
        "Jogador": [nome1, nome2],
        "Pontos": [pontos1, pontos2]
    })

    sns.barplot(
        data=dados_grafico,
        x="Jogador",
        y="Pontos"
    )

    plt.title("Comparação de Pontos")
    plt.xlabel("Jogadores")
    plt.ylabel("Pontos")

    plt.show()

else:

    print("\nUm dos jogadores não foi encontrado.")

top10 = df.sort_values(
    "pontos",
    ascending=False
).head(10)

print("\nTOP 10 JOGADORES POR PONTOS:")

print(top10[[
    "nome",
    "pontos",
    "rebotes",
    "assistencias"
]])