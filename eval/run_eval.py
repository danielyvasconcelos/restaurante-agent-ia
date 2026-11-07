"""Roda a avaliação do agente com o Gemini de verdade (gasta centavos).

    python -m eval.run_eval              # roda todos os casos
    python -m eval.run_eval --ids guard-01 conj-01
    python -m eval.run_eval --repeticoes 3   # repete tudo: mede a variação entre execuções

Saída: tabela no terminal e eval/ultimo_resultado.json.
"""
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from google.genai import errors as genai_errors

from app import config
from app.agent import conversar
from app.menu import carregar_cardapio
from app.rag import carregar_indice, indice_desatualizado
from app.session import Sessao
from eval.checks import checar, validar_caso

PASTA = Path(__file__).resolve().parent
CASOS = PASTA / "eval_set.json"
SAIDA = PASTA / "ultimo_resultado.json"

TENTATIVAS = 3          # tentativas por caso quando o provedor falha (429/5xx/timeout)
ESPERA_429_S = 40       # o limite do plano gratuito é por minuto: espera passar
ESPERA_5XX_S = 10
CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}


def eh_erro_de_infra(e: Exception) -> bool:
    """Falha do provedor (sobrecarga, limite de taxa, timeout), não resposta errada do agente."""
    if isinstance(e, httpx.TimeoutException):
        return True
    return isinstance(e, genai_errors.APIError) and getattr(e, "code", None) in CODIGOS_TRANSITORIOS


def espera_para(e: Exception) -> int:
    return ESPERA_429_S if getattr(e, "code", None) == 429 else ESPERA_5XX_S


def percentil(valores: list[float], p: float) -> float:
    """Mesmo cálculo do app/metrics.py (numpy, com interpolação), para os números baterem."""
    return float(np.percentile(valores, p)) if valores else 0.0


def rodar_caso(caso: dict, pratos, indice) -> dict:
    sessao = Sessao()  # sessão nova por caso: um caso nunca contamina outro
    chamadas, respostas, turnos = [], [], []
    erro = None
    infra = False
    espera = 0
    try:
        for pergunta in caso["turnos"]:
            r = conversar(pergunta, sessao, pratos, indice)
            chamadas.extend(r["chamadas"])
            respostas.append(r["texto"])
            turnos.append(
                {k: r[k] for k in ("tokens_entrada", "tokens_saida", "latencia_s", "custo_usd", "chamadas_llm")}
            )
    except Exception as e:  # uma falha de API não pode derrubar a avaliação inteira
        erro = f"{type(e).__name__}: {str(e)[:200]}"
        infra = eh_erro_de_infra(e)
        espera = espera_para(e)

    carrinho = {i.prato.nome: i.quantidade for i in sessao.carrinho.itens()}
    alergias = sorted(getattr(a, "value", a) for a in sessao.alergias)
    falhas = [f"erro na execução: {erro}"] if erro else checar(
        caso["esperado"], respostas[-1] if respostas else "", chamadas, carrinho, alergias
    )
    return {
        "id": caso["id"],
        "categoria": caso["categoria"],
        "aprovado": not falhas,
        "erro_infra": infra,
        "espera_s": espera,
        "falhas": falhas,
        "turnos_usuario": caso["turnos"],
        "respostas": respostas,
        "chamadas": [{"nome": c["nome"], "ok": c["ok"], "erro": c.get("erro")} for c in chamadas],
        "carrinho": carrinho,
        "alergias": alergias,
        "turnos": turnos,
    }


def resumir(resultados: list[dict]) -> dict:
    """Erro de infraestrutura (provedor fora do ar) NÃO conta como erro do agente:
    o acerto é calculado sobre os casos que de fato rodaram. Os dois números aparecem."""
    executados = [r for r in resultados if not r.get("erro_infra")]
    aprovados = sum(r["aprovado"] for r in executados)
    por_categoria = defaultdict(lambda: [0, 0])
    for r in executados:
        por_categoria[r["categoria"]][1] += 1
        por_categoria[r["categoria"]][0] += r["aprovado"]
    turnos = [t for r in executados for t in r["turnos"]]
    latencias = [t["latencia_s"] for t in turnos]
    custo = sum(t["custo_usd"] for t in turnos)
    n = len(executados)
    return {
        "casos": len(resultados),
        "executados": n,
        "erros_infra": len(resultados) - n,
        "aprovados": aprovados,
        "taxa_acerto": round(aprovados / n, 4) if n else 0.0,
        "taxa_acerto_sobre_todos": round(aprovados / len(resultados), 4) if resultados else 0.0,
        "por_categoria": {c: {"aprovados": a, "total": t} for c, (a, t) in por_categoria.items()},
        "turnos": len(turnos),
        "custo_total_usd": round(custo, 6),
        "custo_medio_por_caso_usd": round(custo / n, 6) if n else 0.0,
        "custo_medio_por_turno_usd": round(custo / len(turnos), 6) if turnos else 0.0,
        "tokens_entrada_total": sum(t["tokens_entrada"] for t in turnos),
        "tokens_saida_total": sum(t["tokens_saida"] for t in turnos),
        "latencia_turno_s": {
            "media": round(statistics.mean(latencias), 2) if latencias else 0.0,
            "p50": round(percentil(latencias, 50), 2),
            "p95": round(percentil(latencias, 95), 2),
            "max": round(max(latencias), 2) if latencias else 0.0,
        },
    }


