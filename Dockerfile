FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    poppler-utils \
    libreoffice \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p jobs outputs

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
