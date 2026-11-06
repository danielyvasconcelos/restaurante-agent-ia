"""Carregamento e validacao do cardapio."""
import json
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
