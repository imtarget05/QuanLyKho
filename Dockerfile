FROM python:3.11-slim

WORKDIR /app/backend

COPY backend/pyproject.toml backend/poetry.lock ./
RUN pip install --no-cache-dir poetry==2.5.1 poetry-plugin-export==1.10.1 && \
    poetry export -o requirements.txt --without-hashes && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY docs /app/docs
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/entrypoint.sh /app/backend/entrypoint.sh
RUN chmod +x /app/backend/entrypoint.sh && \
    useradd --uid 10001 --create-home --shell /bin/bash appuser && \
    chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["/app/backend/entrypoint.sh"]
