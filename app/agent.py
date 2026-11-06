"""Agente do restaurante.

Etapa 4: responde perguntas usando RAG. Busca os pratos mais relevantes, coloca
no prompt de sistema como contexto e pede ao modelo que responda so com base neles.
"""
from google.genai import types

from app.guardrails import detectar_alergias, itens_em_conflito, restricao_nao_reconhecida
from app.llm import chamar_llm, chamar_llm_com_ferramentas, texto_da_resposta
from app.menu import formatar_preco
from app.rag import IndiceVetorial, buscar
from app.schemas import Prato
from app.session import Sessao
from app.tools import FERRAMENTAS, executar

PROMPT_SISTEMA = """Você é o atendente virtual de um restaurante brasileiro. Seja simpático, claro e breve.

Regras:
1. Responda SOMENTE com base nos pratos listados em "CARDÁPIO RELEVANTE" abaixo. Não use conhecimento externo sobre o restaurante.
2. Se a informação não estiver no cardápio fornecido, diga que não encontrou e sugira falar com um atendente humano. Nunca invente pratos, preços, ingredientes ou alergênicos.
3. Ao falar de ingredientes ou alergênicos, use exatamente o que consta no cardápio. Não conclua que um prato é seguro só porque ele não aparece na lista recebida.
4. Se a pessoa mencionar alergia ou restrição alimentar, informe os alergênicos do prato citado e recomende confirmar com a equipe do restaurante.
5. Responda em português do Brasil.

CARDÁPIO RELEVANTE:
{contexto}"""


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


# ---------------------------------------------------------------------------
# Etapa 6: agente com ferramentas (function calling)
# ---------------------------------------------------------------------------
PROMPT_AGENTE = """Você é o atendente virtual de um restaurante brasileiro. Seja simpático, claro e breve. Cumprimente apenas na primeira mensagem da conversa.

Regras sobre o cardápio:
1. Para informar pratos, preços, ingredientes e alergênicos, use SOMENTE o "CARDÁPIO RELEVANTE" abaixo ou o resultado das ferramentas. Nunca invente nada.
2. O cardápio relevante traz só alguns pratos. Para perguntas que dependem de TODO o cardápio (por exemplo "quais pratos não têm lactose", "que sobremesas vocês têm", "o que custa até 30 reais"), use a ferramenta filtrar_pratos e responda com o que ela devolver.
3. Se a informação não existir, diga que não encontrou e sugira falar com um atendente humano.
4. Se a pessoa mencionar alergia ou restrição, informe os alergênicos do prato e recomende confirmar com a equipe do restaurante.

Regras sobre o pedido:
5. Para adicionar ou remover itens, SEMPRE use as ferramentas. Nunca diga que adicionou ou removeu algo sem a ferramenta ter confirmado (ok = true).
6. Se a ferramenta indicar que o prato é ambíguo, pergunte qual das opções o cliente quer. Se der erro, explique o motivo com simpatia.
7. Para valores e totais, use os números devolvidos pelas ferramentas. Não faça contas por conta própria.
8. Responda em português do Brasil.

Regras sobre alergias:
9. O sistema registra automaticamente as alergias que o cliente declara (veja "ALERGIAS" abaixo). Você NUNCA deve dizer que o cliente tem uma alergia que não consta ali.
10. Se adicionar_item devolver o erro "alergenico_detectado", o prato NÃO foi adicionado. Explique o risco, cite os alergênicos e pergunte se o cliente quer mesmo o prato. Só chame adicionar_item de novo se o cliente confirmar claramente na mensagem seguinte.
11. Nunca recomende pratos que contenham alergênicos declarados. Para sugerir alternativas, use filtrar_pratos com sem_alergenicos.

ALERGIAS:
{alergias}

CARDÁPIO RELEVANTE:
{contexto}"""

MENSAGEM_FALHA = "Desculpe, não consegui concluir isso agora. Pode reformular ou falar com um atendente?"


