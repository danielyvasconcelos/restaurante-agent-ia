"""Testes do cardapio. Rode da raiz do projeto: pytest"""
import pytest
from pydantic import ValidationError

from app.menu import carregar_cardapio
from app.schemas import Prato

# Palavra-chave num ingrediente -> alergenico que o prato PRECISA declarar.
# Rede de seguranca: um erro no JSON aqui seria informar alergenico errado ao cliente.
PALAVRA_PARA_ALERGENICO = {
    "leite": "lactose",
    "queijo": "lactose",
    "manteiga": "lactose",
    "requeijão": "lactose",
    "ovo": "ovo",
    "farinha de trigo": "gluten",
    "farinha de rosca": "gluten",
    "pão": "gluten",
    "camarão": "crustaceos",
    "peixe": "peixe",
    "anchova": "peixe",
    "paçoca": "amendoim",
    "castanha": "castanhas",
    "tahine": "gergelim",
    "soja": "soja",
}


def _prato_valido(**mudancas) -> dict:
    base = {
        "id": 1,
        "nome": "Prato de Teste",
        "categoria": "entrada",
        "descricao": "Descricao de teste com tamanho suficiente.",
        "preco": 10.0,
        "ingredientes": ["agua"],
        "alergenicos": [],
    }
    return {**base, **mudancas}


def test_cardapio_carrega_e_tem_entre_10_e_15_pratos():
    pratos = carregar_cardapio()
    assert 10 <= len(pratos) <= 15


def test_ids_sao_unicos():
    ids = [p.id for p in carregar_cardapio()]
    assert len(ids) == len(set(ids))


def test_alergenicos_batem_com_os_ingredientes():
    for prato in carregar_cardapio():
        declarados = {a.value for a in prato.alergenicos}
        for ingrediente in prato.ingredientes:
            if "de coco" in ingrediente:  # leite de coco nao e lactose
                continue
            for palavra, alergenico in PALAVRA_PARA_ALERGENICO.items():
                if palavra in ingrediente:
                    assert alergenico in declarados, (
                        f"{prato.nome}: '{ingrediente}' exige '{alergenico}'"
                    )


@pytest.mark.parametrize(
    "mudanca",
    [
        {"preco": -5},
        {"preco": 0},
        {"nome": ""},
        {"ingredientes": []},
        {"alergenicos": ["pimenta"]},
        {"categoria": "lanche"},
        {"campo_inventado": "x"},
    ],
)
def test_prato_invalido_e_rejeitado(mudanca):
    with pytest.raises(ValidationError):
        Prato.model_validate(_prato_valido(**mudanca))
