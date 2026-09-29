import weatherApi
import moviesApi



APIs = {
    1:("API de filmes", moviesApi.main),
    2:("API de Clima", weatherApi.main),
}



def ler_opcao(mensagem, validos):
    while True:
        try:
            valor = int(input(mensagem).strip())
        except ValueError:
            print("Digite apenas números.")
            continue
        if valor in validos:
            return valor
        print("Opção invalida, tente novamente.")


def mostrar_menu():
    print("\n=======APIs=======")
    for numero, (nome, _) in APIs.items():
        print(f"{numero} - {nome}")
    print("0 - Sair")
 


def menu(): 
    while True:
        mostrar_menu()
        opcao = ler_opcao ("Escolha:", range(0, len(APIs) + 1))
        if opcao == 0:
            print("Encerando Programa")
            break
        APIs[opcao][1]()


if __name__ == "__main__":
    menu()
