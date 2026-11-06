"""Cliente do Gemini: chamadas de texto, chamadas com ferramentas e embeddings."""
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
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_S * 1000),  # em ms
        )
    return _client


def calcular_custo(tokens_entrada: int, tokens_saida: int) -> float:
    """Custo estimado em USD. Tokens de saida incluem os de 'pensamento'."""
    return (
        tokens_entrada * config.PRECO_ENTRADA_POR_MILHAO
        + tokens_saida * config.PRECO_SAIDA_POR_MILHAO
    ) / 1_000_000


def _metricas(resposta, latencia: float) -> dict:
    uso = resposta.usage_metadata
    tokens_entrada = (uso.prompt_token_count or 0) if uso else 0
    tokens_resposta = (uso.candidates_token_count or 0) if uso else 0
    tokens_pensamento = (uso.thoughts_token_count or 0) if uso else 0
    tokens_saida = tokens_resposta + tokens_pensamento
    return {
        "modelo": config.GEMINI_MODEL,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "tokens_pensamento": tokens_pensamento,
        "latencia_s": round(latencia, 2),
        "custo_usd": calcular_custo(tokens_entrada, tokens_saida),
    }


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
    return {"texto": resposta.text or "", **_metricas(resposta, latencia)}


def chamar_llm_com_ferramentas(
    contents: list,
    system: str,
    ferramentas: list,
    temperature: float = 0.2,
    max_output_tokens: int = 1024,
) -> tuple:
    """Uma rodada de conversa com ferramentas. Devolve (resposta_bruta, metricas).

    A execucao automatica de funcoes do SDK fica DESLIGADA: quem executa as
    ferramentas e o nosso codigo (agent.py). Assim controlamos limites, erros e logs.
    """
    client = _get_client()

    inicio = time.perf_counter()
    resposta = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=ferramentas,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    latencia = time.perf_counter() - inicio
    return resposta, _metricas(resposta, latencia)


def texto_da_resposta(resposta) -> str:
    """Junta as partes de texto da resposta (ignora chamadas de funcao e 'pensamento')."""
    if not resposta.candidates or not resposta.candidates[0].content:
        return ""
    partes = resposta.candidates[0].content.parts or []
    return "".join(p.text for p in partes if p.text and not p.thought).strip()


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
