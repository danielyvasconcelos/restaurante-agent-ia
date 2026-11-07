# Imagem do atendente virtual. Build: docker compose build
FROM python:3.13-slim

# Sem arquivos .pyc e com logs sem buffer (aparecem na hora no `docker logs`)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Dependências primeiro: esta camada só é refeita se o requirements.txt mudar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código depois: muda toda hora, então fica nas últimas camadas
COPY app ./app
COPY scripts ./scripts
COPY frontend ./frontend
COPY data/menu.json ./data/menu.json

# Usuário sem privilégios: se alguém explorar o app, não é root dentro do container
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
