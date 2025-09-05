# OpenCorpInsight MCP Server Dockerfile
FROM python:3.11-slim

# 메타데이터
LABEL maintainer="OpenCorpInsight Team"
LABEL description="한국 기업 재무 분석 및 포트폴리오 관리 MCP 서버"
LABEL version="1.0.0"

# 시스템 패키지 업데이트 및 필요한 도구 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 의존성 먼저 복사 및 설치 (Docker 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY src/ ./src/
COPY cache/ ./cache/
COPY logs/ ./logs/
COPY scripts/ ./scripts/
COPY mcp_config.json .
COPY env.example .env

# 권한 설정
RUN chmod +x scripts/*.sh

# 캐시 및 로그 디렉토리 생성
RUN mkdir -p cache logs

# 환경변수 설정
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# 포트 노출 (MCP는 stdio를 사용하지만 향후 HTTP 지원을 위해)
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.path.append('src'); from dart_mcp_server import app; print('OK')" || exit 1

# MCP 서버 실행
CMD ["python3", "-m", "src.dart_mcp_server"] 