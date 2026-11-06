"""Testes da busca semantica. Nao chamam a API: usam vetores falsos."""
import numpy as np
import pytest

from app import rag
from app.menu import carregar_cardapio


def test_texto_do_prato_inclui_ingredientes_e_alergenicos():
    pratos = {p.nome: p for p in carregar_cardapio()}
    texto = rag.texto_do_prato(pratos["Moqueca de Camarão"])
    assert "camarão" in texto
    assert "crustaceos" in texto
    assert "62" not in texto  # preco fica de fora


def test_normalizar_deixa_vetores_com_comprimento_1():
    m = rag.normalizar([[3.0, 4.0], [0.0, 2.0]])
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0)


def test_normalizar_rejeita_vetor_nulo():
    with pytest.raises(ValueError):
        rag.normalizar([[0.0, 0.0]])


def test_top_k_ordena_do_mais_parecido_para_o_menos():
    matriz = rag.normalizar([[1, 0], [0, 1], [1, 1]])
    consulta = rag.normalizar([1, 0.1])[0]
    resultado = rag.top_k(matriz, consulta, k=3)
    assert [pos for pos, _ in resultado] == [0, 2, 1]
    scores = [s for _, s in resultado]
    assert scores == sorted(scores, reverse=True)


def test_top_k_nao_estoura_quando_k_maior_que_o_indice():
    matriz = rag.normalizar([[1, 0], [0, 1]])
    assert len(rag.top_k(matriz, np.array([1.0, 0.0]), k=10)) == 2


def _embeddings_falsos(textos, tipo="documento"):
    return [[float(len(t)), float(i + 1), 1.0] for i, t in enumerate(textos)]


def test_salvar_e_carregar_indice_preserva_os_dados(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "gerar_embeddings", _embeddings_falsos)
    pratos = carregar_cardapio()
    indice = rag.construir_indice(pratos)
    arquivo = tmp_path / "idx.json"
    rag.salvar_indice(indice, arquivo)
    lido = rag.carregar_indice(arquivo)
    assert lido.ids == indice.ids
    assert lido.hashes == indice.hashes
    assert np.allclose(lido.matriz, indice.matriz, atol=1e-6)
    assert not rag.indice_desatualizado(pratos, lido)


def test_indice_fica_desatualizado_quando_o_cardapio_muda(monkeypatch):
    monkeypatch.setattr(rag, "gerar_embeddings", _embeddings_falsos)
    pratos = carregar_cardapio()
    indice = rag.construir_indice(pratos)
    alterado = [p.model_copy(update={"descricao": "Descricao totalmente nova aqui."}) for p in pratos]
    assert rag.indice_desatualizado(alterado, indice)


def test_carregar_indice_inexistente_da_mensagem_util(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_index"):
        rag.carregar_indice(tmp_path / "nao_existe.json")
