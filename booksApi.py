import requests
import pandas as pd
import matplotlib.pyplot as plt

busca = input("Digite o autor/título do livro: ")
api_key = ""

url = "https://www.googleapis.com/books/v1/volumes"
params = {
    "q": busca,
    "key": api_key,
}

resposta = requests.get(url, params = params)

if resposta.status_code != 200:
    print("Erro na requisição:", resposta.status_code)
    exit()

dados = resposta.json()

livros = []
for item in dados.get("items", []):
    info = item.get("volumeInfo", {})
    data = info.get("publishedDate", "")
    livros.append({
        "titulo": info.get("title", "Título desconhecido"),
        "autores": ", ".join(info.get("authors", ["Autor desconhecido"])),
        "ano": int(data[:4]) if data[:4].isdigit() else None,
        "genero": (info.get("categories") or ["Sem gênero"])[0],
    })

df = pd.DataFrame(livros)

if df.empty:
    print("Nenhum livro encontrado.")
    exit()

print(f"\nTotal de livros encontrados: {len(df)}")

# Desafio 1
print("\n10 livros mais antigos:")
antigos = df.dropna(subset=["ano"]).sort_values("ano").head(10)
print(antigos[["titulo", "autores", "ano"]].to_string(index=False))

# Desafio 2
fig, eixos = plt.subplots(1, 2, figsize=(14, 5))

df["genero"].value_counts().head(10).plot(
    kind="bar", ax=eixos[0], title="Gêneros mais comuns"
)
eixos[0].set_ylabel("Quantidade")

df["ano"].dropna().astype(int).value_counts().sort_index().plot(
    kind="bar", ax=eixos[1], title="Livros por ano de publicação"
)
eixos[1].set_ylabel("Quantidade")

plt.tight_layout()
plt.show()