# ── 前端构建 ─────────────────────────────────────────────
FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ── 运行时 ───────────────────────────────────────────────
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ ./server/
COPY --from=web /build/dist ./web/dist

RUN useradd -m note && mkdir -p /notes && chown note:note /notes
USER note

ENV NOTE_MD_ROOT=/notes
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8080"]
