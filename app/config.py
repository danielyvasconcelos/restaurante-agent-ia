"""Configuracoes do projeto, lidas de variaveis de ambiente (.env)."""
import os
from pathlib import Path

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

# Embeddings (Etapa 3). Podem ser trocados no .env sem mexer no codigo.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSAO = int(os.getenv("EMBEDDING_DIMENSAO", "768"))

# API (Etapa 8)
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "30"))  # tempo maximo de UMA chamada ao Gemini
MAX_PERGUNTAS_POR_SESSAO = 50  # cada turno reenvia o historico: conversa longa = custo crescente
MAX_SESSOES = 1000  # protege a memoria do servidor

# Metricas e protecao de custo (Etapa 9)
METRICAS_PATH = Path(
    os.getenv("METRICAS_PATH", str(Path(__file__).resolve().parent.parent / "data" / "metricas.jsonl"))
)
# Teto de gasto por dia (UTC). 0 desliga. Com chave paga, e uma rede de seguranca.
ORCAMENTO_DIARIO_USD = float(os.getenv("ORCAMENTO_DIARIO_USD", "2.0"))
