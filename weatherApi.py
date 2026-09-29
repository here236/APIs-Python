import json
import requests
import matplotlib.pyplot as plt

apiKey = ''
cidades = ["uberlândia", "xique-xique", "colinas do Tocantins", "ribeirão preto", "três lagoas"]


def buscar_dados():
    dados = []
    for cidade in cidades:
        urlClima = f"https://api.openweathermap.org/data/2.5/weather?q={cidade}&appid={apiKey}&units=metric"
        clima = requests.get(urlClima).json()

        urlPrevisao = f"https://api.openweathermap.org/data/2.5/forecast?q={cidade}&appid={apiKey}&units=metric"
        previsao = requests.get(urlPrevisao).json()

        dias = {}
        for item in previsao["list"]:
            dia = item["dt_txt"][:10]
            if dia not in dias:
                dias[dia] = {"temps": [], "chuva": 0}
            dias[dia]["temps"].append(item["main"]["temp"])
            dias[dia]["chuva"] += item.get("rain", {}).get("3h", 0)

        proximos = []
        for dia, valores in dias.items():
            proximos.append({
                "dia": dia,
                "minima": min(valores["temps"]),
                "maxima": max(valores["temps"]),
                "chuva": round(valores["chuva"], 2)
            })

        dados.append({
            "cidade": cidade,
            "minima": clima["main"]["temp_min"],
            "maxima": clima["main"]["temp_max"],
            "umidade": clima["main"]["humidity"],
            "pressao": clima["main"]["pressure"],
            "vento": clima["wind"]["speed"],
            "chuva": clima.get("rain", {}).get("1h", 0),
            "previsao": proximos
        })

    with open("clima.json", "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4, ensure_ascii=False)

    return dados
    
def mostrar_graficos(dados):
    nomes = [item["cidade"] for item in dados]
    minimas = [item["minima"] for item in dados]
    maximas = [item["maxima"] for item in dados]
    umidades = [item["umidade"] for item in dados]
    pressoes = [item["pressao"] for item in dados]
    ventos = [item["vento"] for item in dados]
    chuvas = [item["chuva"] for item in dados]
    
    posicoes = range(len(nomes))
    largura = 0.4
    
    plt.figure(figsize=(10, 6))
    plt.bar([p - largura / 2 for p in posicoes], minimas, largura, label="Mínima", color="steelblue")
    plt.bar([p + largura / 2 for p in posicoes], maximas, largura, label="Máxima", color="tomato")
    plt.xticks(posicoes, nomes, rotation=15)
    plt.xlabel("Cidade")
    plt.ylabel("Temperatura (°C)")
    plt.title("Temperaturas atuais")
    plt.legend()
    plt.tight_layout()
    
    fig, eixos = plt.subplots(2, 2, figsize=(12, 8))
    
    eixos[0][0].bar(nomes, umidades, color="teal")
    eixos[0][0].set_title("Umidade (%)")
    
    eixos[0][1].bar(nomes, pressoes, color="purple")
    eixos[0][1].set_title("Pressão (hPa)")
    
    eixos[1][0].bar(nomes, ventos, color="orange")
    eixos[1][0].set_title("Vento (m/s)")
    
    eixos[1][1].bar(nomes, chuvas, color="navy")
    eixos[1][1].set_title("Precipitação na última hora (mm)")
    
    for linha in eixos:
        for eixo in linha:
            eixo.tick_params(axis="x", rotation=20)
    plt.tight_layout()
    
    plt.figure(figsize=(10, 6))
    for item in dados:
        dias = [p["dia"][5:] for p in item["previsao"]]
        maximasDia = [p["maxima"] for p in item["previsao"]]
        plt.plot(dias, maximasDia, marker="o", label=item["cidade"])
    plt.xlabel("Dia")
    plt.ylabel("Temperatura máxima (°C)")
    plt.title("Previsão dos próximos dias")
    plt.legend()
    plt.tight_layout()
    
    plt.figure(figsize=(10, 6))
    larguraChuva = 0.15
    for i, item in enumerate(dados):
        dias = [p["dia"][5:] for p in item["previsao"]]
        chuvaDia = [p["chuva"] for p in item["previsao"]]
        deslocamento = [j + i * larguraChuva for j in range(len(dias))]
        plt.bar(deslocamento, chuvaDia, larguraChuva, label=item["cidade"])
    plt.xticks([j + larguraChuva * 2 for j in range(len(dias))], dias)
    plt.xlabel("Dia")
    plt.ylabel("Precipitação prevista (mm)")
    plt.title("Chuva prevista por dia")
    plt.legend()
    plt.tight_layout()
    
    plt.show()

def main():
    try:
        dados= buscar_dados()
    except (requests.RequestException, KeyError):
        print("Erro ao buscar dados, Verifique sua chave de api e sua conexão")
        return
    mostrar_graficos(dados)



if __name__ == "__main__":
    main()