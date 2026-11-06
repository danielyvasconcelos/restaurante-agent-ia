"""Registro e resumo de metricas por requisicao (tokens, custo, latencia).

Cada requisicao vira uma linha JSON em data/metricas.jsonl. Nao guardamos o texto
da mensagem (pode ter dado pessoal, como alergias) e o session_id entra so como hash.
"""
import json
import logging
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger("restaurante.metricas")

MAX_EVENTOS_EM_MEMORIA = 10_000  # o arquivo guarda tudo; a memoria so os mais recentes


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RegistroMetricas:
    """Guarda eventos em memoria e, se houver caminho, tambem em um arquivo JSONL."""

    def __init__(self, caminho: Path | str | None = None) -> None:
        self._caminho = Path(caminho) if caminho else None
        self._lock = threading.Lock()
        self._eventos: deque = deque(maxlen=MAX_EVENTOS_EM_MEMORIA)
        if self._caminho and self._caminho.exists():
            self._carregar()

    def _carregar(self) -> None:
        for linha in self._caminho.read_text(encoding="utf-8").splitlines():
            try:
                self._eventos.append(json.loads(linha))
            except json.JSONDecodeError:
                logger.warning("linha corrompida ignorada em %s", self._caminho)

    def registrar(self, evento: dict) -> None:
        evento = {"ts": _agora(), **evento}
        with self._lock:
            self._eventos.append(evento)
            if self._caminho:
                try:
                    with open(self._caminho, "a", encoding="utf-8", newline="\n") as f:
                        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
                except OSError:
                    # Falhar em registrar metrica nunca pode derrubar o atendimento.
                    logger.warning("nao consegui gravar metricas em %s", self._caminho)

    def eventos(self) -> list[dict]:
        with self._lock:
            return list(self._eventos)

    def custo_de_hoje(self) -> float:
        """Gasto acumulado hoje (data em UTC), para o teto diario."""
        hoje = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            return sum(e.get("custo_usd", 0.0) for e in self._eventos if e.get("ts", "")[:10] == hoje)


def _estatisticas(valores: list[float]) -> dict | None:
    if not valores:
        return None
    a = np.asarray(valores, dtype=float)
    return {
        "media": round(float(a.mean()), 3),
        "p50": round(float(np.percentile(a, 50)), 3),
        "p95": round(float(np.percentile(a, 95)), 3),
        "max": round(float(a.max()), 3),
    }


def resumir(eventos: list[dict]) -> dict:
    """Resumo para o README e para o endpoint /metricas.

    Tokens, custo e latencia consideram so as requisicoes bem-sucedidas; as falhas
    aparecem contadas por codigo HTTP (o custo de uma falha nao e medido).
    """
    ok = [e for e in eventos if e.get("ok")]
    falhas = Counter(str(e.get("status")) for e in eventos if not e.get("ok"))
    resumo = {
        "requisicoes": len(eventos),
        "sucessos": len(ok),
        "falhas_por_status": dict(falhas),
        "taxa_sucesso": round(len(ok) / len(eventos), 3) if eventos else None,
    }
    if ok:
        custos = [e["custo_usd"] for e in ok]
        resumo.update(
            tokens_entrada_medio=round(float(np.mean([e["tokens_entrada"] for e in ok])), 1),
            tokens_saida_medio=round(float(np.mean([e["tokens_saida"] for e in ok])), 1),
            custo_total_usd=round(sum(custos), 6),
            custo_medio_usd=round(sum(custos) / len(custos), 6),
            latencia_total_s=_estatisticas([e["latencia_total_s"] for e in ok]),
            latencia_llm_s=_estatisticas([e["latencia_llm_s"] for e in ok]),
            latencia_busca_s=_estatisticas([e["latencia_busca_s"] for e in ok]),
            chamadas_llm_medio=round(float(np.mean([e["chamadas_llm"] for e in ok])), 2),
        )
    return resumo
