"""API HTTP do atendente virtual.

    uvicorn app.main:app --reload

Documentacao interativa gerada automaticamente em http://127.0.0.1:8000/docs
"""
import hashlib
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from google.genai import errors as genai_errors

from app import config
from app.agent import conversar
from app.menu import carregar_cardapio
from app.metrics import RegistroMetricas, resumir
from app.rag import carregar_indice, indice_desatualizado
from app.schemas import ChamadaFerramenta, ChatRequest, ChatResponse, Metricas, Prato
from app.session import RepositorioSessoes, SessoesEsgotadas
from app.tools import estado_carrinho

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restaurante")


def _erro_http(e: Exception) -> HTTPException | None:
    """Traduz falhas do provedor de IA em respostas HTTP, sem vazar detalhes internos."""
    if isinstance(e, httpx.TimeoutException):
        return HTTPException(504, "O serviço de IA demorou demais para responder. Tente de novo.")
    if isinstance(e, genai_errors.APIError):
        return HTTPException(502, "O serviço de IA está indisponível no momento. Tente de novo.")
    return None


def _evento(req: ChatRequest, status: int, total: float, r: dict | None = None) -> dict:
    """Linha de metrica de uma requisicao. Sem texto da mensagem; session_id so como hash."""
    evento = {
        "sessao": hashlib.sha256(req.session_id.encode()).hexdigest()[:8],
        "modelo": config.GEMINI_MODEL,
        "status": status,
        "ok": status == 200,
        "msg_chars": len(req.mensagem),
        "latencia_total_s": total,
        # Em falha o consumo de tokens nao e medido (fica 0), mesmo que o provedor tenha cobrado.
        "chamadas_llm": 0, "ferramentas": 0, "tokens_entrada": 0, "tokens_saida": 0,
        "latencia_busca_s": 0.0, "latencia_llm_s": 0.0, "custo_usd": 0.0,
    }
    if r:
        evento.update(
            chamadas_llm=r["chamadas_llm"],
            ferramentas=len(r["chamadas"]),
            tokens_entrada=r["tokens_entrada"],
            tokens_saida=r["tokens_saida"],
            latencia_busca_s=r["latencia_busca_s"],
            latencia_llm_s=r["latencia_s"],
            custo_usd=r["custo_usd"],
        )
    return evento


def criar_app(
    pratos=None, indice=None, repositorio=None, registro=None, orcamento_diario_usd=None
) -> FastAPI:
    """Monta a aplicacao. Os parametros existem para os testes injetarem dados falsos."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Carrega uma vez, na subida do servidor. Falhar aqui e melhor que falhar no 1o cliente.
        app.state.pratos = pratos if pratos is not None else carregar_cardapio()
        if indice is not None:
            app.state.indice = indice
        else:
            app.state.indice = carregar_indice()
            if indice_desatualizado(app.state.pratos, app.state.indice):
                raise RuntimeError(
                    "O índice está desatualizado em relação ao cardápio ou ao modelo. "
                    "Rode: python -m scripts.build_index"
                )
        app.state.repositorio = repositorio if repositorio is not None else RepositorioSessoes()
        app.state.registro = registro if registro is not None else RegistroMetricas(config.METRICAS_PATH)
        app.state.orcamento = (
            orcamento_diario_usd if orcamento_diario_usd is not None else config.ORCAMENTO_DIARIO_USD
        )
        logger.info("API pronta: %d pratos, modelo %s", len(app.state.pratos), config.GEMINI_MODEL)
        yield

    app = FastAPI(title="Atendente virtual do restaurante", lifespan=lifespan)

    @app.get("/health")
    def health(request: Request) -> dict:
        return {
            "status": "ok",
            "pratos": len(request.app.state.pratos),
            "modelo": config.GEMINI_MODEL,
        }

    @app.get("/cardapio", response_model=list[Prato])
    def cardapio(request: Request):
        return request.app.state.pratos

    @app.get("/metricas")
    def metricas(request: Request) -> dict:
        estado = request.app.state
        return {
            **resumir(estado.registro.eventos()),
            "orcamento": {
                "diario_usd": estado.orcamento,
                "gasto_hoje_usd": round(estado.registro.custo_de_hoje(), 6),
            },
        }

    # `def` (e nao `async def`): a chamada ao Gemini bloqueia, entao o FastAPI a roda numa thread
    # e o servidor continua atendendo outras requisicoes enquanto esta espera.
    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest, request: Request) -> ChatResponse:
        estado = request.app.state

        # Teto diario: confere ANTES de gastar. E aproximado: requisicoes simultaneas
        # podem ultrapassar o limite por alguns centavos.
        if estado.orcamento > 0 and estado.registro.custo_de_hoje() >= estado.orcamento:
            raise HTTPException(429, "O limite diário de uso foi atingido. Tente novamente amanhã.")

        try:
            sessao = estado.repositorio.obter(req.session_id)
        except SessoesEsgotadas:
            raise HTTPException(503, "Servidor ocupado. Tente novamente mais tarde.")

        inicio = time.perf_counter()
        with sessao.lock:
            if len(sessao.perguntas) >= config.MAX_PERGUNTAS_POR_SESSAO:
                raise HTTPException(409, "Esta conversa ficou longa demais. Inicie uma nova sessão.")

            foto = sessao.checkpoint()
            try:
                r = conversar(req.mensagem, sessao, estado.pratos, estado.indice)
            except Exception as e:
                # Atomicidade: se o turno falhou, nada dele fica (nem item no carrinho).
                sessao.restaurar(foto)
                http = _erro_http(e)
                status = http.status_code if http else 500
                estado.registro.registrar(
                    _evento(req, status, round(time.perf_counter() - inicio, 2))
                )
                if http is None:
                    logger.exception("erro inesperado session=%s", req.session_id)
                    raise
                logger.warning("falha do provedor session=%s tipo=%s", req.session_id, type(e).__name__)
                raise http from e
            carrinho = estado_carrinho(sessao.carrinho)

        total = round(time.perf_counter() - inicio, 2)
        estado.registro.registrar(_evento(req, 200, total, r))
        logger.info(
            "chat session=%s msg_chars=%d ferramentas=%d tokens=%d/%d llm=%.2fs total=%.2fs custo=%.6f",
            req.session_id, len(req.mensagem), len(r["chamadas"]),
            r["tokens_entrada"], r["tokens_saida"], r["latencia_s"], total, r["custo_usd"],
        )  # o texto da mensagem NAO vai para o log: pode conter dado pessoal (ex.: alergias)
        return ChatResponse(
            session_id=req.session_id,
            resposta=r["texto"],
            alergias=r["alergias"],
            chamadas=[ChamadaFerramenta(**c) for c in r["chamadas"]],
            carrinho=carrinho,
            metricas=Metricas(
                tokens_entrada=r["tokens_entrada"],
                tokens_saida=r["tokens_saida"],
                chamadas_llm=r["chamadas_llm"],
                latencia_busca_s=r["latencia_busca_s"],
                latencia_llm_s=r["latencia_s"],
                latencia_total_s=total,
                custo_usd=r["custo_usd"],
            ),
        )

    @app.delete("/sessoes/{session_id}", status_code=204)
    def encerrar_sessao(session_id: str, request: Request) -> Response:
        request.app.state.repositorio.remover(session_id)  # idempotente: apagar o que nao existe e ok
        return Response(status_code=204)

    return app


app = criar_app()
