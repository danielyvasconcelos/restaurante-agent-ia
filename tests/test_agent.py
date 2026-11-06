"""Testes do agente. Nao chamam a API: buscar e chamar_llm sao substituidos."""
from app import agent
from app.menu import carregar_cardapio


def _prato(nome):
    return next(p for p in carregar_cardapio() if p.nome == nome)


def test_formatar_preco_usa_virgula_e_duas_casas():
    assert agent.formatar_preco(_prato("Feijoada Completa").preco) == "R$ 49,90"
    assert agent.formatar_preco(_prato("Moqueca de Peixe").preco) == "R$ 62,00"


def test_montar_contexto_traz_ingredientes_preco_e_alergenicos():
    texto = agent.montar_contexto([_prato("Sundae de Paçoca")])
    assert "Sundae de Paçoca" in texto
    assert "R$ 19,90" in texto
    assert "paçoca" in texto
    assert "amendoim" in texto


def test_montar_contexto_indica_nenhum_quando_nao_ha_alergenicos():
    assert "Alergênicos: nenhum" in agent.montar_contexto([_prato("Feijoada Completa")])


def test_prompt_de_sistema_proibe_inventar_e_tem_lugar_para_o_contexto():
    assert "SOMENTE" in agent.PROMPT_SISTEMA
    assert "Nunca invente" in agent.PROMPT_SISTEMA
    assert "{contexto}" in agent.PROMPT_SISTEMA


def test_responder_coloca_os_pratos_recuperados_no_prompt_de_sistema(monkeypatch):
    pratos = carregar_cardapio()
    escolhido = _prato("Pudim de Leite")
    capturado = {}

    monkeypatch.setattr(agent, "buscar", lambda pergunta, p, i, k: [(escolhido, 0.91234)])

    def falso_llm(prompt, system, temperature):
        capturado.update(prompt=prompt, system=system, temperature=temperature)
        return {"texto": "ok", "tokens_entrada": 1, "tokens_saida": 1}

    monkeypatch.setattr(agent, "chamar_llm", falso_llm)

    r = agent.responder("tem sobremesa?", pratos, indice=None)

    assert "Pudim de Leite" in capturado["system"]
    assert "Feijoada" not in capturado["system"]  # so o que foi recuperado entra
    assert capturado["prompt"] == "tem sobremesa?"
    assert capturado["temperature"] <= 0.3
    assert r["pratos_usados"] == [("Pudim de Leite", 0.912)]
