# OpenCorpInsight DART MCP Server

**OpenCorpInsight**는 금융감독원 전자공시시스템(DART) API를 활용하여 기업의 재무정보를 분석하는 MCP(Model Context Protocol) 서버입니다.

## 🎯 주요 기능

### Phase 1 (완료) ✅
- **기업 정보 조회**: 회사명으로 기업의 기본 정보 조회
- **재무제표 조회**: 현금흐름표, 손익계산서, 재무상태표 등 조회
- **재무비율 계산**: ROE, ROA, 부채비율 등 주요 재무비율 자동 계산
- **기업간 비교**: 여러 기업의 재무지표 비교 분석
- **공시 목록 조회**: 특정 기간의 공시 보고서 목록 조회
- **캐싱 시스템**: SQLite 기반 지능형 캐싱으로 성능 최적화

### Phase 2 (완료) ✅
- **재무 건전성 분석**: AI 기반 종합 재무 건전성 평가 (수익성, 안정성, 성장성, 활동성)
- **뉴스 수집 및 분석**: Perplexity MCP 연동을 통한 기업 관련 뉴스 수집
- **감성 분석**: 뉴스 기사의 감성 분석 및 투자 영향도 평가
- **이벤트 탐지**: 주요 재무 이벤트 자동 탐지 (실적발표, 배당, M&A 등)
- **고급 캐싱**: Phase 2 데이터에 최적화된 캐시 정책 적용

### Phase 3 (완료) ✅
- **투자 신호 생성**: 종합 분석 기반 Buy/Hold/Sell 투자 신호 생성
- **종합 리포트 생성**: 전문적인 기업 분석 리포트 자동 생성
- **PDF 내보내기**: 분석 결과를 PDF 형태로 내보내기
- **고급 분석**: 리스크 허용도 기반 맞춤형 투자 분석

### Phase 4 (완료) ✅
- **포트폴리오 최적화**: 다중 기업 포트폴리오 최적화 및 리밸런싱 제안
- **시계열 분석**: 기업 성과의 시계열 트렌드 분석 및 미래 예측
- **벤치마크 비교**: 업계 평균과의 상세 비교 분석 및 순위 평가
- **경쟁 분석**: 경쟁사 대비 포지션 분석 및 SWOT 분석
- **업계 리포트**: 특정 업계의 종합 분석 리포트 생성

## 🚀 빠른 시작

### 자동 설치 (권장)

```bash
# 저장소 클론
git clone https://github.com/your-username/OpenCorpInsight.git
cd OpenCorpInsight

# 자동 설치 스크립트 실행
chmod +x scripts/install.sh
./scripts/install.sh
```

### 수동 설치

```bash
# 1. Python 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp env.example .env
# .env 파일에 DART_API_KEY 설정

# 4. 캐시 디렉토리 생성
mkdir -p cache logs
```

### Claude Desktop 연동

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "opencorpinsight": {
      "command": "python3",
      "args": ["-m", "src.dart_mcp_server"],
      "cwd": "/path/to/OpenCorpInsight",
      "env": {
        "PYTHONPATH": "/path/to/OpenCorpInsight/src"
      }
    }
  }
}
```

### Docker 실행

```bash
# Docker 이미지 빌드
docker build -t opencorpinsight .

# 컨테이너 실행
docker run -d --name opencorpinsight \
  -e DART_API_KEY=your_api_key \
  -v $(pwd)/cache:/app/cache \
  opencorpinsight
```

### 서버 실행

```bash
# 직접 실행
python3 -m src.dart_mcp_server

