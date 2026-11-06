"""Busca pratos por significado. Rode da raiz do projeto:

    python -m scripts.buscar "algo leve sem carne"
    python -m scripts.buscar "tenho alergia a camarao" -k 5
"""
import argparse

from app.menu import carregar_cardapio
from app.rag import buscar, carregar_indice


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("consulta")
    parser.add_argument("-k", type=int, default=3)
    args = parser.parse_args()

    pratos = carregar_cardapio()
    indice = carregar_indice()
    print(f"Pergunta: {args.consulta}\n")
    for prato, score in buscar(args.consulta, pratos, indice, k=args.k):
        print(f"{score:.3f} | {prato.nome}")


if __name__ == "__main__":
    main()
