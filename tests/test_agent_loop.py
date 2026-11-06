"""Testes do loop do agente. O Gemini e substituido por respostas falsas e roteirizadas."""
from google.genai import types

from app import agent
from app.menu import carregar_cardapio
from app.session import Sessao

METRICAS = {
    "tokens_entrada": 10, "tokens_saida": 5, "tokens_pensamento": 0,
    "latencia_s": 0.1, "custo_usd": 0.0001, "modelo": "falso",
}


def _resp(*partes):
    content = types.Content(role="model", parts=list(partes))
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def _chamada(nome, args):
    return _resp(types.Part(function_call=types.FunctionCall(name=nome, args=args)))


def _texto(t):
    return _resp(types.Part(text=t))


def _instalar_roteiro(monkeypatch, respostas):
    """Faz o agente receber as respostas do roteiro, uma por chamada ao 'LLM'."""
    fila = iter(respostas)
    chamadas_ao_llm = []

    def falso(contents, system, ferramentas, temperature=0.2, max_output_tokens=1024):
        chamadas_ao_llm.append(system)
        return next(fila), dict(METRICAS)

    monkeypatch.setattr(agent, "chamar_llm_com_ferramentas", falso)
    monkeypatch.setattr(agent, "buscar", lambda consulta, p, i, k: [(p[0], 0.9)])
    return chamadas_ao_llm


def test_modelo_pede_ferramenta_executamos_e_ele_responde(monkeypatch):
    pratos = carregar_cardapio()
    sessao = Sessao()
    _instalar_roteiro(monkeypatch, [
        _chamada("adicionar_item", {"nome_prato": "feijoada", "quantidade": 2}),
        _texto("Pronto! 2 feijoadas no carrinho."),
    ])

    r = agent.conversar("quero 2 feijoadas", sessao, pratos, indice=None)

    assert r["texto"] == "Pronto! 2 feijoadas no carrinho."
    assert sessao.carrinho.itens()[0].quantidade == 2  # a ferramenta rodou de verdade
    assert r["chamadas"] == [
        {"nome": "adicionar_item", "args": {"nome_prato": "feijoada", "quantidade": 2},
         "ok": True, "erro": None}
    ]
    assert [m.role for m in sessao.historico] == ["user", "model", "user", "model"]
    assert r["tokens_entrada"] == 20  # duas chamadas ao modelo somadas


def test_erro_da_ferramenta_volta_ao_modelo_como_dado(monkeypatch):
    pratos = carregar_cardapio()
    sessao = Sessao()
    _instalar_roteiro(monkeypatch, [
        _chamada("adicionar_item", {"nome_prato": "moqueca"}),
        _texto("Qual moqueca você prefere, de peixe ou de camarão?"),
    ])

    r = agent.conversar("quero uma moqueca", sessao, pratos, indice=None)

    assert sessao.carrinho.esta_vazio()  # ambiguo: nada foi adicionado
    assert r["chamadas"][0]["ok"] is False
    resposta_da_ferramenta = sessao.historico[2].parts[0].function_response.response
    assert resposta_da_ferramenta["erro"] == "prato_ambiguo"


def test_pergunta_simples_nao_chama_ferramenta(monkeypatch):
    sessao = Sessao()
    _instalar_roteiro(monkeypatch, [_texto("Temos feijoada!")])
    r = agent.conversar("o que vocês têm?", sessao, carregar_cardapio(), indice=None)
    assert r["chamadas"] == []
    assert len(sessao.historico) == 2


def test_loop_para_no_limite_de_passos(monkeypatch):
    sessao = Sessao()
    _instalar_roteiro(monkeypatch, [_chamada("ver_carrinho", {}) for _ in range(10)])
    r = agent.conversar("oi", sessao, carregar_cardapio(), indice=None, max_passos=3)
    assert r["texto"] == agent.MENSAGEM_FALHA
    assert len(r["chamadas"]) == 3
    assert sessao.historico[-1].role == "model"  # historico fechado corretamente


def test_resposta_vazia_do_modelo_vira_mensagem_de_falha(monkeypatch):
    sessao = Sessao()
    _instalar_roteiro(monkeypatch, [types.GenerateContentResponse(candidates=[])])
    r = agent.conversar("oi", sessao, carregar_cardapio(), indice=None)
    assert r["texto"] == agent.MENSAGEM_FALHA


def test_busca_usa_as_duas_ultimas_perguntas(monkeypatch):
    pratos = carregar_cardapio()
    sessao = Sessao()
    consultas = []
    _instalar_roteiro(monkeypatch, [_texto("a"), _texto("b")])
    monkeypatch.setattr(
        agent, "buscar", lambda consulta, p, i, k: consultas.append(consulta) or [(p[0], 0.9)]
    )
    agent.conversar("fale da feijoada", sessao, pratos, indice=None)
    agent.conversar("e o preço dela?", sessao, pratos, indice=None)
    assert consultas == ["fale da feijoada", "fale da feijoada e o preço dela?"]


def test_prompt_do_agente_manda_usar_ferramentas_e_nao_fazer_contas():
    p = agent.PROMPT_AGENTE
    assert "filtrar_pratos" in p
    assert "SEMPRE use as ferramentas" in p
    assert "Não faça contas" in p
    assert "{contexto}" in p
