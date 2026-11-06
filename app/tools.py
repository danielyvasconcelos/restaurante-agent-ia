"""Ferramentas do agente: adicionar_item, remover_item, ver_carrinho.

Cada ferramenta devolve um dicionario com "ok" True/False. Erros voltam como DADOS,
nao como excecao, para o modelo ler o motivo e se corrigir (ex.: perguntar qual prato).
"""
from decimal import Decimal, InvalidOperation

from google.genai import types

from app.cart import Carrinho, CarrinhoErro
from app.guardrails import avaliar_adicao, conflitos_do_prato, itens_em_conflito
from app.menu import buscar_por_nome, formatar_preco, normalizar_texto
from app.schemas import Alergenico, Categoria, Prato
from app.session import Sessao


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
    carrinho: Carrinho,
    pratos: list[Prato],
    nome_prato: str,
    quantidade: int = 1,
    avaliar=None,
) -> dict:
    """avaliar: funcao opcional (prato -> erro | None) que pode vetar a adicao (guardrail)."""
    prato, erro = _resolver_prato(nome_prato, pratos)
    if erro:
        return erro
    if avaliar is not None:
        veto = avaliar(prato)
        if veto:
            return veto
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


def ver_carrinho(carrinho: Carrinho, alergias: set[str] | None = None) -> dict:
    if carrinho.esta_vazio():
        return {"ok": True, "mensagem": "O carrinho está vazio.", "carrinho": _estado(carrinho)}
    resultado = {"ok": True, "carrinho": _estado(carrinho)}
    conflitos = itens_em_conflito(carrinho, alergias or set())
    if conflitos:
        resultado["avisos_alergia"] = conflitos
    return resultado


# ---------------------------------------------------------------------------
# Filtro exato sobre o cardapio inteiro (resolve o que o RAG nao consegue)
# ---------------------------------------------------------------------------
_SINONIMOS_ALERGENICO = {
    "leite": "lactose",
    "trigo": "gluten",
    "camarao": "crustaceos",
    "crustaceo": "crustaceos",
    "castanha": "castanhas",
    "amendoins": "amendoim",
    "ovos": "ovo",
    "peixes": "peixe",
}
_SINONIMOS_CATEGORIA = {
    "sobremesas": "sobremesa",
    "entradas": "entrada",
    "bebidas": "bebida",
    "pratos principais": "prato principal",
    "prato": "prato principal",
}


def _resolver_alergenico(texto: str) -> str | None:
    n = normalizar_texto(texto)
    n = _SINONIMOS_ALERGENICO.get(n, n)
    return n if n in {a.value for a in Alergenico} else None


def _resolver_categoria(texto: str) -> str | None:
    n = normalizar_texto(texto)
    n = _SINONIMOS_CATEGORIA.get(n, n)
    return n if n in {c.value for c in Categoria} else None


def filtrar_pratos(
    pratos: list[Prato],
    sem_alergenicos: list[str] | None = None,
    categoria: str | None = None,
    preco_maximo: float | None = None,
    alergias_declaradas: set[str] | None = None,
) -> dict:
    """Filtra o cardapio INTEIRO por alergenicos, categoria e preco, em codigo exato."""
    if isinstance(sem_alergenicos, str):
        sem_alergenicos = [sem_alergenicos]

    excluir = set()
    for texto in sem_alergenicos or []:
        valor = _resolver_alergenico(str(texto))
        if valor is None:
            return _erro(
                "alergenico_invalido",
                f"Alergênico desconhecido: '{texto}'.",
                validos=sorted(a.value for a in Alergenico),
            )
        excluir.add(valor)

    cat = None
    if categoria:
        cat = _resolver_categoria(str(categoria))
        if cat is None:
            return _erro(
                "categoria_invalida",
                f"Categoria desconhecida: '{categoria}'.",
                validas=sorted(c.value for c in Categoria),
            )

    limite = None
    if preco_maximo is not None:
        try:
            limite = Decimal(str(preco_maximo))
        except InvalidOperation:
            return _erro("preco_invalido", f"Preço máximo inválido: '{preco_maximo}'.")

    achados = [
        p
        for p in pratos
        if not (excluir & {a.value for a in p.alergenicos})
        and (cat is None or p.categoria.value == cat)
        and (limite is None or p.preco <= limite)
    ]
    def _linha(p: Prato) -> dict:
        linha = {
            "nome": p.nome,
            "categoria": p.categoria.value,
            "preco": formatar_preco(p.preco),
            "alergenicos": [a.value for a in p.alergenicos],
        }
        if alergias_declaradas:
            linha["contem_alergenico_declarado"] = conflitos_do_prato(p, alergias_declaradas)
        return linha

    return {"ok": True, "quantidade": len(achados), "pratos": [_linha(p) for p in achados]}


