"""Chat no terminal para testar o agente. Rode da raiz do projeto:

    python -m scripts.chat_cli

Digite 'sair' para encerrar.
"""
from app.agent import conversar
from app.menu import carregar_cardapio
from app.rag import carregar_indice
from app.session import RepositorioSessoes


def main() -> None:
    pratos = carregar_cardapio()
    indice = carregar_indice()
    sessao = RepositorioSessoes().obter("terminal")
    print("Atendente virtual. Digite 'sair' para encerrar.\n")

    while True:
        pergunta = input("Você: ").strip()
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if not pergunta:
            continue

        r = conversar(pergunta, sessao, pratos, indice)
        print(f"\nAtendente: {r['texto']}\n")
        for c in r["chamadas"]:
            erro = f" erro={c['erro']}" if c["erro"] else ""
            print(f"  [ferramenta: {c['nome']}({c['args']}) -> ok={c['ok']}{erro}]")
        if r["alergias"]:
            print(f"  [alergias registradas: {', '.join(r['alergias'])}]")
        usados = ", ".join(f"{nome} ({score})" for nome, score in r["pratos_usados"])
        print(f"  [contexto: {usados}]")
        print(
            f"  [tokens: {r['tokens_entrada']} entrada / {r['tokens_saida']} saída | "
            f"{r['latencia_s']} s | US$ {r['custo_usd']:.6f}]\n"
        )


if __name__ == "__main__":
    main()
