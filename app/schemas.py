"""Modelos de dados (Pydantic) do projeto."""
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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
