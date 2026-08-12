# ---------- Build stage: frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Runtime stage: API + SPA ----------
FROM python:3.12-slim
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

# Persist the SQLite database on a volume
RUN mkdir -p /app/data
ENV DATABASE_PATH=/app/data/jobs.db

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
