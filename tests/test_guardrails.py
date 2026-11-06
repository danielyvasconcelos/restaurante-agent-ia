"""Testes do guardrail de alergenicos. Nenhum chama a API."""
import pytest
from google.genai import types

from app import agent, guardrails, tools
from app.menu import carregar_cardapio
from app.schemas import Alergenico
from app.session import Sessao


@pytest.fixture
def pratos():
    return carregar_cardapio()


def _prato(pratos, nome):
    return next(p for p in pratos if p.nome == nome)


# --- deteccao de alergias ---------------------------------------------------------
@pytest.mark.parametrize(
    "mensagem, esperado",
    [
        ("tenho alergia a lactose", {"lactose"}),
        ("Sou alérgica a camarão", {"crustaceos"}),
        ("sou celíaca", {"gluten"}),
        ("tenho alergia a amendoim e castanha", {"amendoim", "castanhas"}),
        ("alergia a frutos do mar", {"crustaceos", "peixe"}),  # na duvida, os dois
        ("sou intolerante a lactose", {"lactose"}),
        ("não posso comer ovo", {"ovo"}),
        ("minha filha tem alergia a leite", {"lactose"}),
        ("Tenho alergia a lactose. Quero uma feijoada com ovo", {"lactose"}),  # ovo e outra frase
    ],
)
def test_detecta_alergias_declaradas(mensagem, esperado):
    assert guardrails.detectar_alergias(mensagem) == esperado


@pytest.mark.parametrize(
    "mensagem",
    [
        "quero uma feijoada",
        "quais pratos têm lactose?",  # pergunta, nao declaracao
        "não tenho alergia a lactose",
        "não sou alérgico a nada",
        "quero algo sem glúten",  # preferencia, nao alergia declarada
    ],
)
def test_nao_registra_alergia_quando_nao_ha_declaracao(mensagem):
    assert guardrails.detectar_alergias(mensagem) == set()


def test_negacao_anula_so_o_trecho_negado():
    msg = "não tenho alergia a lactose, mas sou alérgica a ovo"
    assert guardrails.detectar_alergias(msg) == {"ovo"}


def test_todo_alergenico_do_cardapio_e_detectavel():
    """Se alguem criar um alergenico novo no Enum e esquecer o lexico, este teste falha."""
    for a in Alergenico:
        assert guardrails.detectar_alergias(f"tenho alergia a {a.value}") == {a.value}, a.value


def test_restricao_desconhecida_e_sinalizada():
    assert guardrails.restricao_nao_reconhecida("tenho alergia a pimenta") is True
    assert guardrails.restricao_nao_reconhecida("tenho alergia a lactose") is False
    assert guardrails.restricao_nao_reconhecida("quero feijoada") is False


# --- confirmacao ------------------------------------------------------------------
@pytest.mark.parametrize(
    "msg", ["sim", "Sim, pode adicionar", "confirmo", "quero sim, mesmo assim", "pode", "ok!"]
)
def test_confirmacoes_claras(msg):
    assert guardrails.eh_confirmacao(msg) is True


@pytest.mark.parametrize(
    "msg",
    ["não", "não, deixa", "cancela", "sim, mas sem o pudim", "e o preço?", "qual o total?", "talvez"],
)
def test_na_duvida_nao_confirma(msg):
    assert guardrails.eh_confirmacao(msg) is False


# --- avaliar_adicao: o fluxo de alerta e confirmacao ------------------------------
def test_prato_sem_conflito_passa_direto(pratos):
    s = Sessao(alergias={"lactose"})
    assert guardrails.avaliar_adicao(s, _prato(pratos, "Feijoada Completa")) is None


