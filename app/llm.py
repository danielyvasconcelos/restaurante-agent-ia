"""Cliente do Gemini: uma funcao que chama o LLM e devolve texto + metricas."""
import time

from google import genai
from google.genai import types

from app import config

_client = None


def _get_client() -> genai.Client:
    """Cria o cliente uma unica vez e reaproveita nas proximas chamadas."""
    global _client
    if _client is None:
        config.validar_config()
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def calcular_custo(tokens_entrada: int, tokens_saida: int) -> float:
    """Custo estimado em USD. Tokens de saida incluem os de 'pensamento'."""
    return (
        tokens_entrada * config.PRECO_ENTRADA_POR_MILHAO
        + tokens_saida * config.PRECO_SAIDA_POR_MILHAO
    ) / 1_000_000


def chamar_llm(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
) -> dict:
    """Envia um prompt ao Gemini e devolve o texto e as metricas da chamada."""
    client = _get_client()

    inicio = time.perf_counter()
    resposta = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    latencia = time.perf_counter() - inicio

    uso = resposta.usage_metadata
    tokens_entrada = uso.prompt_token_count or 0
    tokens_resposta = uso.candidates_token_count or 0
    tokens_pensamento = uso.thoughts_token_count or 0
    tokens_saida = tokens_resposta + tokens_pensamento

    return {
        "texto": resposta.text or "",
        "modelo": config.GEMINI_MODEL,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "tokens_pensamento": tokens_pensamento,
        "latencia_s": round(latencia, 2),
        "custo_usd": calcular_custo(tokens_entrada, tokens_saida),
    }


# Para busca, documento e consulta usam "tipos de tarefa" diferentes: o modelo
# ajusta o vetor conforme o papel do texto (ser encontrado vs. encontrar).
TIPOS_EMBEDDING = {"documento": "RETRIEVAL_DOCUMENT", "consulta": "RETRIEVAL_QUERY"}


def _embed(textos: list[str], tipo: str) -> list[list[float]]:
    resposta = _get_client().models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=textos,
        config=types.EmbedContentConfig(
            task_type=TIPOS_EMBEDDING[tipo],
            output_dimensionality=config.EMBEDDING_DIMENSAO,
        ),
    )
    return [list(e.values) for e in resposta.embeddings]


def gerar_embeddings(textos: list[str], tipo: str = "documento") -> list[list[float]]:
    """Converte textos em vetores. tipo: 'documento' (pratos) ou 'consulta' (pergunta)."""
    if tipo not in TIPOS_EMBEDDING:
        raise ValueError(f"tipo invalido: {tipo!r}. Use 'documento' ou 'consulta'.")
    if not textos:
        return []

    vetores = _embed(textos, tipo)
    if len(vetores) != len(textos):
        # Alguns modelos juntam varios textos em um unico vetor. Como precisamos de
        # um vetor por texto, repetimos uma chamada por texto.
        vetores = [_embed([t], tipo)[0] for t in textos]
    return vetores
