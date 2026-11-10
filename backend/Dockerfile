FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/seeds ./seeds
COPY exporters ./exporters
# Contrato del modelo propio (mismo prompt que el entrenamiento y el celular):
# prompt_contract.py lee el prompt de sistema del archivo Dart.
COPY training/prompt_contract.py ./training/prompt_contract.py
COPY mobile/lib/services/assistant_prompt.dart ./mobile/lib/services/assistant_prompt.dart
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