def test_prato_com_conflito_e_vetado_com_instrucao_para_o_modelo(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("quero um pudim")
    veto = guardrails.avaliar_adicao(s, _prato(pratos, "Pudim de Leite"))
    assert veto["ok"] is False
    assert veto["erro"] == "alergenico_detectado"
    assert veto["alergenicos"] == ["lactose"]
    assert veto["requer_confirmacao_do_cliente"] is True


def test_modelo_nao_se_autoconfirma_dentro_do_mesmo_turno(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("tenho alergia a lactose, quero pudim")
    pudim = _prato(pratos, "Pudim de Leite")
    assert guardrails.avaliar_adicao(s, pudim) is not None
    assert guardrails.avaliar_adicao(s, pudim) is not None  # insistir nao adianta


def test_cliente_confirma_na_mensagem_seguinte(pratos):
    s = Sessao(alergias={"lactose"})
    pudim = _prato(pratos, "Pudim de Leite")
    s.perguntas.append("quero pudim")
    assert guardrails.avaliar_adicao(s, pudim) is not None
    s.perguntas.append("sim, pode adicionar")
    assert guardrails.avaliar_adicao(s, pudim) is None
    assert pudim.id not in s.pendencias  # a confirmacao e de uso unico


def test_cliente_recusa_e_o_modelo_insiste(pratos):
    s = Sessao(alergias={"lactose"})
    pudim = _prato(pratos, "Pudim de Leite")
    s.perguntas.append("quero pudim")
    guardrails.avaliar_adicao(s, pudim)
    s.perguntas.append("não, deixa")
    assert guardrails.avaliar_adicao(s, pudim) is not None


def test_confirmacao_antiga_expira(pratos):
    s = Sessao(alergias={"lactose"})
    pudim = _prato(pratos, "Pudim de Leite")
    s.perguntas.append("quero pudim")
    guardrails.avaliar_adicao(s, pudim)
    s.perguntas.append("qual o preço da feijoada?")  # a conversa seguiu outro rumo
    s.perguntas.append("sim")
    assert guardrails.avaliar_adicao(s, pudim) is not None


def test_confirmar_um_prato_nao_libera_outro(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("quero pudim")
    guardrails.avaliar_adicao(s, _prato(pratos, "Pudim de Leite"))
    s.perguntas.append("sim")
    assert guardrails.avaliar_adicao(s, _prato(pratos, "Brigadeiro Gourmet")) is not None


# --- integracao com as ferramentas ------------------------------------------------
def test_executar_bloqueia_e_nao_adiciona(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("quero pudim")
    r = tools.executar("adicionar_item", {"nome_prato": "pudim"}, s, pratos)
    assert r["erro"] == "alergenico_detectado"
    assert s.carrinho.esta_vazio()


def test_executar_adiciona_depois_da_confirmacao(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("quero pudim")
    tools.executar("adicionar_item", {"nome_prato": "pudim"}, s, pratos)
    s.perguntas.append("sim, confirmo")
    r = tools.executar("adicionar_item", {"nome_prato": "pudim"}, s, pratos)
    assert r["ok"] is True
    assert len(s.carrinho.itens()) == 1


def test_modelo_nao_consegue_desligar_o_guardrail_por_argumento(pratos):
    s = Sessao(alergias={"lactose"})
    s.perguntas.append("quero pudim")
    r = tools.executar("adicionar_item", {"nome_prato": "pudim", "avaliar": None}, s, pratos)
    assert r["ok"] is False
    assert r["erro"] == "argumentos_invalidos"
    assert s.carrinho.esta_vazio()


def test_ver_carrinho_avisa_sobre_itens_em_conflito(pratos):
    s = Sessao()
    tools.executar("adicionar_item", {"nome_prato": "pudim"}, s, pratos)  # ainda sem alergia
    s.alergias.add("ovo")  # a alergia e declarada depois
    r = tools.executar("ver_carrinho", {}, s, pratos)
    assert r["avisos_alergia"] == [{"item": "Pudim de Leite", "alergenicos": ["ovo"]}]


def test_filtro_marca_pratos_que_conflitam_com_a_alergia(pratos):
    s = Sessao(alergias={"amendoim"})
    r = tools.executar("filtrar_pratos", {"categoria": "sobremesa"}, s, pratos)
    marcas = {p["nome"]: p["contem_alergenico_declarado"] for p in r["pratos"]}
    assert marcas["Sundae de Paçoca"] == ["amendoim"]
    assert marcas["Pudim de Leite"] == []


# --- integracao com o loop do agente ----------------------------------------------
METRICAS = {
    "tokens_entrada": 10, "tokens_saida": 5, "tokens_pensamento": 0,
    "latencia_s": 0.1, "custo_usd": 0.0001, "modelo": "falso",
}


def _resp(*partes):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(partes)))]
    )


def _chamada(nome, args):
    return _resp(types.Part(function_call=types.FunctionCall(name=nome, args=args)))


def _texto(t):
    return _resp(types.Part(text=t))


def _roteiro(monkeypatch, respostas):
    fila = iter(respostas)
    systems = []

    def falso(contents, system, ferramentas, temperature=0.2, max_output_tokens=1024):
        systems.append(system)
        return next(fila), dict(METRICAS)

    monkeypatch.setattr(agent, "chamar_llm_com_ferramentas", falso)
    monkeypatch.setattr(agent, "buscar", lambda consulta, p, i, k: [(p[0], 0.9)])
    return systems


def test_agente_registra_alergia_antes_do_modelo_e_bloqueia(monkeypatch, pratos):
    s = Sessao()
    systems = _roteiro(monkeypatch, [
        _chamada("adicionar_item", {"nome_prato": "pudim"}),
        _texto("Esse prato contém lactose. Quer mesmo?"),
    ])
    r = agent.conversar("Tenho alergia a lactose, quero um pudim", s, pratos, indice=None)

    assert s.alergias == {"lactose"}
    assert s.carrinho.esta_vazio()
    assert r["chamadas"][0]["erro"] == "alergenico_detectado"
    assert r["alergias"] == ["lactose"]
    assert "Alergias declaradas pelo cliente: lactose" in systems[0]  # o modelo foi informado


def test_agente_fluxo_completo_alerta_confirmacao_e_adicao(monkeypatch, pratos):
    s = Sessao()
    _roteiro(monkeypatch, [
        _chamada("adicionar_item", {"nome_prato": "pudim"}), _texto("Contém lactose. Confirma?"),
        _chamada("adicionar_item", {"nome_prato": "pudim"}), _texto("Adicionado!"),
    ])
    agent.conversar("Tenho alergia a lactose, quero um pudim", s, pratos, indice=None)
    assert s.carrinho.esta_vazio()
    agent.conversar("sim, pode adicionar", s, pratos, indice=None)
    assert s.carrinho.itens()[0].prato.nome == "Pudim de Leite"


def test_agente_modelo_insiste_apos_recusa_do_cliente(monkeypatch, pratos):
    s = Sessao()
    _roteiro(monkeypatch, [
        _chamada("adicionar_item", {"nome_prato": "pudim"}), _texto("Confirma?"),
        _chamada("adicionar_item", {"nome_prato": "pudim"}), _texto("Ok, não adicionei."),
    ])
    agent.conversar("Tenho alergia a lactose, quero um pudim", s, pratos, indice=None)
    agent.conversar("não, deixa pra lá", s, pratos, indice=None)
    assert s.carrinho.esta_vazio()


def test_bloco_de_alergias_avisa_sobre_item_ja_no_carrinho(pratos):
    s = Sessao()
    tools.executar("adicionar_item", {"nome_prato": "pudim"}, s, pratos)
    s.alergias.add("lactose")
    bloco = agent.montar_bloco_alergias(s)
    assert "Pudim de Leite" in bloco and "já está no carrinho" in bloco


def test_bloco_de_alergias_sinaliza_restricao_desconhecida():
    s = Sessao(restricao_nao_reconhecida=True)
    assert "não reconheceu" in agent.montar_bloco_alergias(s)


def test_prompt_proibe_inventar_alergia_e_manda_respeitar_o_erro():
    p = agent.PROMPT_AGENTE
    assert "NUNCA deve dizer que o cliente tem uma alergia" in p
    assert "alergenico_detectado" in p
    assert "{alergias}" in p
