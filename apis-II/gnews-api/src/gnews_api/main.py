import requests
import os
from dotenv import load_dotenv
from collections import Counter
import json

load_dotenv(".env")
APIKEY = os.getenv("API_KEY")
URL_BASE = "https://gnews.io/api/v4/"

def top_headlines():
    CONJUNCOES = {"e", "ou", "mas", "pode", "no", "não", "é","chegam", "porque", "porém", "pois", "nem", "de", "da", "com","globo", "e", "estão", "pessoas", "que", "crédito", "r$", "1", "na", "a", "e", "para", "em", "o", "do"}
    ENDPOINT = "top-headlines"
    URL = URL_BASE + ENDPOINT + f"?category=general&lang=pt&country=br&max=100&apikey={APIKEY}"

    response_news = requests.get(URL)
    if response_news.status_code != 200:
        print("Não foi possivel realizar a requisição")
        return

    # with open("dados.json", "r", encoding="utf-8") as arquivo:
    #     dados_noticias = json.load(arquivo)

    print("Principais Notícias do Dia:")
    cont = Counter()
    dados_noticias = response_news.json()
    for noticia in dados_noticias['articles'][:5]:
        print(f"- {noticia['title']}")

        palavras = noticia['title'].lower().split()

        palavras_filtradas = [
            palavra for palavra in palavras
            if palavra not in CONJUNCOES
        ]
        cont.update(palavras_filtradas)

        palavras = noticia['description'].lower().split()

        palavras_filtradas = [
            palavra for palavra in palavras
            if palavra not in CONJUNCOES
        ]
        cont.update(palavras_filtradas)

        palavras = noticia['source']['name'].lower().split()

        palavras_filtradas = [
            palavra for palavra in palavras
            if palavra not in CONJUNCOES
        ]

        cont.update(palavras_filtradas)

    top5 = cont.most_common(5)
    for posicao, (palavra, quantidade) in enumerate(top5, 1):
        print(f"{posicao}. {palavra}: {quantidade}")


def main():
    top_headlines()


if __name__ == "__main__":
    main()