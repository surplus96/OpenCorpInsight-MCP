#!/bin/bash
# OpenCorpInsight MCP Server 실행 스크립트

set -e

# 색상 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 현재 디렉토리 확인
if [ ! -f "src/dart_mcp_server.py" ]; then
    echo "❌ OpenCorpInsight 프로젝트 디렉토리에서 실행해주세요."
    exit 1
fi

# 가상환경 활성화
if [ ! -d ".venv" ]; then
    echo "❌ 가상환경이 없습니다. scripts/install.sh를 먼저 실행해주세요."
    exit 1
fi

print_status "가상환경 활성화 중..."
source .venv/bin/activate
print_success "가상환경 활성화됨"

# 환경변수 로드
if [ -f ".env" ]; then
    print_status "환경변수 로드 중..."
    export $(cat .env | grep -v '^#' | xargs)
    print_success "환경변수 로드됨"
else
    print_warning ".env 파일이 없습니다. 기본 설정으로 실행합니다."
fi

# 캐시 디렉토리 확인
if [ ! -d "cache" ]; then
    mkdir -p cache
    print_status "캐시 디렉토리 생성됨"
fi

if [ ! -d "logs" ]; then
    mkdir -p logs
    print_status "로그 디렉토리 생성됨"
fi

print_status "OpenCorpInsight MCP Server 시작 중..."
echo ""
echo "🚀 OpenCorpInsight MCP Server"
echo "📊 한국 기업 재무 분석 및 포트폴리오 관리"
echo "🔗 MCP 프로토콜로 Claude Desktop과 연동"
echo ""
print_status "서버가 실행 중입니다. 종료하려면 Ctrl+C를 누르세요."
echo ""

# MCP 서버 실행
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
python3 -m src.dart_mcp_server 