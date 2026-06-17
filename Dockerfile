# Atlas — imagem do bot (motor de rotinas pessoais).
# Roda `python -m atlas` em long-poll. Sem domínio, sem porta exposta:
# o container puxa as mensagens do Telegram de dentro pra fora.
FROM python:3.12-slim

# Não gera .pyc e não bufferiza o stdout (logs aparecem na hora).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ATLAS_DB_PATH=/data/atlas.sqlite \
    ATLAS_ROUTINES_DIR=/app/routines \
    ATLAS_DOCS_DIR=/app/docs

WORKDIR /app

# Instala dependências primeiro (cache de camada). O projeto não tem deps
# externas hoje, mas isto mantém o build rápido quando tiver.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Código que muda com frequência por último.
COPY routines ./routines
COPY docs ./docs

# Usuário não-root + diretório de dados persistente (volume).
RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /data \
    && chown -R atlas:atlas /data /app
VOLUME ["/data"]
USER atlas

CMD ["python", "-m", "atlas"]
