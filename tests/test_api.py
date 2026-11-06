"""Testes da API. O Gemini e substituido por funcoes falsas: nenhum chama a rede."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app import config, main
from app.menu import carregar_cardapio
from app.rag import CAMINHO_INDICE
from app.session import RepositorioSessoes, Sessao


def _resultado(texto="Olá!"):
    return {
        "texto": texto, "chamadas": [], "pratos_usados": [], "alergias": [],
        "tokens_entrada": 100, "tokens_saida": 20, "latencia_s": 0.5, "custo_usd": 0.0001,
    }


@pytest.fixture
def pratos():
    return carregar_cardapio()


def _cliente(pratos, repositorio=None):
    app = main.criar_app(pratos=pratos, indice=object(), repositorio=repositorio)
    return TestClient(app)


def _chat(c, mensagem="oi", session_id="ana"):
    return c.post("/chat", json={"session_id": session_id, "mensagem": mensagem})


def test_health_e_cardapio(pratos):
    with _cliente(pratos) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["pratos"] == len(pratos)
        itens = c.get("/cardapio").json()
        assert len(itens) == len(pratos)
        assert itens[0]["preco"] == "49.90"  # dinheiro como texto exato, nao float


def test_chat_devolve_resposta_carrinho_e_metricas(monkeypatch, pratos):
    def falso(pergunta, sessao, p, i):
        sessao.perguntas.append(pergunta)
        sessao.carrinho.adicionar(p[0], 2)
        r = _resultado("Adicionei!")
        r["chamadas"] = [{"nome": "adicionar_item", "args": {"nome_prato": "feijoada"}, "ok": True, "erro": None}]
        return r

    monkeypatch.setattr(main, "conversar", falso)
    with _cliente(pratos) as c:
        r = _chat(c, "quero 2 feijoadas")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resposta"] == "Adicionei!"
    assert corpo["carrinho"]["total"] == "R$ 99,80"
    assert corpo["chamadas"][0]["nome"] == "adicionar_item"
    assert corpo["metricas"]["tokens_entrada"] == 100
    assert corpo["metricas"]["latencia_total_s"] >= 0


def test_mesma_sessao_mantem_estado_e_sessoes_diferentes_sao_isoladas(monkeypatch, pratos):
    def falso(pergunta, sessao, p, i):
        sessao.perguntas.append(pergunta)
        return _resultado(f"mensagens nesta sessao: {len(sessao.perguntas)}")

    monkeypatch.setattr(main, "conversar", falso)
    with _cliente(pratos) as c:
        assert "1" in _chat(c, "a", "ana").json()["resposta"]
        assert "2" in _chat(c, "b", "ana").json()["resposta"]
        assert "1" in _chat(c, "c", "bia").json()["resposta"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"session_id": "ana", "mensagem": ""},
        {"session_id": "ana", "mensagem": "    "},
        {"session_id": "ana", "mensagem": "x" * 501},
        {"session_id": "ana"},
        {"session_id": "a b", "mensagem": "oi"},
        {"session_id": "../etc", "mensagem": "oi"},
        {"session_id": "a" * 65, "mensagem": "oi"},
        {"session_id": "ana", "mensagem": "oi", "extra": 1},
    ],
)
def test_entrada_invalida_e_rejeitada_antes_de_gastar_tokens(monkeypatch, pratos, corpo):
    chamadas = []
    monkeypatch.setattr(main, "conversar", lambda *a: chamadas.append(1))
    with _cliente(pratos) as c:
        assert c.post("/chat", json=corpo).status_code == 422
    assert chamadas == []  # o modelo nem foi chamado


def test_falha_do_provedor_vira_502_e_desfaz_o_turno(monkeypatch, pratos):
    def falho(pergunta, sessao, p, i):
        sessao.perguntas.append(pergunta)
        sessao.alergias.add("lactose")
        sessao.carrinho.adicionar(p[0], 1)  # a ferramenta chegou a rodar...
        raise genai_errors.ServerError(500, {"error": {"message": "segredo interno", "status": "X"}})

    monkeypatch.setattr(main, "conversar", falho)
    repo = RepositorioSessoes()
    with _cliente(pratos, repo) as c:
        r = _chat(c, "quero feijoada")
    assert r.status_code == 502
    assert "segredo interno" not in r.text  # nada de detalhe interno para o cliente
    sessao = repo.obter("ana")
    assert sessao.carrinho.esta_vazio()  # ...mas o turno inteiro foi desfeito
    assert sessao.perguntas == [] and sessao.alergias == set()


def test_timeout_vira_504(monkeypatch, pratos):
    def lento(*a):
        raise httpx.ReadTimeout("demorou")

    monkeypatch.setattr(main, "conversar", lento)
    with _cliente(pratos) as c:
        assert _chat(c).status_code == 504


def test_erro_inesperado_nao_vaza_detalhes(monkeypatch, pratos):
    def quebrado(*a):
        raise ValueError("chave sk-123 vazou")

    monkeypatch.setattr(main, "conversar", quebrado)
    app = main.criar_app(pratos=pratos, indice=object())
    with TestClient(app, raise_server_exceptions=False) as c:
        r = _chat(c)
    assert r.status_code == 500
    assert "sk-123" not in r.text


def test_conversa_longa_demais_da_409(monkeypatch, pratos):
    monkeypatch.setattr(config, "MAX_PERGUNTAS_POR_SESSAO", 2)

    def falso(pergunta, sessao, p, i):
        sessao.perguntas.append(pergunta)
        return _resultado()

    monkeypatch.setattr(main, "conversar", falso)
    with _cliente(pratos) as c:
        assert _chat(c).status_code == 200
        assert _chat(c).status_code == 200
        assert _chat(c).status_code == 409
        assert c.delete("/sessoes/ana").status_code == 204  # comecar de novo
        assert _chat(c).status_code == 200


def test_limite_de_sessoes_da_503(monkeypatch, pratos):
    monkeypatch.setattr(main, "conversar", lambda pergunta, sessao, p, i: _resultado())
    with _cliente(pratos, RepositorioSessoes(max_sessoes=1)) as c:
        assert _chat(c, session_id="ana").status_code == 200
        assert _chat(c, session_id="bia").status_code == 503
        assert _chat(c, session_id="ana").status_code == 200  # quem ja tem sessao continua


def test_delete_de_sessao_inexistente_e_idempotente(pratos):
    with _cliente(pratos) as c:
        assert c.delete("/sessoes/nao_existe").status_code == 204


def test_requisicoes_simultaneas_da_mesma_sessao_nao_se_misturam(monkeypatch, pratos):
    ativas, maximo, trava = 0, 0, threading.Lock()

    def lento(pergunta, sessao, p, i):
        nonlocal ativas, maximo
        with trava:
            ativas += 1
            maximo = max(maximo, ativas)
        time.sleep(0.05)
        with trava:
            ativas -= 1
        return _resultado()

    monkeypatch.setattr(main, "conversar", lento)
    with _cliente(pratos) as c:
        with ThreadPoolExecutor(4) as pool:
            codigos = list(pool.map(lambda _: _chat(c).status_code, range(4)))
    assert codigos == [200] * 4
    assert maximo == 1  # nunca duas ao mesmo tempo na mesma sessao


# --- sessao: checkpoint e restauracao ---------------------------------------------
def test_restaurar_volta_ao_estado_da_foto(pratos):
    s = Sessao()
    s.perguntas.append("oi")
    foto = s.checkpoint()
    s.perguntas.append("quero feijoada")
    s.historico.append("x")
    s.alergias.add("ovo")
    s.pendencias[1] = 2
    s.carrinho.adicionar(pratos[0], 3)
    s.restaurar(foto)
    assert s.perguntas == ["oi"] and s.historico == []
    assert s.alergias == set() and s.pendencias == {}
    assert s.carrinho.esta_vazio()


# --- com os arquivos reais (pulado se o indice ainda nao foi gerado) ---------------
@pytest.mark.skipif(not CAMINHO_INDICE.exists(), reason="rode scripts.build_index primeiro")
def test_sobe_com_o_cardapio_e_o_indice_reais():
    with TestClient(main.criar_app()) as c:
        assert c.get("/health").json()["pratos"] == 15
