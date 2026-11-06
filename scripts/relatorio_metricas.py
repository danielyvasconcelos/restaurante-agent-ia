"""Resumo das metricas registradas em data/metricas.jsonl.

    python -m scripts.relatorio_metricas
"""
from app import config
from app.metrics import RegistroMetricas, resumir


def _linha(nome: str, e: dict | None, unidade: str = "s") -> None:
    if e:
        print(f"  {nome:<14} média {e['media']}{unidade} | p50 {e['p50']}{unidade} | "
              f"p95 {e['p95']}{unidade} | máx {e['max']}{unidade}")


def main() -> None:
    eventos = RegistroMetricas(config.METRICAS_PATH).eventos()
    if not eventos:
        print("Nenhuma métrica registrada ainda. Converse pelo /chat e rode de novo.")
        return
    r = resumir(eventos)
    print(f"Requisições: {r['requisicoes']} | sucessos: {r['sucessos']} | taxa de sucesso: {r['taxa_sucesso']}")
    if r["falhas_por_status"]:
        print(f"Falhas por status HTTP: {r['falhas_por_status']}")
    if r["sucessos"] == 0:
        return
    print(f"Tokens médios por requisição: {r['tokens_entrada_medio']} entrada / {r['tokens_saida_medio']} saída")
    print(f"Chamadas ao modelo por requisição (média): {r['chamadas_llm_medio']}")
    print(f"Custo: total US$ {r['custo_total_usd']:.6f} | médio por requisição US$ {r['custo_medio_usd']:.6f}")
    print("Latência (só requisições bem-sucedidas):")
    _linha("total", r["latencia_total_s"])
    _linha("modelo", r["latencia_llm_s"])
    _linha("busca", r["latencia_busca_s"])


if __name__ == "__main__":
    main()
