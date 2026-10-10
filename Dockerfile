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
# The Angular build writes straight into dist/, not dist/<project>/browser/.
COPY --from=frontend /app/dist ./static
ENV STATIC_DIR=/app/static \
    DATA_DIR=/app/data
EXPOSE 8080
# One worker: the PDF job pool and its in-flight set live in the process.
CMD ["sh", "-c", "flask --app app reset-db && exec gunicorn -b 0.0.0.0:8080 -w 1 --threads 8 'app:create_app()'"]
