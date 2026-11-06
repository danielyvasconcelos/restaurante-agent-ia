"""Sessao de conversa: tudo o que o servidor precisa lembrar de um cliente."""
import copy
import threading
from dataclasses import dataclass, field

from app import config
from app.cart import Carrinho


class SessoesEsgotadas(RuntimeError):
    """O servidor atingiu o numero maximo de sessoes simultaneas."""


@dataclass
class Sessao:
    carrinho: Carrinho = field(default_factory=Carrinho)
    historico: list = field(default_factory=list)  # mensagens (types.Content) trocadas
    perguntas: list[str] = field(default_factory=list)  # so o texto das mensagens do cliente
    # Guardrail de alergenicos:
    alergias: set[str] = field(default_factory=set)  # alergenicos declarados pelo cliente
    pendencias: dict[int, int] = field(default_factory=dict)  # id do prato -> turno do alerta
    restricao_nao_reconhecida: bool = False  # cliente citou restricao que nao sabemos mapear
    # Duas requisicoes da mesma sessao nao podem rodar ao mesmo tempo.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def checkpoint(self) -> tuple:
        """Foto do estado antes de um turno, para desfazer se o turno falhar."""
        return (
            copy.deepcopy(self.carrinho),
            set(self.alergias),
            dict(self.pendencias),
            self.restricao_nao_reconhecida,
            len(self.historico),
            len(self.perguntas),
        )

    def restaurar(self, foto: tuple) -> None:
        """Volta ao estado da foto. O turno que falhou nao deixa rastro."""
        carrinho, alergias, pendencias, restricao, n_historico, n_perguntas = foto
        self.carrinho = carrinho
        self.alergias = alergias
        self.pendencias = pendencias
        self.restricao_nao_reconhecida = restricao
        del self.historico[n_historico:]
        del self.perguntas[n_perguntas:]


class RepositorioSessoes:
    """Uma sessao por session_id, em memoria. Reiniciar o servidor apaga tudo."""

    def __init__(self, max_sessoes: int = config.MAX_SESSOES) -> None:
        self._sessoes: dict[str, Sessao] = {}
        self._max = max_sessoes
        self._lock = threading.Lock()

    def obter(self, session_id: str) -> Sessao:
        with self._lock:  # duas requisicoes novas ao mesmo tempo nao podem criar duas sessoes
            if session_id not in self._sessoes:
                if len(self._sessoes) >= self._max:
                    raise SessoesEsgotadas("limite de sessoes atingido")
                self._sessoes[session_id] = Sessao()
            return self._sessoes[session_id]

    def remover(self, session_id: str) -> None:
        with self._lock:
            self._sessoes.pop(session_id, None)
