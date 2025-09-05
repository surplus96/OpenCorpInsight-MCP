# OpenCorpInsight MCP 도구 상세 명세서

## 도구 분류 체계

### 네이밍 컨벤션
- **접두사**: 기능별 카테고리 구분
  - `company_`: 기업 기본 정보
  - `financial_`: 재무 데이터
  - `analysis_`: 분석 및 계산
  - `news_`: 뉴스 및 미디어
  - `report_`: 보고서 생성
- **동사**: 명확한 액션 표현 (`get`, `analyze`, `compare`, `generate` 등)

---

## Phase 1: 기본 재무 도구

### 1. `company_get_info`

```json
{
  "name": "company_get_info",
  "description": "기업의 기본 정보를 조회합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "identifier": {
        "type": "string",
        "description": "회사명 또는 종목코드"
      },
      "identifier_type": {
        "type": "string",
        "enum": ["name", "code"],
        "default": "name",
        "description": "식별자 타입"
      }
    },
    "required": ["identifier"]
  }
}
```

**출력 예시:**
```json
{
  "corp_code": "00126380",
  "corp_name": "삼성전자",
  "stock_code": "005930",
  "ceo_name": "이재용",
  "corp_cls": "Y",
  "est_dt": "19690113",
  "list_dt": "19751211",
  "industry": "반도체",
  "address": "경기도 수원시...",
  "homepage": "https://www.samsung.com"
}
```

### 2. `financial_get_statements`

```json
{
  "name": "financial_get_statements",
  "description": "기업의 재무제표를 조회합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "bsns_year": {"type": "string"},
      "reprt_code": {
        "type": "string",
        "enum": ["11011", "11012", "11013", "11014"],
        "default": "11014"
      },
      "fs_div": {
        "type": "string", 
        "enum": ["CFS", "OFS"],
        "default": "CFS"
      },
      "statement_type": {
        "type": "string",
        "enum": ["재무상태표", "손익계산서", "현금흐름표", "자본변동표"],
        "default": "현금흐름표"
      }
    },
    "required": ["corp_name", "bsns_year"]
  }
}
```

### 3. `financial_get_ratios`

```json
{
  "name": "financial_get_ratios",
  "description": "주요 재무비율을 계산하고 조회합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "bsns_year": {"type": "string"},
      "ratio_categories": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["profitability", "stability", "activity", "growth"]
        },
        "default": ["profitability", "stability"]
      },
      "include_industry_avg": {
        "type": "boolean",
        "default": true
      }
    },
    "required": ["corp_name", "bsns_year"]
  }
}
```

**계산 지표:**
- **수익성**: ROE, ROA, 영업이익률, 순이익률
- **안정성**: 부채비율, 유동비율, 당좌비율, 이자보상배수
- **활동성**: 총자산회전율, 재고자산회전율, 매출채권회전율
- **성장성**: 매출액증가율, 영업이익증가율, 순이익증가율

### 4. `financial_compare_companies`

```json
{
  "name": "financial_compare_companies",
  "description": "여러 기업의 재무지표를 비교합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "companies": {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 2,
        "maxItems": 5
      },
      "bsns_year": {"type": "string"},
      "comparison_metrics": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["revenue", "operating_profit", "net_profit", "roe", "debt_ratio"]
      },
      "visualization": {
        "type": "boolean",
        "default": true
      }
    },
    "required": ["companies", "bsns_year"]
  }
}
```

---

## Phase 2: 분석 및 뉴스 도구

### 5. `analysis_company_health`

```json
{
  "name": "analysis_company_health",
  "description": "기업의 재무 건전성을 종합 분석합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "analysis_period": {
        "type": "integer",
        "default": 3,
        "description": "분석 기간 (년)"
      },
      "weight_config": {
        "type": "object",
        "properties": {
          "profitability": {"type": "number", "default": 0.3},
          "stability": {"type": "number", "default": 0.3},
          "growth": {"type": "number", "default": 0.2},
          "activity": {"type": "number", "default": 0.2}
        }
      }
    },
    "required": ["corp_name"]
  }
}
```

**출력 구조:**
```json
{
  "overall_score": 75.2,
  "grade": "B+",
  "category_scores": {
    "profitability": {"score": 78, "trend": "improving"},
    "stability": {"score": 82, "trend": "stable"},
    "growth": {"score": 65, "trend": "declining"},
    "activity": {"score": 73, "trend": "stable"}
  },
  "key_strengths": ["높은 수익성", "안정적 재무구조"],
  "concerns": ["성장률 둔화", "매출채권 증가"],
  "recommendation": "HOLD",
  "ai_commentary": "GPT 기반 정성적 분석..."
}
```

### 6. `news_get_company_news`

