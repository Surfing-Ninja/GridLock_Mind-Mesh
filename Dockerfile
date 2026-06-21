FROM node:22-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/curbflow-ai/src:/app/curbflow-ai \
    NEXT_PUBLIC_API_BASE_URL=/api \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN pip install --upgrade pip \
    && pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        pandas \
        numpy \
        pyarrow \
        duckdb \
        scikit-learn \
        joblib \
        pyyaml \
        pydantic \
        pydantic-settings \
        python-dotenv \
        shapely \
        networkx \
        geopy

COPY curbflow-ai/apps/web/package.json curbflow-ai/apps/web/package-lock.json ./curbflow-ai/apps/web/
RUN cd curbflow-ai/apps/web && npm ci

COPY . .

RUN cd curbflow-ai/apps/web && NEXT_PUBLIC_API_BASE_URL=/api npm run build

WORKDIR /app/curbflow-ai

EXPOSE 7860

CMD ["bash", "-lc", "set -euo pipefail; python scripts/seed_demo_db.py --rebuild; python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 & API_PID=$!; cd apps/web; npm run start -- --hostname 0.0.0.0 --port ${PORT:-7860} & WEB_PID=$!; trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT; wait -n $API_PID $WEB_PID"]
