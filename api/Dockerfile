FROM python:3.12-slim

WORKDIR /app

# 의존성 설치 (레이어 캐시 활용)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# 소스 복사
COPY . .

# DB 디렉토리 (볼륨 마운트 시 override)
ENV DIPEEN_DB_PATH=/data/dipeen.db
VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
