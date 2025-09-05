#!/bin/bash
# OpenCorpInsight DART MCP Server 테스트 실행 스크립트

set -e

echo "🧪 OpenCorpInsight DART MCP Server 테스트 시작"

# 가상환경 활성화 확인
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  가상환경이 활성화되지 않았습니다. 가상환경을 활성화해주세요."
    echo "   source .venv/bin/activate"
    exit 1
fi

# 테스트 디렉터리로 이동
cd "$(dirname "$0")/.."

# 의존성 확인
echo "📦 의존성 확인 중..."
python -c "import pytest, mcp, pandas, requests" || {
    echo "❌ 필수 의존성이 설치되지 않았습니다. requirements.txt를 확인해주세요."
    exit 1
}

# 캐시 디렉터리 생성
mkdir -p cache
mkdir -p logs

# 단위 테스트 실행
echo "🔍 단위 테스트 실행 중..."
python -m pytest tests/test_dart_mcp_server.py::TestDartMCPServer -v --tb=short

# 캐시 매니저 테스트 실행
echo "💾 캐시 매니저 테스트 실행 중..."
python -m pytest tests/test_dart_mcp_server.py::TestCacheManager -v --tb=short

# 통합 테스트 실행 (API 키가 있는 경우)
if [[ -n "$DART_API_KEY" ]]; then
    echo "🔗 통합 테스트 실행 중..."
    python -m pytest tests/test_dart_mcp_server.py::TestIntegration -v --tb=short -m integration
else
    echo "⚠️  DART_API_KEY 환경변수가 설정되지 않아 통합 테스트를 건너뜁니다."
fi

# 테스트 커버리지 리포트 (pytest-cov가 설치된 경우)
if python -c "import pytest_cov" 2>/dev/null; then
    echo "📊 테스트 커버리지 생성 중..."
    python -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing
    echo "📈 커버리지 리포트가 htmlcov/index.html에 생성되었습니다."
fi

echo "✅ 모든 테스트가 완료되었습니다!" 