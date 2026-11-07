"""Testes da interface: entrega, seguranca e consistencia com o backend."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.menu import carregar_cardapio
from app.metrics import RegistroMetricas
from app.schemas import MAX_MENSAGEM_CHARS

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
JS = (RAIZ / "frontend" / "app.js").read_text(encoding="utf-8")
CSS = (RAIZ / "frontend" / "style.css").read_text(encoding="utf-8")


@pytest.fixture
def cliente():
    app = main.criar_app(pratos=carregar_cardapio(), indice=object(), registro=RegistroMetricas(None))
    with TestClient(app) as c:
        yield c


def test_raiz_entrega_a_pagina_com_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert 'lang="pt-BR"' in r.text


def test_arquivos_estaticos_sao_servidos(cliente):
    assert cliente.get("/static/app.js").status_code == 200
    assert cliente.get("/static/style.css").status_code == 200
    assert cliente.get("/static/nao_existe.js").status_code == 404


def test_pagina_nao_depende_de_recursos_externos():
    assert not re.search(r'(?:src|href)="https?://', HTML)
    assert "@import" not in CSS and "url(http" not in CSS


def test_html_sem_script_nem_manipulador_inline():
    assert not re.search(r"<script(?![^>]*\bsrc=)", HTML)
    assert not re.search(r"\son[a-z]+\s*=", HTML)  # onclick=, onload=...
    assert 'style="' not in HTML


@pytest.mark.parametrize(
    "perigoso", ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setAttribute(\"style\""]
)
def test_js_nunca_injeta_html_nem_executa_texto(perigoso):
    """O texto do modelo entra na pagina so como texto. Uma resposta maliciosa nao vira codigo."""
    assert perigoso not in JS


def test_limite_de_caracteres_do_front_e_do_back_coincidem():
    assert f"MAX_CHARS = {MAX_MENSAGEM_CHARS}" in JS
    assert f'maxlength="{MAX_MENSAGEM_CHARS}"' in HTML


def test_toda_mensagem_de_erro_do_backend_tem_texto_na_interface():
    codigos = set(re.findall(r'_erro\(\s*"([a-z_]+)"', (RAIZ / "app" / "tools.py").read_text(encoding="utf-8")))
    codigos |= {"alergenico_detectado"}  # vem do guardrail
    faltando = [c for c in sorted(codigos) if c not in JS]
    assert faltando == [], f"codigos sem texto na interface: {faltando}"


def test_ids_usados_pelo_js_existem_no_html():
    usados = set(re.findall(r'\$\("([a-z-]+)"\)', JS))
    existentes = set(re.findall(r'id="([a-z-]+)"', HTML))
    assert usados <= existentes, f"ids ausentes no HTML: {sorted(usados - existentes)}"
