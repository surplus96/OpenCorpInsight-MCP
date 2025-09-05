#!/bin/bash
# OpenCorpInsight MCP Server 설치 스크립트

set -e

echo "🚀 OpenCorpInsight MCP Server 설치를 시작합니다..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수 정의
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 시스템 요구사항 확인
check_requirements() {
    print_status "시스템 요구사항 확인 중..."
    
    # Python 3.8+ 확인
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3이 설치되지 않았습니다."
        print_status "Python 3.8 이상을 설치해주세요."
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [[ $(echo "$PYTHON_VERSION < 3.8" | bc -l) -eq 1 ]]; then
        print_error "Python 3.8 이상이 필요합니다. 현재 버전: $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION 확인됨"
    
    # pip 확인
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3가 설치되지 않았습니다."
        exit 1
    fi
    
    print_success "pip3 확인됨"
}

# 가상환경 생성
create_venv() {
    print_status "Python 가상환경 생성 중..."
    
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        print_success "가상환경 생성 완료"
    else
        print_warning "가상환경이 이미 존재합니다."
    fi
    
    # 가상환경 활성화
    source .venv/bin/activate
    print_success "가상환경 활성화됨"
}

# 의존성 설치
install_dependencies() {
    print_status "의존성 패키지 설치 중..."
    
    # 기본 의존성 설치
    pip install --upgrade pip
    pip install -r requirements.txt
    
    print_success "의존성 설치 완료"
}

# 캐시 디렉토리 생성
setup_cache() {
    print_status "캐시 디렉토리 설정 중..."
    
    if [ ! -d "cache" ]; then
        mkdir -p cache
        print_success "캐시 디렉토리 생성됨"
    fi
    
    if [ ! -d "logs" ]; then
        mkdir -p logs
        print_success "로그 디렉토리 생성됨"
    fi
}

# 환경변수 파일 생성
setup_env() {
    print_status "환경 설정 파일 생성 중..."
    
    if [ ! -f ".env" ]; then
        cp env.example .env
        print_success ".env 파일 생성됨"
        print_warning "DART_API_KEY를 .env 파일에 설정해주세요."
    else
        print_warning ".env 파일이 이미 존재합니다."
    fi
}

# MCP 설정 검증
verify_mcp() {
    print_status "MCP 서버 설정 검증 중..."
    
    # 기본 import 테스트
    python3 -c "
import sys
sys.path.append('src')
try:
    from dart_mcp_server import app
    print('✅ MCP 서버 모듈 로드 성공')
except Exception as e:
    print(f'❌ MCP 서버 모듈 로드 실패: {e}')
    sys.exit(1)
"
    
    print_success "MCP 서버 검증 완료"
}

# Claude Desktop 설정 가이드
show_claude_setup() {
    print_status "Claude Desktop 연동 설정 가이드"
    echo ""
    echo "다음 설정을 Claude Desktop의 설정 파일에 추가하세요:"
    echo ""
    echo "macOS: ~/Library/Application Support/Claude/claude_desktop_config.json"
    echo "Windows: %APPDATA%/Claude/claude_desktop_config.json"
    echo ""
    echo "{"
    echo "  \"mcpServers\": {"
    echo "    \"opencorpinsight\": {"
    echo "      \"command\": \"python3\","
    echo "      \"args\": [\"-m\", \"src.dart_mcp_server\"],"
    echo "      \"cwd\": \"$(pwd)\","
    echo "      \"env\": {"
    echo "        \"PYTHONPATH\": \"$(pwd)/src\""
    echo "      }"
    echo "    }"
    echo "  }"
    echo "}"
    echo ""
    print_warning "설정 후 Claude Desktop을 재시작해주세요."
}

# 테스트 실행
run_tests() {
    print_status "설치 테스트 실행 중..."
    
    if [ -f "scripts/run_tests.sh" ]; then
        chmod +x scripts/run_tests.sh
        ./scripts/run_tests.sh
        print_success "테스트 완료"
    else
        print_warning "테스트 스크립트를 찾을 수 없습니다."
    fi
}

# 메인 설치 프로세스
main() {
    echo "📦 OpenCorpInsight MCP Server v1.0.0"
    echo "🏢 한국 기업 재무 분석 및 포트폴리오 관리 도구"
    echo ""
    
    check_requirements
    create_venv
    install_dependencies
    setup_cache
    setup_env
    verify_mcp
    
    print_success "🎉 OpenCorpInsight MCP Server 설치가 완료되었습니다!"
    echo ""
    
    show_claude_setup
    
    echo ""
    print_status "다음 단계:"
    echo "1. .env 파일에 DART_API_KEY 설정"
    echo "2. Claude Desktop 설정 파일 업데이트"
    echo "3. Claude Desktop 재시작"
    echo "4. 'python3 -m src.dart_mcp_server'로 서버 테스트"
    echo ""
    print_success "설치가 완료되었습니다! 🚀"
}

# 스크립트 실행
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 