"""Busca semantica: transforma pratos em vetores e acha os mais parecidos com a pergunta."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config
from app.llm import gerar_embeddings
from app.schemas import Prato

CAMINHO_INDICE = Path(__file__).resolve().parent.parent / "data" / "embeddings.json"


@dataclass
class IndiceVetorial:
    modelo: str
    ids: list[int]
    hashes: list[str]
    matriz: np.ndarray  # uma linha por prato, ja normalizada


def texto_do_prato(prato: Prato) -> str:
    """Texto que representa o prato no indice (1 prato = 1 chunk).

    O preco fica de fora de proposito: numeros pouco ajudam a busca por significado
    e o preco real e consultado no cardapio, nao no vetor.
    """
    alergenicos = ", ".join(a.value for a in prato.alergenicos) or "nenhum"
    return (
        f"{prato.nome}. Categoria: {prato.categoria.value}. {prato.descricao} "
        f"Ingredientes: {', '.join(prato.ingredientes)}. Alergenicos: {alergenicos}."
    )


def normalizar(vetores) -> np.ndarray:
    """Deixa cada vetor com comprimento 1. Depois disso, produto escalar = cosseno."""
    m = np.asarray(vetores, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    normas = np.linalg.norm(m, axis=1, keepdims=True)
    if np.any(normas == 0):
        raise ValueError("vetor nulo recebido; nao da para normalizar")
    return m / normas


def top_k(matriz: np.ndarray, consulta: np.ndarray, k: int = 3) -> list[tuple[int, float]]:
    """Devolve (posicao, similaridade) dos k vetores mais parecidos, do melhor ao pior."""
    similaridades = matriz @ consulta
    k = min(k, len(similaridades))
    posicoes = np.argsort(-similaridades)[:k]
    return [(int(i), float(similaridades[i])) for i in posicoes]


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def construir_indice(pratos: list[Prato]) -> IndiceVetorial:
    textos = [texto_do_prato(p) for p in pratos]
    vetores = gerar_embeddings(textos, tipo="documento")
    return IndiceVetorial(
        modelo=config.EMBEDDING_MODEL,
        ids=[p.id for p in pratos],
        hashes=[_hash(t) for t in textos],
        matriz=normalizar(vetores),
    )


def salvar_indice(indice: IndiceVetorial, caminho: Path = CAMINHO_INDICE) -> None:
    conteudo = {
        "modelo": indice.modelo,
        "dimensao": int(indice.matriz.shape[1]),
        "itens": [
            {"id": i, "hash": h, "vetor": v.tolist()}
            for i, h, v in zip(indice.ids, indice.hashes, indice.matriz)
        ],
    }
    Path(caminho).write_text(json.dumps(conteudo), encoding="utf-8")


def carregar_indice(caminho: Path = CAMINHO_INDICE) -> IndiceVetorial:
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} nao existe. Gere o indice com: python -m scripts.build_index"
        )
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    itens = dados["itens"]
    return IndiceVetorial(
        modelo=dados["modelo"],
        ids=[i["id"] for i in itens],
        hashes=[i["hash"] for i in itens],
        matriz=np.asarray([i["vetor"] for i in itens], dtype=np.float32),
    )


def indice_desatualizado(pratos: list[Prato], indice: IndiceVetorial) -> bool:
    """True se o cardapio ou o modelo mudou desde que o indice foi gerado."""
    esperado = [(p.id, _hash(texto_do_prato(p))) for p in pratos]
    atual = list(zip(indice.ids, indice.hashes))
    return esperado != atual or indice.modelo != config.EMBEDDING_MODEL


def buscar(
    consulta: str, pratos: list[Prato], indice: IndiceVetorial, k: int = 3
) -> list[tuple[Prato, float]]:
    """Acha os k pratos mais relevantes para a pergunta."""
    if indice_desatualizado(pratos, indice):
        raise RuntimeError(
            "O indice esta desatualizado em relacao ao cardapio ou ao modelo. "
            "Rode: python -m scripts.build_index"
        )
    vetor = normalizar(gerar_embeddings([consulta], tipo="consulta"))[0]
    por_id = {p.id: p for p in pratos}
    return [(por_id[indice.ids[pos]], score) for pos, score in top_k(indice.matriz, vetor, k)]
