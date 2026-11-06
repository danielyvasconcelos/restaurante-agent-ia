"""Ferramentas do agente: adicionar_item, remover_item, ver_carrinho.

Cada ferramenta devolve um dicionario com "ok" True/False. Erros voltam como DADOS,
nao como excecao, para o modelo ler o motivo e se corrigir (ex.: perguntar qual prato).
"""
from app.cart import Carrinho, CarrinhoErro
from app.menu import buscar_por_nome, formatar_preco
from app.schemas import Prato


def _estado(carrinho: Carrinho) -> dict:
    return {
        "itens": [
            {
                "nome": i.prato.nome,
                "quantidade": i.quantidade,
                "preco_unitario": formatar_preco(i.prato.preco),
                "subtotal": formatar_preco(i.subtotal),
            }
            for i in carrinho.itens()
        ],
        "total_unidades": sum(i.quantidade for i in carrinho.itens()),
        "total": formatar_preco(carrinho.total()),
    }


def _erro(codigo: str, mensagem: str, **extra) -> dict:
    return {"ok": False, "erro": codigo, "mensagem": mensagem, **extra}


def _resolver_prato(nome_prato: str, pratos: list[Prato]) -> tuple[Prato | None, dict | None]:
    """Devolve (prato, None) se achou um so, ou (None, erro) se nao achou/ambiguo."""
    achados = buscar_por_nome(nome_prato, pratos)
    if not achados:
        return None, _erro("prato_nao_encontrado", f"Não encontrei '{nome_prato}' no cardápio.")
    if len(achados) > 1:
        return None, _erro(
            "prato_ambiguo",
            f"'{nome_prato}' pode ser mais de um prato. Pergunte qual o cliente quer.",
            opcoes=[p.nome for p in achados],
        )
    return achados[0], None


def _como_inteiro(valor):
    """O modelo pode mandar 2.0 em vez de 2; aceitamos so se for inteiro de fato."""
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return valor


def adicionar_item(
    carrinho: Carrinho, pratos: list[Prato], nome_prato: str, quantidade: int = 1
) -> dict:
    prato, erro = _resolver_prato(nome_prato, pratos)
    if erro:
        return erro
    try:
        item = carrinho.adicionar(prato, _como_inteiro(quantidade))
    except CarrinhoErro as e:
        return _erro("carrinho_invalido", str(e))
    return {
        "ok": True,
        "mensagem": f"{item.quantidade}x {prato.nome} no carrinho.",
        "carrinho": _estado(carrinho),
    }


def remover_item(
    carrinho: Carrinho, pratos: list[Prato], nome_prato: str, quantidade: int | None = None
) -> dict:
    prato, erro = _resolver_prato(nome_prato, pratos)
    if erro:
        return erro
    try:
        removidas = carrinho.remover(prato.id, _como_inteiro(quantidade))
    except CarrinhoErro as e:
        return _erro("carrinho_invalido", str(e))
    return {
        "ok": True,
        "mensagem": f"Removi {removidas}x {prato.nome}.",
        "carrinho": _estado(carrinho),
    }


def ver_carrinho(carrinho: Carrinho) -> dict:
    if carrinho.esta_vazio():
        return {"ok": True, "mensagem": "O carrinho está vazio.", "carrinho": _estado(carrinho)}
    return {"ok": True, "carrinho": _estado(carrinho)}
