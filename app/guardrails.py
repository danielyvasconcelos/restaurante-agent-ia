"""Guardrail de alergenicos.

Regras que o CODIGO garante, mesmo que o modelo erre, esqueca ou seja enganado por
uma mensagem do cliente. O prompt pede; o guardrail impoe.

Escolha de projeto: na duvida, errar para o lado seguro. Registrar uma alergia a mais
(falso positivo) so gera uma pergunta extra. Deixar de registrar uma (falso negativo)
pode colocar uma pessoa em risco.
"""
import re

from app.cart import Carrinho
from app.menu import normalizar_texto
from app.schemas import Prato
from app.session import Sessao

# --- 1. Deteccao de alergias na mensagem do cliente -------------------------------
_SEPARADOR = re.compile(r"[.!?;\n]+|\bmas\b|\bporem\b")
_GATILHO = re.compile(
    r"\b(alergi\w*|intoleran\w*|celiac\w*|restricao|restricoes"
    r"|nao (?:posso|consigo) (?:comer|tomar|ingerir))\b"
)
# "nao tenho alergia a lactose": a negacao anula so esse trecho, nao a mensagem toda.
_NEGADO = re.compile(
    r"\b(?:nao|sem|nenhuma?)\b(?:\W+\w+){0,3}?\W+(?:alergi\w*|intoleran\w*)(?:\W+\w+){0,2}"
)
_LEXICO = [
    (r"\b(lactose|leite|laticinio\w*|derivados? de leite)\b", {"lactose"}),
    (r"\b(gluten|trigo|celiac\w*)\b", {"gluten"}),
    (r"\bovos?\b", {"ovo"}),
    (r"\bamendoi(?:m|ns)\b", {"amendoim"}),  # singular termina em m, plural em ns
    (r"\b(castanha\w*|caju|nozes?)\b", {"castanhas"}),
    (r"\b(camarao|camaroes|crustace\w*|marisco\w*|lagosta|siri|caranguejo)\b", {"crustaceos"}),
    (r"\bfrutos? do mar\b", {"crustaceos", "peixe"}),  # na duvida, os dois
    (r"\b(peixes?|anchova\w*)\b", {"peixe"}),
    (r"\bsoja\b", {"soja"}),
    (r"\b(gergelim|tahine)\b", {"gergelim"}),
]


def _trechos_com_restricao(texto: str) -> list[str]:
    """Trechos da mensagem que falam de alergia/restricao (ja sem as negacoes)."""
    trechos = []
    for trecho in _SEPARADOR.split(normalizar_texto(texto)):
        trecho = _NEGADO.sub(" ", trecho)
        if _GATILHO.search(trecho):
            trechos.append(trecho)
    return trechos


def _alergenicos_do_trecho(trecho: str) -> set[str]:
    achados: set[str] = set()
    for padrao, valores in _LEXICO:
        if re.search(padrao, trecho):
            achados |= valores
    return achados


def detectar_alergias(texto: str) -> set[str]:
    """Alergenicos que o cliente declarou ter nesta mensagem."""
    achados: set[str] = set()
    for trecho in _trechos_com_restricao(texto):
        achados |= _alergenicos_do_trecho(trecho)
    return achados


def restricao_nao_reconhecida(texto: str) -> bool:
    """True se o cliente falou de alergia/restricao mas nao conseguimos mapear a nenhum alergenico."""
    return any(not _alergenicos_do_trecho(t) for t in _trechos_com_restricao(texto))


# --- 2. Confirmacao do cliente -----------------------------------------------------
_NEGACAO = re.compile(r"\b(nao|sem|mas|porem|cancel\w*|deixa|esquece|desisto)\b")
_AFIRMACAO = re.compile(
    r"\b(sim|confirmo|confirmado|pode adicionar|pode sim|pode ser|quero sim|mesmo assim"
    r"|com certeza|isso mesmo|claro|ok|okay|fechado|beleza)\b"
)


def eh_confirmacao(texto: str) -> bool:
    """True so se a mensagem confirma com clareza. Na duvida, NAO confirma."""
    n = normalizar_texto(texto)
    if _NEGACAO.search(n):
        return False
    return bool(_AFIRMACAO.search(n)) or n.strip(" .!") == "pode"


# --- 3. Regras sobre o carrinho ----------------------------------------------------
def conflitos_do_prato(prato: Prato, alergias: set[str]) -> list[str]:
    return sorted({a.value for a in prato.alergenicos} & set(alergias))


def itens_em_conflito(carrinho: Carrinho, alergias: set[str]) -> list[dict]:
    achados = []
    for item in carrinho.itens():
        conflitos = conflitos_do_prato(item.prato, alergias)
        if conflitos:
            achados.append({"item": item.prato.nome, "alergenicos": conflitos})
    return achados


def avaliar_adicao(sessao: Sessao, prato: Prato) -> dict | None:
    """Decide se um prato pode entrar no carrinho.

    Devolve None se pode. Senao, devolve o erro que a ferramenta repassa ao modelo.
    A confirmacao so vale se: (1) o alerta foi dado na mensagem imediatamente anterior,
    (2) o cliente confirmou com clareza na mensagem atual. O modelo nao consegue
    confirmar por conta propria, nem dentro do mesmo turno.
    """
    conflitos = conflitos_do_prato(prato, sessao.alergias)
    if not conflitos:
        return None

    turno = len(sessao.perguntas)
    alerta_anterior = sessao.pendencias.get(prato.id) == turno - 1
    if alerta_anterior and sessao.perguntas and eh_confirmacao(sessao.perguntas[-1]):
        del sessao.pendencias[prato.id]
        return None

    sessao.pendencias[prato.id] = turno
    lista = ", ".join(conflitos)
    return {
        "ok": False,
        "erro": "alergenico_detectado",
        "requer_confirmacao_do_cliente": True,
        "alergenicos": conflitos,
        "mensagem": (
            f"O cliente declarou alergia a {lista} e '{prato.nome}' contém {lista}. "
            "NÃO foi adicionado. Avise o cliente do risco e pergunte se quer mesmo o prato. "
            "Só chame adicionar_item de novo se ele confirmar claramente na PRÓXIMA mensagem."
        ),
    }
