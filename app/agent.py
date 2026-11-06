"""Agente do restaurante.

Etapa 4: responde perguntas usando RAG. Busca os pratos mais relevantes, coloca
no prompt de sistema como contexto e pede ao modelo que responda so com base neles.
"""
from app.llm import chamar_llm
from app.rag import IndiceVetorial, buscar
from app.schemas import Prato

PROMPT_SISTEMA = """Você é o atendente virtual de um restaurante brasileiro. Seja simpático, claro e breve.

Regras:
1. Responda SOMENTE com base nos pratos listados em "CARDÁPIO RELEVANTE" abaixo. Não use conhecimento externo sobre o restaurante.
2. Se a informação não estiver no cardápio fornecido, diga que não encontrou e sugira falar com um atendente humano. Nunca invente pratos, preços, ingredientes ou alergênicos.
3. Ao falar de ingredientes ou alergênicos, use exatamente o que consta no cardápio. Não conclua que um prato é seguro só porque ele não aparece na lista recebida.
4. Se a pessoa mencionar alergia ou restrição alimentar, informe os alergênicos do prato citado e recomende confirmar com a equipe do restaurante.
5. Responda em português do Brasil.

CARDÁPIO RELEVANTE:
{contexto}"""


def formatar_preco(preco) -> str:
    """49.9 -> 'R$ 49,90' (formato brasileiro)."""
    return f"R$ {preco:.2f}".replace(".", ",")


def montar_contexto(pratos: list[Prato]) -> str:
    """Transforma os pratos recuperados em texto para o prompt."""
    linhas = []
    for p in pratos:
        alergenicos = ", ".join(a.value for a in p.alergenicos) or "nenhum"
        linhas.append(
            f"- {p.nome} ({p.categoria.value}) - {formatar_preco(p.preco)}. "
            f"{p.descricao} Ingredientes: {', '.join(p.ingredientes)}. "
            f"Alergênicos: {alergenicos}."
        )
    return "\n".join(linhas)


def responder(
    pergunta: str,
    pratos: list[Prato],
    indice: IndiceVetorial,
    k: int = 4,
    temperature: float = 0.2,
) -> dict:
    """Recupera os k pratos mais relevantes e pede ao LLM que responda com base neles."""
    encontrados = buscar(pergunta, pratos, indice, k=k)
    contexto = montar_contexto([prato for prato, _ in encontrados])

    resultado = chamar_llm(
        prompt=pergunta,
        system=PROMPT_SISTEMA.format(contexto=contexto),
        temperature=temperature,  # baixa: queremos fidelidade ao cardapio, nao criatividade
    )
    resultado["pratos_usados"] = [(prato.nome, round(score, 3)) for prato, score in encontrados]
    return resultado
