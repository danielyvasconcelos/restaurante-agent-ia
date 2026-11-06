"""Carregamento e validacao do cardapio."""
import json
import unicodedata
from pathlib import Path

from app.schemas import Prato

CAMINHO_PADRAO = Path(__file__).resolve().parent.parent / "data" / "menu.json"


def carregar_cardapio(caminho: Path = CAMINHO_PADRAO) -> list[Prato]:
    """Le o JSON, valida cada prato e garante que os ids sejam unicos."""
    # encoding explicito: no Windows o padrao nao e UTF-8 e quebraria os acentos.
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    pratos = [Prato.model_validate(item) for item in dados]

    ids = [p.id for p in pratos]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        raise ValueError(f"ids repetidos no cardapio: {sorted(repetidos)}")
    return pratos


def formatar_preco(preco) -> str:
    """49.9 -> 'R$ 49,90' (formato brasileiro)."""
    return f"R$ {preco:.2f}".replace(".", ",")


def normalizar_texto(texto: str) -> str:
    """Minusculas e sem acento, para comparar 'Pão' com 'pao'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def buscar_por_nome(nome: str, pratos: list[Prato]) -> list[Prato]:
    """Acha pratos pelo nome, ignorando acento e maiusculas.

    Nome exato vence. Senao, devolve os pratos cujo nome contem todas as palavras
    digitadas. Pode devolver 0 (nao achou), 1 (achou) ou varios (ambiguo).
    """
    consulta = normalizar_texto(nome)
    if not consulta:
        return []
    exatos = [p for p in pratos if normalizar_texto(p.nome) == consulta]
    if exatos:
        return exatos
    palavras = consulta.split()
    return [p for p in pratos if all(w in normalizar_texto(p.nome) for w in palavras)]
