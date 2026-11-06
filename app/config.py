"""Configuracoes do projeto, lidas de variaveis de ambiente (.env)."""
import os

from dotenv import load_dotenv

# Le o arquivo .env (se existir) e coloca os valores no ambiente.
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# Precos em USD por 1 milhao de tokens, do modelo gemini-3.1-flash-lite.
# Fonte: https://ai.google.dev/gemini-api/docs/pricing (conferido em 02/11/2026).
# Se trocar GEMINI_MODEL, atualize estes valores, senao o custo calculado fica errado.
PRECO_ENTRADA_POR_MILHAO = 0.25
PRECO_SAIDA_POR_MILHAO = 1.50


def validar_config() -> None:
    """Falha cedo, com mensagem clara, se a chave nao estiver configurada."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY nao encontrada. Copie .env.example para .env e preencha."
        )
