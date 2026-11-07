"""Testa a PARTE QUE NÃO USA A API da avaliação: o gabarito e as verificações."""
import json
from pathlib import Path

import pytest

from app.menu import carregar_cardapio
from eval.checks import checar, validar_caso
from eval.run_eval import CASOS, percentil, resumir

CASOS_JSON = json.loads(Path(CASOS).read_text(encoding="utf-8"))
NOMES = {p.nome for p in carregar_cardapio()}


def test_conjunto_tem_cerca_de_vinte_casos_com_ids_unicos():
    ids = [c["id"] for c in CASOS_JSON]
    assert len(ids) == len(set(ids))
    assert 18 <= len(ids) <= 25


@pytest.mark.parametrize("caso", CASOS_JSON, ids=lambda c: c["id"])
def test_cada_caso_esta_bem_escrito(caso):
    assert validar_caso(caso, NOMES) == []


def test_validar_caso_pega_prato_inexistente_e_chave_desconhecida():
    ruim = {"id": "x", "categoria": "c", "turnos": ["oi"],
            "esperado": {"carrinho": {"Pizza": 1}, "contem_tudo": ["a"]}}
    erros = validar_caso(ruim, NOMES)
    assert any("Pizza" in e for e in erros)
    assert any("contem_tudo" in e for e in erros)


def test_validar_caso_rejeita_esperado_vazio():
    assert validar_caso({"id": "x", "categoria": "c", "turnos": ["oi"], "esperado": {}}, NOMES)


def test_checar_ignora_acento_e_maiuscula():
    assert checar({"contem_todos": ["Pão de Queijo"]}, "Temos PAO DE QUEIJO!", [], {}, []) == []


def test_checar_falha_quando_falta_ou_sobra_texto():
    assert checar({"contem_todos": ["pudim"]}, "so brigadeiro", [], {}, [])
    assert checar({"nao_contem": ["paris"]}, "A capital é Paris", [], {}, [])
    assert checar({"contem_algum": ["a", "b"]}, "xyz", [], {}, [])


def test_nao_regex_distingue_negacao():
    padrao = {"nao_regex": ["(?<!nao )\\b(contem|leva|tem) gluten"]}
    assert checar(padrao, "Não contém glúten.", [], {}, []) == []
    assert checar(padrao, "Sim, contém glúten.", [], {}, [])


def test_ferramenta_ok_exige_sucesso_e_nao_ok_proibe_sucesso():
    falha = [{"nome": "adicionar_item", "ok": False}]
    sucesso = [{"nome": "adicionar_item", "ok": True}]
    assert checar({"ferramenta_ok": ["adicionar_item"]}, "", falha, {}, [])
    assert checar({"ferramenta_ok": ["adicionar_item"]}, "", sucesso, {}, []) == []
    assert checar({"ferramenta_nao_ok": ["adicionar_item"]}, "", sucesso, {}, [])
    assert checar({"ferramenta_nao_ok": ["adicionar_item"]}, "", falha, {}, []) == []


def test_carrinho_vazio_esperado_nao_aceita_item():
    assert checar({"carrinho": {}}, "", [], {}, []) == []
    assert checar({"carrinho": {}}, "", [], {"Pudim de Leite": 1}, [])


def test_alergias_comparadas_sem_importar_a_ordem():
    assert checar({"alergias": ["soja", "lactose"]}, "", [], {}, ["lactose", "soja"]) == []
    assert checar({"alergias": ["lactose"]}, "", [], {}, [])


def test_percentil_e_resumo():
    assert percentil([], 95) == 0.0
    assert percentil([1, 2, 3, 4, 5], 50) == 3.0
    turno = {"tokens_entrada": 100, "tokens_saida": 10, "latencia_s": 2.0, "custo_usd": 0.001, "chamadas_llm": 1}
    res = [
        {"aprovado": True, "categoria": "a", "turnos": [turno]},
        {"aprovado": False, "categoria": "a", "turnos": [turno, turno]},
    ]
    r = resumir(res)
    assert r["aprovados"] == 1 and r["casos"] == 2 and r["taxa_acerto"] == 0.5
    assert r["por_categoria"]["a"] == {"aprovados": 1, "total": 2}
    assert r["turnos"] == 3
    assert r["custo_total_usd"] == 0.003
    assert r["custo_medio_por_caso_usd"] == 0.0015


@pytest.mark.parametrize("resposta,deve_passar", [
    ("Não, a Moqueca de Peixe não contém glúten.", True),
    ("A moqueca de peixe não leva glúten.", True),
    ("Ela é livre de glúten, não se preocupe.", True),
    ("Sim, contém glúten.", False),
    ("Ela leva glúten na farofa.", False),
])
def test_gabarito_da_pergunta_sobre_gluten_aceita_respostas_certas(resposta, deve_passar):
    caso = next(c for c in CASOS_JSON if c["id"] == "alerg-03")
    padroes = {"nao_regex": caso["esperado"]["nao_regex"]}
    assert (checar(padroes, resposta, [], {}, []) == []) is deve_passar
