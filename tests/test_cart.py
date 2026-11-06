"""Testes do carrinho e do repositorio de sessoes."""
from decimal import Decimal

import pytest

from app.cart import MAX_POR_ITEM, Carrinho, CarrinhoErro
from app.menu import carregar_cardapio


@pytest.fixture
def pratos():
    return {p.nome: p for p in carregar_cardapio()}


def test_carrinho_novo_esta_vazio_e_total_zero():
    c = Carrinho()
    assert c.esta_vazio()
    assert c.total() == Decimal("0")


def test_adicionar_soma_quantidade_do_mesmo_prato(pratos):
    c = Carrinho()
    c.adicionar(pratos["Feijoada Completa"], 1)
    c.adicionar(pratos["Feijoada Completa"], 2)
    assert len(c.itens()) == 1
    assert c.itens()[0].quantidade == 3


def test_total_usa_decimal_sem_erro_de_arredondamento(pratos):
    c = Carrinho()
    c.adicionar(pratos["Feijoada Completa"], 3)  # 3 x 49,90
    c.adicionar(pratos["Suco de Laranja Natural"], 1)  # 9,90
    assert c.total() == Decimal("159.60")


@pytest.mark.parametrize("quantidade", [0, -1, 1.5, "2", True, None])
def test_quantidade_invalida_e_rejeitada(pratos, quantidade):
    with pytest.raises(CarrinhoErro):
        Carrinho().adicionar(pratos["Feijoada Completa"], quantidade)


def test_limite_por_item_vale_somando_adicoes(pratos):
    c = Carrinho()
    c.adicionar(pratos["Feijoada Completa"], MAX_POR_ITEM)
    with pytest.raises(CarrinhoErro):
        c.adicionar(pratos["Feijoada Completa"], 1)
    assert c.itens()[0].quantidade == MAX_POR_ITEM  # nada mudou apos o erro


def test_remover_parte_e_remover_tudo(pratos):
    c = Carrinho()
    c.adicionar(pratos["Pudim de Leite"], 3)
    assert c.remover(pratos["Pudim de Leite"].id, 1) == 1
    assert c.itens()[0].quantidade == 2
    assert c.remover(pratos["Pudim de Leite"].id) == 2  # None remove tudo
    assert c.esta_vazio()


def test_remover_quantidade_maior_que_a_existente_da_erro(pratos):
    c = Carrinho()
    c.adicionar(pratos["Pudim de Leite"], 2)
    with pytest.raises(CarrinhoErro):
        c.remover(pratos["Pudim de Leite"].id, 5)
    assert c.itens()[0].quantidade == 2


def test_remover_item_que_nao_esta_no_carrinho_da_erro(pratos):
    with pytest.raises(CarrinhoErro):
        Carrinho().remover(pratos["Pudim de Leite"].id)
