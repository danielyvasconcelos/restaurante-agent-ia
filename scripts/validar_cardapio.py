"""Valida o cardapio e mostra um resumo. Rode da raiz do projeto:

    python -m scripts.validar_cardapio
"""
from app.menu import carregar_cardapio


def main() -> None:
    pratos = carregar_cardapio()
    print(f"Cardapio valido: {len(pratos)} pratos\n")
    for p in pratos:
        alergicos = ", ".join(a.value for a in p.alergenicos) or "nenhum"
        print(f"{p.id:>2} | {p.nome:<32} | R$ {p.preco:>6.2f} | alergenicos: {alergicos}")


if __name__ == "__main__":
    main()
