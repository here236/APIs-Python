import requests
from multiprocessing import Process
import pandas as pd
import matplotlib.pyplot as plt

API_KEY = ""
BASE = "https://api.themoviedb.org/3"


def get(caminho, **extra):
    params = {"api_key": API_KEY, "language": "pt-BR", **extra}
    r = requests.get(BASE + caminho, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def ler_opcao(mensagem, validos):
    while True:
        try:
            valor = int(input(mensagem).strip())
        except ValueError:
            print("Digite apenas números.")
            continue
        if valor in validos:
            return valor
        print("Opção inválida, tente novamente.")


def escolher_genero():
    generos = get("/genre/movie/list")["genres"]
    for g in generos:
        print(f"{g['id']} - {g['name']}")
    validos = [0] + [g["id"] for g in generos]
    return ler_opcao("ID do gênero (0 para todos): ", validos)


def escolher_ordem():
    print("1 - Mais bem avaliados")
    print("2 - Mais populares")
    op = ler_opcao("Escolha: ", [1, 2])
    return "vote_average.desc" if op == 1 else "popularity.desc"


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
    print("Sinopse:", d["overview"] or "Sem sinopse disponível.")

    elenco = get(f"/movie/{filme_id}/credits")["cast"][:10]
    print("\nElenco:")
    for i, a in enumerate(elenco, 1):
        print(f"{i} - {a['name']} como {a['character']}")
    return elenco


def filmografia(pessoa_id):
    creditos = get(f"/person/{pessoa_id}/movie_credits")["cast"]
    if not creditos:
        print("Nenhuma filmografia encontrada.")
        return
    df = pd.DataFrame(creditos)
    df = df[["title", "release_date", "vote_average"]].dropna()
    df = df.sort_values("release_date", ascending=False).head(15)
    print(df.to_string(index=False))


def main():
    try:
        genero = escolher_genero()
        ordem = escolher_ordem()
        filmes = buscar_filmes(genero, ordem)
    except requests.RequestException:
        print("Erro ao acessar a API. Verifique sua chave e sua conexão.")
        return

    if not filmes:
        print("Nenhum filme encontrado para esse gênero.")
        return

    df = pd.DataFrame(filmes)[["id", "title", "vote_average", "popularity"]]
    df.columns = ["id", "titulo", "nota", "popularidade"]
    df.index = range(1, len(df) + 1)
    print(df[["titulo", "nota", "popularidade"]])

    Process(target=grafico, args=(df, ordem)).start()

    while True:
        escolha = ler_opcao("\nNúmero do filme para detalhes (0 para sair): ", range(0, len(df) + 1))
        if escolha == 0:
            break

        try:
            elenco = detalhes_filme(int(df.loc[escolha, "id"]))
            if not elenco:
                continue
            ator = ler_opcao("\nNúmero do ator para ver filmografia (0 para pular): ", range(0, len(elenco) + 1))
            if ator != 0:
                filmografia(elenco[ator - 1]["id"])
        except requests.RequestException:
            print("Erro ao buscar os dados. Tente novamente.")


if __name__ == "__main__":
    main()