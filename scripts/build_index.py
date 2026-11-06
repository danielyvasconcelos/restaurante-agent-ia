"""Gera os embeddings do cardapio e salva em data/embeddings.json.

    python -m scripts.build_index
"""
from app.menu import carregar_cardapio
from app.rag import CAMINHO_INDICE, construir_indice, salvar_indice


def main() -> None:
    pratos = carregar_cardapio()
    indice = construir_indice(pratos)
    salvar_indice(indice)
    print(f"Indice gerado: {len(pratos)} pratos, {indice.matriz.shape[1]} dimensoes")
    print(f"Modelo: {indice.modelo}")
    print(f"Salvo em: {CAMINHO_INDICE}")


if __name__ == "__main__":
    main()