# 또는 스크립트 사용
./scripts/start_server.sh
```

## 🔧 사용법

### Claude Desktop 연동

`mcp_config.json`을 Claude Desktop 설정에 추가:

```json
{
  "mcpServers": {
    "dart-mcp-server": {
      "command": "python",
      "args": ["/path/to/OpenCorpInsight/src/dart_mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/OpenCorpInsight/.venv/lib/python3.13/site-packages"
      }
    }
  }
}
```

## 📖 MCP 도구 사용 예시

### Phase 1: 기본 재무 분석

#### 1. API 키 설정
```json
{
  "tool": "set_dart_api_key",
  "arguments": {
    "api_key": "your_dart_api_key_here"
  }
}
```

#### 2. 기업 정보 조회
```json
{
  "tool": "get_company_info", 
  "arguments": {
    "corp_name": "삼성전자"
  }
}
```

#### 3. 재무제표 조회
```json
{
  "tool": "get_financial_statements",
  "arguments": {
    "corp_name": "삼성전자",
    "year": "2023",
    "reprt_code": "11014",
    "fs_div": "CFS", 
    "statement_type": "현금흐름표"
  }
}
```

#### 4. 재무비율 계산
```json
{
  "tool": "get_financial_ratios",
  "arguments": {
    "corp_name": "삼성전자",
    "year": "2023"
  }
}
```

#### 5. 기업간 비교 분석
```json
{
  "tool": "compare_financials",
  "arguments": {
    "corp_names": ["삼성전자", "SK하이닉스", "LG전자"],
    "year": "2023",
    "metrics": ["ROE", "ROA", "부채비율", "영업이익률"]
  }
}
```

### Phase 2: 고급 분석 및 뉴스

#### 6. 재무 건전성 종합 분석
```json
{
  "tool": "analyze_company_health",
  "arguments": {
    "corp_name": "삼성전자",
    "analysis_period": 3,
    "weight_config": {
      "profitability": 0.3,
      "stability": 0.3,
      "growth": 0.2,
      "activity": 0.2
    }
  }
}
```

#### 7. 기업 뉴스 수집 및 분석 (Perplexity 연동)
```json
{
  "tool": "get_company_news",
  "arguments": {
    "corp_name": "삼성전자",
    "search_period": "week",
    "news_categories": ["earnings", "business", "technology"],
    "include_sentiment": true
  }
}
```

#### 8. 뉴스 감성 분석
```json
{
  "tool": "analyze_news_sentiment",
  "arguments": {
    "corp_name": "삼성전자",
    "search_period": "week",
    "analysis_depth": "detailed"
  }
}
```

#### 9. 재무 이벤트 탐지
```json
{
  "tool": "detect_financial_events",
  "arguments": {
    "corp_name": "삼성전자",
    "monitoring_period": 30,
    "event_types": ["earnings", "dividend", "capital_increase", "major_contract"]
  }
}
```

### Phase 3: 투자 신호 및 리포트

#### 10. 투자 신호 생성
```json
{
  "tool": "generate_investment_signal",
  "arguments": {
    "corp_name": "삼성전자",
    "analysis_period": 3,
    "weight_config": {
      "financial_health": 0.4,
      "news_sentiment": 0.3,
      "event_impact": 0.2,
      "market_trend": 0.1
    },
    "risk_tolerance": "moderate"
  }
}
```

#### 11. 종합 분석 리포트 생성
```json
{
  "tool": "generate_summary_report",
  "arguments": {
    "corp_name": "삼성전자",
    "report_type": "comprehensive",
    "include_charts": false,
    "analysis_depth": "detailed"
  }
}
```

#### 12. PDF 내보내기
```json
{
  "tool": "export_to_pdf",
  "arguments": {
    "corp_name": "삼성전자",
    "report_content": "# 삼성전자 분석 리포트\n\n...",
    "include_metadata": true,
    "page_format": "A4"
  }
}
```

### Phase 4: 포트폴리오 분석 및 벤치마킹

#### 13. 포트폴리오 최적화
```json
{
  "tool": "optimize_portfolio",
  "arguments": {
    "companies": ["삼성전자", "LG전자", "SK하이닉스"],
    "investment_amount": 100000000,
    "risk_tolerance": "moderate",
    "optimization_method": "sharpe"
  }
}
```

#### 14. 시계열 분석
```json
{
  "tool": "analyze_time_series",
  "arguments": {
    "corp_name": "삼성전자",
    "analysis_period": 5,
    "metrics": ["매출액", "영업이익", "순이익"],
    "forecast_periods": 8
  }
}
```

#### 15. 업계 벤치마크 비교
```json
{
  "tool": "compare_with_industry",
  "arguments": {
    "corp_name": "삼성전자",
    "industry": "반도체",
    "comparison_metrics": ["ROE", "ROA", "부채비율"],
    "analysis_type": "detailed"
  }
}
```

#### 16. 경쟁 포지션 분석
```json
{
  "tool": "analyze_competitive_position",
  "arguments": {
    "corp_name": "삼성전자",
    "competitors": ["SK하이닉스", "LG전자"],
    "analysis_metrics": ["ROE", "ROA", "매출액증가율"],
    "include_swot": true
  }
}
```

#### 17. 업계 분석 리포트
```json
{
  "tool": "generate_industry_report",
  "arguments": {
    "industry": "반도체",
    "report_type": "comprehensive",
    "include_rankings": true
  }
}
```

## 🧪 테스트

### 자동 테스트 실행

```bash
# 테스트 스크립트 실행
./scripts/run_tests.sh

