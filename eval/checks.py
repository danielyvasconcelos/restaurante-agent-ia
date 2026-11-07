"""Verificações da avaliação. Funções puras: não chamam a API, então são testáveis.

Cada caso tem um bloco "esperado". Cada chave é uma verificação independente; o caso só
passa se TODAS passarem. Textos são comparados sem acento e em minúsculas.
"""
import re

from app.menu import normalizar_texto

CHAVES_VALIDAS = {
    "contem_todos",      # todos estes trechos devem aparecer na resposta final
    "contem_algum",      # pelo menos um destes trechos deve aparecer
    "nao_contem",        # nenhum destes trechos pode aparecer
    "nao_regex",         # nenhuma destas expressões regulares pode casar (para negações)
    "ferramenta_ok",     # cada ferramenta listada deve ter rodado com sucesso (ok=true)
    "ferramenta_nao_ok", # nenhuma ferramenta listada pode ter rodado com sucesso
    "carrinho",          # estado final da comanda: {nome do prato: quantidade}
    "alergias",          # alergias registradas na sessão ao final
}


def _norm(textos):
    return [normalizar_texto(t) for t in textos]


def checar(esperado: dict, texto_final: str, chamadas: list[dict], carrinho: dict, alergias: list[str]) -> list[str]:
    """Devolve a lista de falhas (vazia = caso aprovado)."""
    falhas = []
    texto = normalizar_texto(texto_final)

    for trecho in _norm(esperado.get("contem_todos", [])):
        if trecho not in texto:
            falhas.append(f"faltou na resposta: '{trecho}'")

    algum = _norm(esperado.get("contem_algum", []))
    if algum and not any(t in texto for t in algum):
        falhas.append(f"faltou ao menos um de: {algum}")

    for trecho in _norm(esperado.get("nao_contem", [])):
        if trecho in texto:
            falhas.append(f"não deveria aparecer na resposta: '{trecho}'")

    for padrao in esperado.get("nao_regex", []):
        if re.search(padrao, texto):
            falhas.append(f"casou padrão proibido: {padrao}")

    com_sucesso = {c["nome"] for c in chamadas if c.get("ok")}
    for nome in esperado.get("ferramenta_ok", []):
        if nome not in com_sucesso:
            falhas.append(f"ferramenta não rodou com sucesso: {nome}")
    for nome in esperado.get("ferramenta_nao_ok", []):
        if nome in com_sucesso:
            falhas.append(f"ferramenta não deveria ter funcionado: {nome}")

    if "carrinho" in esperado and carrinho != esperado["carrinho"]:
        falhas.append(f"comanda final {carrinho} != esperada {esperado['carrinho']}")

    if "alergias" in esperado and sorted(alergias) != sorted(esperado["alergias"]):
        falhas.append(f"alergias {sorted(alergias)} != esperadas {sorted(esperado['alergias'])}")

    return falhas


def validar_caso(caso: dict, nomes_pratos: set[str]) -> list[str]:
    """Confere se o próprio caso de teste está bem escrito (evita erro no gabarito)."""
    erros = []
    for campo in ("id", "categoria", "turnos", "esperado"):
        if campo not in caso:
            erros.append(f"{caso.get('id', '?')}: falta o campo '{campo}'")
    if erros:
        return erros
    if not caso["turnos"] or not all(isinstance(t, str) and t.strip() for t in caso["turnos"]):
        erros.append(f"{caso['id']}: 'turnos' precisa de textos não vazios")
    desconhecidas = set(caso["esperado"]) - CHAVES_VALIDAS
    if desconhecidas:
        erros.append(f"{caso['id']}: verificações desconhecidas {sorted(desconhecidas)}")
    if not caso["esperado"]:
        erros.append(f"{caso['id']}: 'esperado' vazio (o caso nunca falharia)")
    for nome in caso["esperado"].get("carrinho", {}):
        if nome not in nomes_pratos:
            erros.append(f"{caso['id']}: prato '{nome}' não existe no cardápio")
    for padrao in caso["esperado"].get("nao_regex", []):
        try:
            re.compile(padrao)
        except re.error as e:
            erros.append(f"{caso['id']}: regex inválida ({e})")
    return erros
