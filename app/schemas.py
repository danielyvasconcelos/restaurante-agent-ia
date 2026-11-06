"""Modelos de dados (Pydantic) do projeto."""
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class Alergenico(str, Enum):
    """Lista fechada de alergenicos. Valores sem acento, para comparar sem erro."""

    GLUTEN = "gluten"
    LACTOSE = "lactose"
    OVO = "ovo"
    AMENDOIM = "amendoim"
    CASTANHAS = "castanhas"
    CRUSTACEOS = "crustaceos"
    PEIXE = "peixe"
    SOJA = "soja"
    GERGELIM = "gergelim"


class Categoria(str, Enum):
    ENTRADA = "entrada"
    PRATO_PRINCIPAL = "prato principal"
    SOBREMESA = "sobremesa"
    BEBIDA = "bebida"


class Prato(BaseModel):
    # extra="forbid": campo desconhecido no JSON (ex.: "alergenicoss") vira erro.
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    nome: str = Field(min_length=2)
    categoria: Categoria
    descricao: str = Field(min_length=10)
    # Decimal em vez de float: dinheiro nao deve acumular erro de arredondamento.
    preco: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    ingredientes: list[str] = Field(min_length=1)
    alergenicos: list[Alergenico]

    @field_serializer("preco", when_used="json")
    def _preco_com_duas_casas(self, preco: Decimal) -> str:
        """Na API o preco sai sempre como texto com 2 casas ('49.90'), nunca float."""
        return f"{preco:.2f}"


# --- Contrato da API HTTP (Etapa 8) ---------------------------------------------------
MAX_MENSAGEM_CHARS = 500


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    mensagem: str = Field(min_length=1, max_length=MAX_MENSAGEM_CHARS)


class ChamadaFerramenta(BaseModel):
    nome: str
    args: dict
    ok: bool | None = None
    erro: str | None = None


class Metricas(BaseModel):
    tokens_entrada: int
    tokens_saida: int
    chamadas_llm: int  # quantas vezes o modelo foi chamado neste turno (1 + uma por rodada de ferramentas)
    latencia_busca_s: float  # busca semantica (inclui gerar o embedding da pergunta)
    latencia_llm_s: float  # soma das chamadas ao modelo neste turno
    latencia_total_s: float  # a requisicao inteira (busca + modelo + ferramentas)
    custo_usd: float


class ChatResponse(BaseModel):
    session_id: str
    resposta: str
    alergias: list[str]
    chamadas: list[ChamadaFerramenta]
    carrinho: dict
    metricas: Metricas