# ---------------------------------------------------------------------------
# Ligacao com o Gemini: descricao das ferramentas e despachante
# ---------------------------------------------------------------------------
DECLARACOES = [
    types.FunctionDeclaration(
        name="adicionar_item",
        description=(
            "Adiciona um prato ao carrinho do cliente. Use quando o cliente pedir um prato. "
            "Se o nome for ambíguo, a ferramenta devolve as opções para você perguntar ao cliente."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "nome_prato": {"type": "string", "description": "Nome do prato, como o cliente falou."},
                "quantidade": {"type": "integer", "minimum": 1, "description": "Quantidade (padrão 1)."},
            },
            "required": ["nome_prato"],
        },
    ),
    types.FunctionDeclaration(
        name="remover_item",
        description=(
            "Remove um prato do carrinho. Sem quantidade, remove o item inteiro; "
            "com quantidade, remove só essa quantidade."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "nome_prato": {"type": "string", "description": "Nome do prato a remover."},
                "quantidade": {"type": "integer", "minimum": 1, "description": "Quantas unidades remover."},
            },
            "required": ["nome_prato"],
        },
    ),
    types.FunctionDeclaration(
        name="ver_carrinho",
        description="Mostra os itens, as quantidades e o total atual do carrinho.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="filtrar_pratos",
        description=(
            "Filtra o cardápio INTEIRO por alergênicos, categoria e preço máximo. Use para perguntas "
            "como 'quais pratos não têm lactose', 'que sobremesas vocês têm' ou 'o que custa até 30 reais'."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "sem_alergenicos": {
                    "type": "array",
                    "items": {"type": "string", "enum": sorted(a.value for a in Alergenico)},
                    "description": "Exclui pratos que contenham qualquer um destes alergênicos.",
                },
                "categoria": {
                    "type": "string",
                    "enum": sorted(c.value for c in Categoria),
                    "description": "Mostra só pratos desta categoria.",
                },
                "preco_maximo": {"type": "number", "description": "Preço máximo em reais."},
            },
        },
    ),
]
FERRAMENTAS = [types.Tool(function_declarations=DECLARACOES)]


def executar(nome: str, args: dict, sessao: Sessao, pratos: list[Prato]) -> dict:
    """Executa a ferramenta pedida pelo modelo. Nunca levanta excecao: devolve erro como dado.

    O guardrail e injetado aqui (e nao pedido ao modelo): argumentos como 'avaliar' ou
    'alergias_declaradas' nao existem na descricao das ferramentas, e se o modelo os
    enviar mesmo assim, o Python recusa por argumento duplicado.
    """
    carrinho = sessao.carrinho
    funcoes = {
        "adicionar_item": lambda a: adicionar_item(
            carrinho, pratos, avaliar=lambda prato: avaliar_adicao(sessao, prato), **a
        ),
        "remover_item": lambda a: remover_item(carrinho, pratos, **a),
        "ver_carrinho": lambda a: ver_carrinho(carrinho, alergias=sessao.alergias, **a),
        "filtrar_pratos": lambda a: filtrar_pratos(
            pratos, alergias_declaradas=sessao.alergias, **a
        ),
    }
    if nome not in funcoes:
        return _erro("ferramenta_desconhecida", f"Não existe a ferramenta '{nome}'.")
    try:
        return funcoes[nome](dict(args or {}))
    except TypeError as e:
        return _erro("argumentos_invalidos", f"Argumentos inválidos para '{nome}': {e}")
