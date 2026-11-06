"""Sessao de conversa: tudo o que o servidor precisa lembrar de um cliente."""
from dataclasses import dataclass, field

from app.cart import Carrinho


@dataclass
class Sessao:
    carrinho: Carrinho = field(default_factory=Carrinho)
    historico: list = field(default_factory=list)  # mensagens (types.Content) trocadas
    perguntas: list[str] = field(default_factory=list)  # so o texto das perguntas do cliente


class RepositorioSessoes:
    """Uma sessao por session_id, em memoria. Reiniciar o servidor apaga tudo."""

    def __init__(self) -> None:
        self._sessoes: dict[str, Sessao] = {}

    def obter(self, session_id: str) -> Sessao:
        if session_id not in self._sessoes:
            self._sessoes[session_id] = Sessao()
        return self._sessoes[session_id]
