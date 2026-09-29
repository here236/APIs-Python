import requests
import pandas as pd
import matplotlib.pyplot as plt

API_KEY = ""
BASE = "https://api.themoviedb.org/3"


def get(caminho, **extra):
    params = {"api_key": API_KEY, "language": "pt-BR", **extra}
    r = requests.get(BASE + caminho, params=params)
    r.raise_for_status()
    return r.json()


def escolher_genero():
    generos = get("/genre/movie/list")["genres"]
    for g in generos:
        print(f"{g['id']} - {g['name']}")
    return int(input("ID do gênero (0 para todos): "))


def escolher_ordem():
    print("1 - Mais bem avaliados")
    print("2 - Mais populares")
    op = input("Escolha: ")
    return "vote_average.desc" if op == "1" else "popularity.desc"


def buscar_filmes(genero, ordem):
    extra = {"sort_by": ordem, "vote_count.gte": 500}
    if genero:
        extra["with_genres"] = genero
    return get("/discover/movie", **extra)["results"][:10]


def grafico(df, ordem):
    coluna = "nota" if ordem == "vote_average.desc" else "popularidade"
    df = df.sort_values(coluna)
    plt.figure(figsize=(10, 6))
    plt.barh(df["titulo"], df[coluna], color="steelblue")
    plt.xlabel(coluna.capitalize())
    plt.title("Ranking de Filmes")
    plt.tight_layout()
    plt.show()


def detalhes_filme(filme_id):
    d = get(f"/movie/{filme_id}")
    print("\nTítulo:", d["title"])
    print("Lançamento:", d["release_date"])
    print("Duração:", d["runtime"], "min")
    print("Gêneros:", ", ".join(g["name"] for g in d["genres"]))
    print("Nota:", d["vote_average"])
    print("Sinopse:", d["overview"])

    elenco = get(f"/movie/{filme_id}/credits")["cast"][:10]
    print("\nElenco:")
    for i, a in enumerate(elenco, 1):
        print(f"{i} - {a['name']} como {a['character']}")
    return elenco


def filmografia(pessoa_id):
    creditos = get(f"/person/{pessoa_id}/movie_credits")["cast"]
    df = pd.DataFrame(creditos)
    df = df[["title", "release_date", "vote_average"]].dropna()
    df = df.sort_values("release_date", ascending=False).head(15)
    print(df.to_string(index=False))


def main():
    genero = escolher_genero()
    ordem = escolher_ordem()
    filmes = buscar_filmes(genero, ordem)

    df = pd.DataFrame(filmes)[["id", "title", "vote_average", "popularity"]]
    df.columns = ["id", "titulo", "nota", "popularidade"]
    df.index = range(1, len(df) + 1)
    print(df[["titulo", "nota", "popularidade"]])

    grafico(df, ordem)

    while True:
        escolha = input("\nNúmero do filme para detalhes (0 para sair): ")
        if escolha == "0":
            break
        filme_id = int(df.loc[int(escolha), "id"])
        elenco = detalhes_filme(filme_id)

        ator = input("\nNúmero do ator para ver filmografia (0 para pular): ")
        if ator != "0":
            filmografia(elenco[int(ator) - 1]["id"])


main()