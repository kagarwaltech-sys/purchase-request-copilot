FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["python", "-m", "copilot", "serve", "--host", "0.0.0.0", "--port", "8000", "--db", "/data/purchase-request.sqlite3"]
