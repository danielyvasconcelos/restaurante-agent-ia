"""Testes do filtro por alergenicos e do despachante de ferramentas."""
import pytest

from app import tools
from app.cart import Carrinho
from app.menu import carregar_cardapio


@pytest.fixture
def pratos():
    return carregar_cardapio()


def _nomes(resultado):
    return {p["nome"] for p in resultado["pratos"]}


def test_sem_lactose_acha_os_cinco_pratos_do_cardapio_inteiro(pratos):
    r = tools.filtrar_pratos(pratos, sem_alergenicos=["lactose"])
    assert _nomes(r) == {
        "Feijoada Completa",
        "Moqueca de Peixe",
        "Moqueca de Camarão",
        "Bowl Vegano de Grão-de-bico",
        "Suco de Laranja Natural",
    }
    assert r["quantidade"] == 5


def test_varios_alergenicos_e_categoria(pratos):
    r = tools.filtrar_pratos(pratos, sem_alergenicos=["lactose", "ovo"], categoria="sobremesa")
    assert r["pratos"] == []  # todas as sobremesas tem lactose


def test_aceita_sinonimos_e_acentos(pratos):
    com_sinonimo = tools.filtrar_pratos(pratos, sem_alergenicos=["glúten", "camarão"])
    sem = tools.filtrar_pratos(pratos, sem_alergenicos=["gluten", "crustaceos"])
    assert _nomes(com_sinonimo) == _nomes(sem)
    assert "Moqueca de Camarão" not in _nomes(com_sinonimo)


def test_alergenico_desconhecido_nunca_e_ignorado(pratos):
    r = tools.filtrar_pratos(pratos, sem_alergenicos=["pimenta"])
    assert r["ok"] is False
    assert r["erro"] == "alergenico_invalido"
    assert "lactose" in r["validos"]


def test_categoria_invalida(pratos):
    assert tools.filtrar_pratos(pratos, categoria="lanche")["erro"] == "categoria_invalida"


def test_preco_maximo(pratos):
    r = tools.filtrar_pratos(pratos, preco_maximo=20)
    assert r["ok"] is True
    assert _nomes(r) == {
        "Pão de Queijo (porção)",
        "Brigadeiro Gourmet",
        "Pudim de Leite",
        "Sundae de Paçoca",
        "Suco de Laranja Natural",
    }


def test_executar_despacha_para_a_ferramenta_certa(pratos):
    c = Carrinho()
    r = tools.executar("adicionar_item", {"nome_prato": "feijoada", "quantidade": 2}, c, pratos)
    assert r["ok"] is True
    assert c.total() == 2 * pratos[0].preco


def test_executar_ferramenta_desconhecida_vira_erro(pratos):
    r = tools.executar("apagar_tudo", {}, Carrinho(), pratos)
    assert r["erro"] == "ferramenta_desconhecida"


def test_executar_argumentos_errados_vira_erro_sem_quebrar(pratos):
    r = tools.executar("adicionar_item", {"prato": "feijoada"}, Carrinho(), pratos)
    assert r["ok"] is False
    assert r["erro"] == "argumentos_invalidos"


def test_declaracoes_batem_com_as_ferramentas_executaveis(pratos):
    for decl in tools.DECLARACOES:
        r = tools.executar(decl.name, {}, Carrinho(), pratos)
        assert r.get("erro") != "ferramenta_desconhecida", decl.name
