"""Testes das ferramentas e da busca de pratos por nome."""
import pytest

from app import tools
from app.cart import Carrinho
from app.menu import buscar_por_nome, carregar_cardapio


@pytest.fixture
def pratos():
    return carregar_cardapio()


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("feijoada", ["Feijoada Completa"]),
        ("FEIJOADA COMPLETA", ["Feijoada Completa"]),
        ("pao de queijo", ["Pão de Queijo (porção)"]),  # sem acento
        ("frango parmegiana", ["Frango à Parmegiana"]),
        ("moqueca de peixe", ["Moqueca de Peixe"]),
        ("pizza", []),
        ("", []),
    ],
)
def test_buscar_por_nome(pratos, texto, esperado):
    assert [p.nome for p in buscar_por_nome(texto, pratos)] == esperado


def test_nome_ambiguo_devolve_varios(pratos):
    assert len(buscar_por_nome("moqueca", pratos)) == 2


def test_adicionar_item_ok_devolve_estado_do_carrinho(pratos):
    c = Carrinho()
    r = tools.adicionar_item(c, pratos, "feijoada", 2)
    assert r["ok"] is True
    assert r["carrinho"]["total"] == "R$ 99,80"
    assert r["carrinho"]["total_unidades"] == 2


def test_adicionar_aceita_quantidade_float_inteira(pratos):
    r = tools.adicionar_item(Carrinho(), pratos, "feijoada", 2.0)
    assert r["ok"] is True


def test_prato_inexistente_vira_erro_como_dado(pratos):
    r = tools.adicionar_item(Carrinho(), pratos, "pizza", 1)
    assert r["ok"] is False
    assert r["erro"] == "prato_nao_encontrado"


def test_prato_ambiguo_lista_as_opcoes(pratos):
    c = Carrinho()
    r = tools.adicionar_item(c, pratos, "moqueca", 1)
    assert r["ok"] is False
    assert r["erro"] == "prato_ambiguo"
    assert set(r["opcoes"]) == {"Moqueca de Peixe", "Moqueca de Camarão"}
    assert c.esta_vazio()  # nada foi adicionado


def test_quantidade_invalida_nao_levanta_excecao(pratos):
    r = tools.adicionar_item(Carrinho(), pratos, "feijoada", 0)
    assert r["ok"] is False
    assert r["erro"] == "carrinho_invalido"


def test_remover_item(pratos):
    c = Carrinho()
    tools.adicionar_item(c, pratos, "pudim", 3)
    r = tools.remover_item(c, pratos, "pudim", 1)
    assert r["ok"] is True
    assert r["carrinho"]["total_unidades"] == 2


def test_remover_item_que_nao_esta_no_carrinho(pratos):
    r = tools.remover_item(Carrinho(), pratos, "pudim")
    assert r["ok"] is False


def test_ver_carrinho_vazio_e_cheio(pratos):
    c = Carrinho()
    assert tools.ver_carrinho(c)["mensagem"] == "O carrinho está vazio."
    tools.adicionar_item(c, pratos, "suco", 1)
    r = tools.ver_carrinho(c)
    assert r["carrinho"]["itens"][0]["nome"] == "Suco de Laranja Natural"
    assert r["carrinho"]["total"] == "R$ 9,90"
