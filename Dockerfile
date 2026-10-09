FROM node:24-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/dist/frontend/browser ./static
ENV STATIC_DIR=/app/static
EXPOSE 8080
# Rebuild the database from backend/seed/ on every start, then serve.
# Threads + a long timeout: flashcard generation waits up to 90 s for the LLM,
# and must neither be killed nor block other requests while it waits.
CMD ["sh", "-c", "flask --app studyapp reset-db && exec gunicorn -b 0.0.0.0:8080 -w 2 --worker-class gthread --threads 8 --timeout 120 'studyapp:create_app()'"]
