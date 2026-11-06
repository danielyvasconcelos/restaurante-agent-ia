"""Carrinho de pedidos. Logica pura: nao depende de LLM nem de API."""
from dataclasses import dataclass
from decimal import Decimal

from app.schemas import Prato

MAX_POR_ITEM = 20  # limite de seguranca contra quantidades absurdas


class CarrinhoErro(ValueError):
    """Erro de regra de negocio do carrinho (mensagem pensada para o usuario)."""


@dataclass(frozen=True)
class ItemCarrinho:
    prato: Prato
    quantidade: int

    @property
    def subtotal(self) -> Decimal:
        return self.prato.preco * self.quantidade


class Carrinho:
    def __init__(self) -> None:
        self._itens: dict[int, ItemCarrinho] = {}  # chave: id do prato

    def adicionar(self, prato: Prato, quantidade: int = 1) -> ItemCarrinho:
        _validar_quantidade(quantidade)
        atual = self._itens[prato.id].quantidade if prato.id in self._itens else 0
        nova = atual + quantidade
        if nova > MAX_POR_ITEM:
            raise CarrinhoErro(
                f"O limite é {MAX_POR_ITEM} unidades por item "
                f"(já há {atual} de '{prato.nome}' no carrinho)."
            )
        self._itens[prato.id] = ItemCarrinho(prato, nova)
        return self._itens[prato.id]

    def remover(self, prato_id: int, quantidade: int | None = None) -> int:
        """Remove unidades de um item. quantidade=None remove o item todo.

        Devolve quantas unidades foram removidas.
        """
        if prato_id not in self._itens:
            raise CarrinhoErro("Esse item não está no carrinho.")
        item = self._itens[prato_id]
        if quantidade is None:
            del self._itens[prato_id]
            return item.quantidade
        _validar_quantidade(quantidade)
        if quantidade > item.quantidade:
            raise CarrinhoErro(
                f"Há apenas {item.quantidade} de '{item.prato.nome}' no carrinho."
            )
        if quantidade == item.quantidade:
            del self._itens[prato_id]
        else:
            self._itens[prato_id] = ItemCarrinho(item.prato, item.quantidade - quantidade)
        return quantidade

    def itens(self) -> list[ItemCarrinho]:
        return list(self._itens.values())

    def total(self) -> Decimal:
        return sum((i.subtotal for i in self._itens.values()), Decimal("0"))

    def esta_vazio(self) -> bool:
        return not self._itens

    def limpar(self) -> None:
        self._itens.clear()


def _validar_quantidade(quantidade) -> None:
    # bool e subclasse de int em Python; True nao e uma quantidade valida.
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise CarrinhoErro("A quantidade precisa ser um número inteiro.")
    if quantidade < 1:
        raise CarrinhoErro("A quantidade precisa ser pelo menos 1.")
    if quantidade > MAX_POR_ITEM:
        raise CarrinhoErro(f"O limite é {MAX_POR_ITEM} unidades por item.")
