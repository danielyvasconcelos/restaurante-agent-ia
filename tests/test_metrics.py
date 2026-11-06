"""Testes do registro e do resumo de metricas."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.metrics import RegistroMetricas, resumir


def _ev(total=1.0, llm=0.8, custo=0.001, ok=True, status=200, **extra):
    return {
        "ok": ok, "status": status, "tokens_entrada": 1000, "tokens_saida": 100,
        "latencia_total_s": total, "latencia_llm_s": llm, "latencia_busca_s": 0.2,
        "custo_usd": custo, "chamadas_llm": 1, **extra,
    }


def test_registrar_persiste_e_uma_nova_instancia_recarrega(tmp_path):
    arquivo = tmp_path / "m.jsonl"
    RegistroMetricas(arquivo).registrar(_ev(custo=0.002))
    novo = RegistroMetricas(arquivo)
    assert len(novo.eventos()) == 1
    assert novo.eventos()[0]["custo_usd"] == 0.002
    assert "ts" in novo.eventos()[0]


def test_linha_corrompida_e_ignorada(tmp_path):
    arquivo = tmp_path / "m.jsonl"
    arquivo.write_text(json.dumps(_ev()) + "\nisto nao e json\n" + json.dumps(_ev()) + "\n", encoding="utf-8")
    assert len(RegistroMetricas(arquivo).eventos()) == 2


def test_falha_ao_gravar_nao_derruba_o_atendimento(tmp_path):
    registro = RegistroMetricas(tmp_path / "pasta_que_nao_existe" / "m.jsonl")
    registro.registrar(_ev())  # nao pode levantar excecao
    assert len(registro.eventos()) == 1  # continua valendo em memoria


def test_gravacoes_simultaneas_nao_corrompem_o_arquivo(tmp_path):
    arquivo = tmp_path / "m.jsonl"
    registro = RegistroMetricas(arquivo)
    threads = [threading.Thread(target=registro.registrar, args=(_ev(),)) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 50
    assert all(json.loads(l)["ok"] for l in linhas)  # nenhuma linha quebrada


def test_resumo_calcula_media_e_percentis():
    r = resumir([_ev(total=t) for t in (1, 2, 3, 10)])
    lat = r["latencia_total_s"]
    assert lat["media"] == 4.0
    assert lat["p50"] == 2.5
    assert lat["p95"] == pytest.approx(8.95)  # a media (4,0) esconde o caso lento; o p95 mostra
    assert lat["max"] == 10


def test_resumo_separa_sucessos_de_falhas():
    eventos = [_ev(custo=0.001), _ev(custo=0.003), _ev(ok=False, status=502, custo=0.0, total=30.0)]
    r = resumir(eventos)
    assert r["requisicoes"] == 3 and r["sucessos"] == 2
    assert r["taxa_sucesso"] == pytest.approx(0.667, abs=0.001)
    assert r["falhas_por_status"] == {"502": 1}
    assert r["custo_total_usd"] == pytest.approx(0.004)
    assert r["custo_medio_usd"] == pytest.approx(0.002)
    assert r["latencia_total_s"]["max"] == 1.0  # a falha de 30 s nao entra na latencia de sucesso


def test_resumo_vazio_e_so_falhas_nao_quebram():
    assert resumir([])["requisicoes"] == 0
    r = resumir([_ev(ok=False, status=504)])
    assert r["sucessos"] == 0 and "custo_medio_usd" not in r


def test_custo_de_hoje_ignora_dias_anteriores():
    registro = RegistroMetricas(None)
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    registro.registrar({"ts": ontem, "custo_usd": 5.0})
    registro.registrar({"custo_usd": 0.25})
    registro.registrar({"custo_usd": 0.25})
    assert registro.custo_de_hoje() == pytest.approx(0.5)
