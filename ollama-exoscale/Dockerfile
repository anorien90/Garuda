FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 11434

ENV EXOSCALE_API_KEY=""
ENV EXOSCALE_API_SECRET=""
ENV EXOSCALE_ZONE="at-vie-2"
ENV EXOSCALE_INSTANCE_TYPE="a5000.small"
ENV EXOSCALE_TEMPLATE="Linux Ubuntu 22.04 LTS 64-bit"
ENV EXOSCALE_DISK_SIZE="50"
ENV EXOSCALE_IDLE_TIMEOUT="1800"
ENV OLLAMA_MODEL="granite3.1-dense:8b"

CMD ["gunicorn", "--bind", "0.0.0.0:11434", "--workers", "2", "--timeout", "600", "app:app"]
