import json
import requests 
import matplotlib as plt

apiKey = ''
cidade= ["uberlândia", "xique-xique","colinas do Tocantins", "ribeirão preto", "três lagoas"]
dados= []

for cidades in cidade:
    cidade = cidades
    urlClima = f"https://api.openweathermap.org/data/2.5/weather?q={cidade}&appid={apiKey}&units=metric"
    dadosClima = requests.get(urlClima)
    clima = dadosClima.json()

    dados.append({
        "cidade" : cidade,
        "minima" : clima["main"]["temp_min"],
        "maxima" : clima["main"]["temp_max"]
    })

with open("clima.json", "w", encoding="utf-8") as arquivo:
    json.dump(dados, arquivo, indent=4, ensure_ascii=False)


with open("clima.json", "r", encoding="utf-8") as arquivo:
    dados = json.load(arquivo)

cidades = [item["cidade"] for item in dados]
minimas = [item["minima"] for item in dados]
maximas = [item["maxima"] for item in dados]

plt.bar(cidades, maximas, label="Máxima")
plt.bar(cidades, minimas, label="Mínima")

plt.xlabel("cidade")
plt.ylabel("Temperatura (°C)")
plt.title("Temperaturas")
plt.legend()

plt.show()