def imprimir(resultados: list[dict], resumo: dict) -> None:
    print()
    for r in resultados:
        rotulo = "INFRA" if r.get("erro_infra") else ("OK   " if r["aprovado"] else "FALHA")
        print(f"{rotulo} {r['id']:<11} {r['categoria']}")
        for f in r["falhas"]:
            print(f"        - {f}")
        if not r["aprovado"] and not r.get("erro_infra"):
            for pergunta, resposta in zip(r["turnos_usuario"], r["respostas"]):
                print(f"        Você: {pergunta}\n        Atendente: {resposta[:400]}")
    print("\n=== Resumo ===")
    print(f"Acerto nos casos executados: {resumo['aprovados']}/{resumo['executados']} ({resumo['taxa_acerto']:.0%})")
    if resumo["erros_infra"]:
        print(f"ATENÇÃO: {resumo['erros_infra']} caso(s) não rodaram por erro do provedor (429/5xx/timeout) "
              f"mesmo após {TENTATIVAS} tentativas. Sobre todos os {resumo['casos']}: {resumo['taxa_acerto_sobre_todos']:.0%}")
    for cat, v in resumo["por_categoria"].items():
        print(f"  {cat:<28} {v['aprovados']}/{v['total']}")
    lat = resumo["latencia_turno_s"]
    print(f"Custo: US$ {resumo['custo_total_usd']:.4f} no total | "
          f"US$ {resumo['custo_medio_por_caso_usd']:.4f} por caso | US$ {resumo['custo_medio_por_turno_usd']:.4f} por turno")
    print(f"Latência por turno: média {lat['media']} s | p50 {lat['p50']} s | p95 {lat['p95']} s | máx {lat['max']} s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", help="roda só estes casos")
    ap.add_argument("--repeticoes", type=int, default=1, help="repete a bateria N vezes")
    args = ap.parse_args()

    config.validar_config()
    pratos = carregar_cardapio()
    indice = carregar_indice()
    if indice_desatualizado(pratos, indice):
        print("Índice desatualizado. Rode: python -m scripts.build_index")
        return 1

    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    nomes = {p.nome for p in pratos}
    erros = [e for c in casos for e in validar_caso(c, nomes)]
    if erros:
        print("Casos de teste inválidos:\n  " + "\n  ".join(erros))
        return 1
    if args.ids:
        casos = [c for c in casos if c["id"] in args.ids]
        if not casos:
            print("Nenhum caso com esses ids.")
            return 1

    resultados = []
    for rodada in range(args.repeticoes):
        for i, caso in enumerate(casos, 1):
            print(f"[{rodada + 1}/{args.repeticoes}] {i}/{len(casos)} {caso['id']} ...", flush=True)
            for tentativa in range(1, TENTATIVAS + 1):
                r = rodar_caso(caso, pratos, indice)
                r["tentativas"] = tentativa
                if not r["erro_infra"] or tentativa == TENTATIVAS:
                    break
                print(f"    erro do provedor; esperando {r['espera_s']} s e tentando de novo "
                      f"({tentativa}/{TENTATIVAS})", flush=True)
                time.sleep(r["espera_s"])
            resultados.append(r)

    resumo = resumir(resultados)
    imprimir(resultados, resumo)
    SAIDA.write_text(
        json.dumps(
            {
                "data_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "modelo": config.GEMINI_MODEL,
                "repeticoes": args.repeticoes,
                "resumo": resumo,
                "resultados": resultados,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetalhes em {SAIDA}")
    return 0 if resumo["aprovados"] == resumo["casos"] else 2


if __name__ == "__main__":
    sys.exit(main())
