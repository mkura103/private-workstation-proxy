# Cloud Run Proxy Server for Cloud Workstations (Python版)
FROM python:3.11-slim

WORKDIR /app

# 依存関係インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコピー
COPY proxy.py .

# 環境変数デフォルト
ENV WORKSTATION_HOST=workstation.cluster.cloudworkstations.dev
ENV PORT=8080

# Cloud Runはポート8080を使用
EXPOSE 8080

# 起動
CMD ["python", "proxy.py"]
