FROM node:20-slim AS frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --include=dev --ignore-scripts --no-progress --no-audit --no-fund --no-color > npm.log 2>&1 || (grep -i "err" npm.log && exit 1)
COPY src/ ./src/
COPY public/ ./public/
COPY index.html vite.config.ts tsconfig*.json tailwind.config.js postcss.config.js ./
RUN npx vite build

FROM python:3.11-slim

LABEL org.opencontainers.image.title="nstech-audit"
LABEL org.opencontainers.image.description="Sistema de Auditoria nstech"

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Instalar dependencias do sistema e timezone
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tzdata \
  && ln -fs /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
  && dpkg-reconfigure -f noninteractive tzdata \
  && rm -rf /var/lib/apt/lists/*

# Instalar requisitos do Python (cached separately from code)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --no-compile -r requirements.txt

# Copiar os arquivos construídos do frontend
COPY --from=frontend-builder /app/dist ./dist

# Copiar documentos oficiais e configurações de auditoria
# ✅ src/ removido: o frontend foi compilado para dist/ na stage anterior.
# Código-fonte TypeScript não tem utilidade na imagem Python final.
COPY package.json ./package.json
COPY logs/versions/ ./logs/versions/
COPY auditoria_criterios/ ./auditoria_criterios/

# Copiar o código do backend
COPY backend/ ./backend/

# Criar diretórios de runtime
RUN mkdir -p /app/logs /app/backend/data \
  && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Definir ambiente e caminhos
ENV ENVIRONMENT=production
ENV TZ="America/Sao_Paulo"
ENV PORT=8080
ENV PYTHONPATH=/app/backend:/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=""

EXPOSE 8080

# Ponto de entrada
# ✅ 'exec' substitui o shell pelo uvicorn como PID 1.
# Sem 'exec': Docker → SIGTERM → shell (ignora) → Docker mata à força após 10s.
# Com 'exec': Docker → SIGTERM → uvicorn (graceful shutdown correto).
CMD ["sh", "-c", "python3 backend/prestart.py && exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT"]
