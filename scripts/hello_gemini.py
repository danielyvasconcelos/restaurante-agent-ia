"""Primeira chamada ao Gemini. Rode da raiz do projeto:

    python -m scripts.hello_gemini
    python -m scripts.hello_gemini --temperatura 1.5
"""
import argparse

from app.llm import chamar_llm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--temperatura", type=float, default=0.7)
    args = parser.parse_args()

    resultado = chamar_llm(
        prompt="Descreva em duas frases um prato de feijoada para um cliente.",
        system="Voce e um atendente simpatico de um restaurante brasileiro.",
        temperature=args.temperatura,
    )

    print(f"Modelo: {resultado['modelo']} | temperatura: {args.temperatura}")
    print(f"\nResposta:\n{resultado['texto']}\n")
    print(f"Tokens de entrada: {resultado['tokens_entrada']}")
    print(f"Tokens de saida:   {resultado['tokens_saida']} "
          f"(pensamento: {resultado['tokens_pensamento']})")
    print(f"Latencia:          {resultado['latencia_s']} s")
    print(f"Custo estimado:    US$ {resultado['custo_usd']:.6f}")


if __name__ == "__main__":
    main()
