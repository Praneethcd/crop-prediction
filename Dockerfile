FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production HOST=0.0.0.0 PORT=8000 \
    AGRIPREDICT_DATABASE=/data/agripredict.db AGRIPREDICT_INSTANCE_PATH=/data/instance
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 gosu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir 'torch>=2.6,<3' 'torchvision>=0.21,<1' --index-url https://download.pytorch.org/whl/cpu
COPY . .
RUN useradd --create-home appuser && mkdir -p /data/instance && chown -R appuser:appuser /data /app
EXPOSE 8000
CMD ["sh", "deployment/start.sh"]
