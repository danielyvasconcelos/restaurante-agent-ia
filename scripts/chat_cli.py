"""Chat no terminal para testar o RAG. Rode da raiz do projeto:

    python -m scripts.chat_cli

Digite 'sair' para encerrar.
"""
from app.agent import responder
from app.menu import carregar_cardapio
from app.rag import carregar_indice


def main() -> None:
    pratos = carregar_cardapio()
    indice = carregar_indice()
    print("Atendente virtual. Digite 'sair' para encerrar.\n")

    while True:
        pergunta = input("Você: ").strip()
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if not pergunta:
            continue

        r = responder(pergunta, pratos, indice)
        print(f"\nAtendente: {r['texto']}\n")
        usados = ", ".join(f"{nome} ({score})" for nome, score in r["pratos_usados"])
        print(f"  [contexto: {usados}]")
        print(
            f"  [tokens: {r['tokens_entrada']} entrada / {r['tokens_saida']} saída | "
            f"{r['latencia_s']} s | US$ {r['custo_usd']:.6f}]\n"
        )


if __name__ == "__main__":
    main()
