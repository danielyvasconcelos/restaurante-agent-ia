from app.session import RepositorioSessoes


def test_mesma_sessao_devolve_o_mesmo_objeto():
    repo = RepositorioSessoes()
    assert repo.obter("ana") is repo.obter("ana")


def test_sessoes_diferentes_sao_independentes():
    repo = RepositorioSessoes()
    repo.obter("ana").perguntas.append("oi")
    assert repo.obter("bia").perguntas == []
    assert repo.obter("bia").carrinho is not repo.obter("ana").carrinho