```json
{
  "name": "news_get_company_news",
  "description": "기업 관련 뉴스를 수집합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "date_range": {
        "type": "object",
        "properties": {
          "start_date": {"type": "string", "format": "date"},
          "end_date": {"type": "string", "format": "date"}
        }
      },
      "sources": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["naver", "daum", "hankyung"]
      },
      "keywords": {
        "type": "array",
        "items": {"type": "string"},
        "description": "추가 필터링 키워드"
      },
      "max_articles": {
        "type": "integer",
        "default": 50,
        "maximum": 200
      }
    },
    "required": ["corp_name"]
  }
}
```

### 7. `news_analyze_sentiment`

```json
{
  "name": "news_analyze_sentiment",
  "description": "뉴스 기사의 감성을 분석합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "date_range": {
        "type": "object",
        "properties": {
          "start_date": {"type": "string"},
          "end_date": {"type": "string"}
        }
      },
      "analysis_method": {
        "type": "string",
        "enum": ["kobert", "openai", "hybrid"],
        "default": "hybrid"
      }
    },
    "required": ["corp_name"]
  }
}
```

**출력 구조:**
```json
{
  "sentiment_summary": {
    "positive": 0.45,
    "neutral": 0.35,
    "negative": 0.20
  },
  "sentiment_trend": "improving",
  "key_topics": {
    "positive": ["신제품 출시", "실적 개선"],
    "negative": ["규제 이슈", "경쟁 심화"]
  },
  "impact_score": 7.2,
  "articles_analyzed": 127
}
```

---

## Phase 3: 고급 분석 및 보고서

### 8. `analysis_investment_signal`

```json
{
  "name": "analysis_investment_signal",
  "description": "종합적인 투자 신호를 생성합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "signal_type": {
        "type": "string",
        "enum": ["conservative", "moderate", "aggressive"],
        "default": "moderate"
      },
      "factors": {
        "type": "object",
        "properties": {
          "financial_weight": {"type": "number", "default": 0.4},
          "news_weight": {"type": "number", "default": 0.3},
          "technical_weight": {"type": "number", "default": 0.3}
        }
      }
    },
    "required": ["corp_name"]
  }
}
```

### 9. `report_generate_summary`

```json
{
  "name": "report_generate_summary",
  "description": "기업 분석 요약 보고서를 생성합니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "corp_name": {"type": "string"},
      "report_type": {
        "type": "string",
        "enum": ["executive", "detailed", "investor"],
        "default": "detailed"
      },
      "include_sections": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["company_overview", "financial_analysis", "news_summary", "investment_opinion", "risk_factors"]
        },
        "default": ["company_overview", "financial_analysis", "investment_opinion"]
      },
      "format": {
        "type": "string",
        "enum": ["markdown", "html", "json"],
        "default": "markdown"
      }
    },
    "required": ["corp_name"]
  }
}
```

### 10. `report_export_pdf`

```json
{
  "name": "report_export_pdf",
  "description": "분석 보고서를 PDF로 내보냅니다",
  "inputSchema": {
    "type": "object",
    "properties": {
      "report_data": {"type": "object"},
      "template": {
        "type": "string",
        "enum": ["corporate", "investment", "research"],
        "default": "corporate"
      },
      "branding": {
        "type": "object",
        "properties": {
          "logo_url": {"type": "string"},
          "primary_color": {"type": "string"},
          "company_name": {"type": "string"}
        }
      },
      "output_path": {"type": "string"}
    },
    "required": ["report_data"]
  }
}
```

---

## 공통 응답 구조

모든 MCP 도구는 다음과 같은 표준화된 응답 구조를 따릅니다:

```json
{
  "status": "success|error",
  "data": {}, 
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "source": "dart_api",
    "cache_hit": true,
    "execution_time_ms": 1250
  },
  "error": {
    "code": "COMPANY_NOT_FOUND",
    "message": "지정된 회사를 찾을 수 없습니다",
    "details": {}
  }
}
```

## 오류 코드 체계

| 코드 | 설명 | 대응 방안 |
|------|------|----------|
| `API_KEY_INVALID` | API 키가 유효하지 않음 | 새 API 키 설정 필요 |
| `COMPANY_NOT_FOUND` | 회사를 찾을 수 없음 | 회사명 또는 종목코드 확인 |
| `DATA_NOT_AVAILABLE` | 요청한 데이터가 없음 | 다른 기간이나 보고서 타입 시도 |
| `RATE_LIMIT_EXCEEDED` | API 호출 한도 초과 | 잠시 후 재시도 |
| `NETWORK_ERROR` | 네트워크 연결 오류 | 연결 상태 확인 후 재시도 |

이 명세서를 바탕으로 각 도구의 구현을 진행하면 일관성 있고 확장 가능한 MCP 시스템을 구축할 수 있습니다. 