def montar_bloco_alergias(sessao: Sessao) -> str:
    """Estado das alergias da sessao, escrito para o modelo ler a cada turno."""
    if sessao.alergias:
        linhas = ["Alergias declaradas pelo cliente: " + ", ".join(sorted(sessao.alergias)) + "."]
    else:
        linhas = ["Nenhuma alergia declarada até agora."]
    for c in itens_em_conflito(sessao.carrinho, sessao.alergias):
        linhas.append(
            f"ATENÇÃO: '{c['item']}' já está no carrinho e contém {', '.join(c['alergenicos'])}. "
            "Avise o cliente."
        )
    if sessao.restricao_nao_reconhecida:
        linhas.append(
            "AVISO: o cliente citou uma restrição que o sistema não reconheceu. "
            "Antes de adicionar pratos, peça que confirme com a equipe do restaurante."
        )
    return "\n".join(linhas)


def conversar(
    pergunta: str,
    sessao: Sessao,
    pratos: list[Prato],
    indice: IndiceVetorial,
    k: int = 4,
    temperature: float = 0.2,
    max_passos: int = 5,
) -> dict:
    """Uma rodada de conversa: RAG + loop de function calling.

    O loop repete 'modelo responde -> executamos as ferramentas que ele pediu ->
    devolvemos o resultado' ate o modelo responder com texto. max_passos evita
    um loop infinito (e uma conta inesperada).
    """
    sessao.perguntas.append(pergunta)
    # Guardrail: a deteccao roda em codigo, ANTES do modelo, sobre a mensagem do cliente.
    sessao.alergias |= detectar_alergias(pergunta)
    if restricao_nao_reconhecida(pergunta):
        sessao.restricao_nao_reconhecida = True
    # Perguntas de acompanhamento ("e o preco dele?") sozinhas buscam mal; usamos as duas ultimas.
    consulta = " ".join(sessao.perguntas[-2:])
    encontrados = buscar(consulta, pratos, indice, k=k)
    system = PROMPT_AGENTE.format(
        contexto=montar_contexto([p for p, _ in encontrados]),
        alergias=montar_bloco_alergias(sessao),
    )

    sessao.historico.append(types.Content(role="user", parts=[types.Part(text=pergunta)]))

    total = {"tokens_entrada": 0, "tokens_saida": 0, "latencia_s": 0.0, "custo_usd": 0.0}
    chamadas = []
    texto = ""

    for _ in range(max_passos):
        resposta, m = chamar_llm_com_ferramentas(
            sessao.historico, system, FERRAMENTAS, temperature=temperature
        )
        total["tokens_entrada"] += m["tokens_entrada"]
        total["tokens_saida"] += m["tokens_saida"]
        total["latencia_s"] = round(total["latencia_s"] + m["latencia_s"], 2)
        total["custo_usd"] += m["custo_usd"]

        if not resposta.candidates or not resposta.candidates[0].content:
            texto = MENSAGEM_FALHA  # resposta vazia ou bloqueada
            break

        # Guardamos a mensagem do modelo INTEIRA (inclui a assinatura de raciocinio).
        sessao.historico.append(resposta.candidates[0].content)

        pedidos = resposta.function_calls or []
        if not pedidos:
            texto = texto_da_resposta(resposta) or MENSAGEM_FALHA
            break

        partes = []
        for pedido in pedidos:
            resultado = executar(pedido.name, dict(pedido.args or {}), sessao, pratos)
            chamadas.append(
                {
                    "nome": pedido.name,
                    "args": dict(pedido.args or {}),
                    "ok": resultado.get("ok"),
                    "erro": resultado.get("erro"),
                }
            )
            partes.append(types.Part.from_function_response(name=pedido.name, response=resultado))
        sessao.historico.append(types.Content(role="user", parts=partes))
    else:
        # Saiu por esgotar os passos: fecha o turno para o historico continuar valido.
        texto = MENSAGEM_FALHA
        sessao.historico.append(types.Content(role="model", parts=[types.Part(text=texto)]))

    return {
        "texto": texto,
        "chamadas": chamadas,
        "pratos_usados": [(p.nome, round(s, 3)) for p, s in encontrados],
        "alergias": sorted(sessao.alergias),
        **total,
    }