# 또는 수동으로 pytest 실행
python -m pytest tests/ -v
```

### 테스트 커버리지

```bash
# 커버리지 포함 테스트
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=html
```

## 📦 배포

### Docker 배포

```bash
# 이미지 빌드
docker build -t opencorpinsight-mcp .

# 컨테이너 실행
docker run -e DART_API_KEY=your_api_key opencorpinsight-mcp
```

### Docker Compose 배포

```bash
# 환경변수 설정 후
docker-compose up -d

# Redis 캐시 포함 배포
docker-compose --profile redis up -d
```

## 🏗️ 아키텍처

```
┌─────────────────┐
│   AI Agent      │ ← Claude, GPT 등
├─────────────────┤
│   MCP Client    │ ← MCP 프로토콜
├─────────────────┤
│   MCP Tools     │ ← 5개 카테고리 도구
├─────────────────┤
│  Cache Layer    │ ← SQLite 캐싱
├─────────────────┤
│  DART API       │ ← 금융감독원 API
└─────────────────┘
```

### 도구 카테고리

- **Company Tools**: 기업 기본 정보
- **Financial Tools**: 재무 데이터 및 비율
- **Analysis Tools**: AI 기반 분석 (Phase 2)
- **News Tools**: 뉴스 수집 및 감성 분석 (Phase 2)
- **Report Tools**: 보고서 생성 (Phase 3)

### 🚄 성능 최적화

**OpenCorpInsight**는 SQLite 기반 지능형 캐싱 시스템으로 최적화되어 있습니다:

#### Phase 1 캐시 정책
- **기업 정보**: 24시간 TTL, 최대 1,000개
- **재무제표**: 24시간 TTL, 최대 5,000개  
- **재무비율**: 12시간 TTL, 최대 2,000개
- **공시 목록**: 6시간 TTL, 최대 3,000개

#### Phase 2 캐시 정책
- **기업 뉴스**: 2시간 TTL, 최대 1,000개 (실시간성 중요)
- **감성 분석**: 4시간 TTL, 최대 800개
- **재무 이벤트**: 6시간 TTL, 최대 500개
- **기업 건전성**: 12시간 TTL, 최대 300개

#### Phase 3 캐시 정책
- **투자 신호**: 8시간 TTL, 최대 200개
- **종합 리포트**: 24시간 TTL, 최대 100개
- **PDF 내보내기**: 72시간 TTL, 최대 50개

#### Phase 4 캐시 정책
- **포트폴리오 최적화**: 12시간 TTL, 최대 150개
- **시계열 분석**: 24시간 TTL, 최대 200개
- **성과 예측**: 48시간 TTL, 최대 100개
- **업계 벤치마크**: 24시간 TTL, 최대 300개
- **경쟁 분석**: 12시간 TTL, 최대 200개
- **업계 리포트**: 72시간 TTL, 최대 50개

## 🔐 보안

- **API 키 보호**: 환경변수 기반 키 관리
- **데이터 프라이버시**: 공개 정보만 수집
- **로그 관리**: 민감 정보 로깅 방지

## 📝 개발 가이드

### 새로운 도구 추가

1. `src/dart_mcp_server.py`에 도구 정의 추가
2. `handle_call_tool()`에 핸들러 추가
3. 구현 함수 작성
4. `tests/` 디렉터리에 테스트 추가

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

**OpenCorpInsight**로 기업 분석을 더 쉽고 정확하게! 🚀 

## ⚙️ 환경 설정

### 1. API 키 설정

#### DART API 키 (필수)
1. [DART 홈페이지](https://opendart.fss.or.kr)에서 회원가입
2. API 신청 후 승인 (보통 1-2일 소요)
3. 발급받은 40자리 API 키를 환경변수로 설정:

```bash
export DART_API_KEY="your_40_character_api_key_here"
```

또는 `.env` 파일 생성:
```env
DART_API_KEY=your_40_character_api_key_here
```
