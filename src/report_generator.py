#!/usr/bin/env python3
"""
Report Generator for OpenCorpInsight
종합 기업 분석 리포트 생성
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
import io
import base64

# PDF 생성 관련
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger = logging.getLogger("report-generator")
    logger.warning("PDF 라이브러리가 설치되지 않음. PDF 기능이 제한됩니다.")

# 차트 생성 관련
try:
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    CHART_AVAILABLE = True
except ImportError:
    CHART_AVAILABLE = False

logger = logging.getLogger("report-generator")

class ReportGenerator:
    """종합 기업 분석 리포트 생성기"""
    
    def __init__(self):
        self.report_templates = {
            'executive_summary': self._generate_executive_summary,
            'financial_analysis': self._generate_financial_analysis,
            'news_analysis': self._generate_news_analysis,
            'investment_signal': self._generate_investment_signal_section,
            'risk_analysis': self._generate_risk_analysis,
            'appendix': self._generate_appendix
        }
    
    async def generate_comprehensive_report(self, corp_name: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """종합 분석 리포트 생성"""
        try:
            report_sections = {}
            
            # 각 섹션별 리포트 생성
            for section_name, generator_func in self.report_templates.items():
                try:
                    section_content = await generator_func(corp_name, analysis_data)
                    report_sections[section_name] = section_content
                except Exception as e:
                    logger.error(f"섹션 '{section_name}' 생성 실패: {e}")
                    report_sections[section_name] = f"섹션 생성 중 오류 발생: {str(e)}"
            
            # 전체 리포트 조합
            full_report = self._combine_report_sections(corp_name, report_sections)
            
            # 메타데이터 추가
            report_metadata = {
                'company': corp_name,
                'generated_at': datetime.now().isoformat(),
                'report_type': 'comprehensive_analysis',
                'sections': list(report_sections.keys()),
                'data_sources': self._extract_data_sources(analysis_data),
                'report_length': len(full_report),
                'version': '1.0'
            }
            
            return {
                'report_content': full_report,
                'metadata': report_metadata,
                'sections': report_sections,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"종합 리포트 생성 실패: {e}")
            return {
                'report_content': f"리포트 생성 중 오류 발생: {str(e)}",
                'metadata': {'error': str(e), 'company': corp_name},
                'sections': {},
                'success': False
            }
    
    async def _generate_executive_summary(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """경영진 요약 섹션"""
        health_data = analysis_data.get('company_health', {})
        investment_signal = analysis_data.get('investment_signal', {})
        
        summary = f"""# 📋 경영진 요약 (Executive Summary)

## 🏢 기업 개요
- **기업명**: {corp_name}
- **분석일**: {datetime.now().strftime('%Y년 %m월 %d일')}
- **종합 평가**: {health_data.get('health_grade', 'N/A')}

## 🎯 핵심 결과
- **재무 건전성**: {health_data.get('overall_score', 0):.1f}/100점
- **투자 신호**: {investment_signal.get('signal', 'N/A')} ({investment_signal.get('confidence', 0):.1f}% 신뢰도)
- **투자 추천도**: {health_data.get('investment_recommendation', 'N/A')}

## ⚡ 주요 강점
{self._format_list_items(health_data.get('strengths', ['데이터 부족']))}

## ⚠️ 주요 위험요인
{self._format_list_items(health_data.get('weaknesses', ['데이터 부족']))}

## 💡 투자 의견
{investment_signal.get('recommendation_summary', '추가 분석이 필요합니다.')}

---
"""
        return summary
    
    async def _generate_financial_analysis(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """재무 분석 섹션"""
        health_data = analysis_data.get('company_health', {})
        ratios_data = analysis_data.get('financial_ratios', {})
        
        analysis = f"""# 💰 재무 분석 (Financial Analysis)

## 📊 재무 건전성 종합 평가
- **종합 점수**: {health_data.get('overall_score', 0):.1f}/100점
- **건전성 등급**: {health_data.get('health_grade', 'N/A')}
- **리스크 수준**: {health_data.get('risk_level', 'N/A')}

## 🎯 영역별 분석

### 💰 수익성 분석
- **점수**: {health_data.get('profitability', {}).get('score', 0):.1f}/100점
- **평가**: {health_data.get('profitability', {}).get('assessment', 'N/A')}
- **세부 내용**:
{health_data.get('profitability', {}).get('details', '- 데이터 부족')}

### 🏛️ 안정성 분석  
- **점수**: {health_data.get('stability', {}).get('score', 0):.1f}/100점
- **평가**: {health_data.get('stability', {}).get('assessment', 'N/A')}
- **세부 내용**:
{health_data.get('stability', {}).get('details', '- 데이터 부족')}

### 📈 성장성 분석
- **점수**: {health_data.get('growth', {}).get('score', 0):.1f}/100점
- **평가**: {health_data.get('growth', {}).get('assessment', 'N/A')}
- **세부 내용**:
{health_data.get('growth', {}).get('details', '- 데이터 부족')}

### ⚡ 활동성 분석
- **점수**: {health_data.get('activity', {}).get('score', 0):.1f}/100점
- **평가**: {health_data.get('activity', {}).get('assessment', 'N/A')}
- **세부 내용**:
{health_data.get('activity', {}).get('details', '- 데이터 부족')}

## 📋 주요 재무비율
{self._format_financial_ratios(ratios_data)}

---
"""
        return analysis
    
    async def _generate_news_analysis(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """뉴스 분석 섹션"""
        sentiment_data = analysis_data.get('news_sentiment', {})
        events_data = analysis_data.get('financial_events', {})
        
        analysis = f"""# 📰 뉴스 및 시장 분석 (News & Market Analysis)

## 💭 뉴스 감성 분석
- **분석 기간**: {sentiment_data.get('analysis_period', 'N/A')}
- **분석 기사 수**: {sentiment_data.get('total_articles_analyzed', 0)}개
- **평균 감성 점수**: {sentiment_data.get('average_sentiment_score', 0):.3f}
- **투자 영향도**: {sentiment_data.get('investment_impact', 'N/A')}

### 📊 감성 분포
{self._format_sentiment_distribution(sentiment_data.get('sentiment_distribution', {}))}

## 🎯 주요 재무 이벤트
- **모니터링 기간**: {events_data.get('monitoring_period_days', 0)}일
- **탐지된 이벤트**: {events_data.get('total_events_detected', 0)}개
- **이벤트 유형**: {', '.join(events_data.get('event_types_found', []))}

### 📋 이벤트 상세
{self._format_financial_events(events_data.get('event_summary', {}))}

## 🔍 시장 트렌드 분석
{self._generate_market_trend_analysis(sentiment_data, events_data)}

---
"""
        return analysis
    
    async def _generate_investment_signal_section(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """투자 신호 섹션"""
        signal_data = analysis_data.get('investment_signal', {})
        
        section = f"""# 🎯 투자 신호 분석 (Investment Signal Analysis)

## 📊 종합 투자 신호
- **신호**: {signal_data.get('signal', 'N/A')}
- **신호 점수**: {signal_data.get('signal_score', 0):.1f}/100점
- **신뢰도**: {signal_data.get('confidence', 0):.1f}%
- **생성 시점**: {signal_data.get('generated_at', 'N/A')}

## 🎯 신호 구성 요소

### 💰 재무 건전성 기여도 (40%)
- **점수**: {signal_data.get('components', {}).get('financial_health', 0):.1f}점
- **가중 점수**: {signal_data.get('components', {}).get('financial_weighted', 0):.1f}점

### 📰 뉴스 감성 기여도 (30%)  
- **점수**: {signal_data.get('components', {}).get('news_sentiment', 0):.1f}점
- **가중 점수**: {signal_data.get('components', {}).get('sentiment_weighted', 0):.1f}점

### 🎯 이벤트 영향 기여도 (20%)
- **점수**: {signal_data.get('components', {}).get('event_impact', 0):.1f}점
- **가중 점수**: {signal_data.get('components', {}).get('event_weighted', 0):.1f}점

### 📈 시장 트렌드 기여도 (10%)
- **점수**: {signal_data.get('components', {}).get('market_trend', 0):.1f}점
- **가중 점수**: {signal_data.get('components', {}).get('trend_weighted', 0):.1f}점

## 💡 투자 권고사항
{signal_data.get('recommendation_summary', '추가 분석이 필요합니다.')}

## ⚠️ 주요 리스크 요인
{self._format_list_items(signal_data.get('risk_factors', ['일반적인 시장 리스크']))}

---
"""
        return section
    
    async def _generate_risk_analysis(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """리스크 분석 섹션"""
        health_data = analysis_data.get('company_health', {})
        signal_data = analysis_data.get('investment_signal', {})
        
        analysis = f"""# ⚠️ 리스크 분석 (Risk Analysis)

## 🎯 주요 리스크 요인
{self._format_list_items(health_data.get('key_concerns', ['일반적인 리스크']))}

## 📊 리스크 수준 평가
- **전체 리스크 수준**: {health_data.get('risk_level', 'N/A')}
- **재무 리스크**: {self._assess_financial_risk(health_data)}
- **시장 리스크**: {self._assess_market_risk(analysis_data)}
- **운영 리스크**: {self._assess_operational_risk(analysis_data)}

## 🛡️ 리스크 완화 방안
{self._generate_risk_mitigation_suggestions(analysis_data)}

## 📈 모니터링 권장사항
- 주요 재무지표 정기 모니터링
- 뉴스 및 공시 정보 지속 추적
- 시장 환경 변화 대응 전략 수립
- 분기별 투자 신호 재평가

---
"""
        return analysis
    
    async def _generate_appendix(self, corp_name: str, analysis_data: Dict[str, Any]) -> str:
        """부록 섹션"""
        appendix = f"""# 📚 부록 (Appendix)

## 📊 데이터 출처
{self._format_data_sources(analysis_data)}

## 🔍 분석 방법론
### 재무 건전성 분석
- 수익성, 안정성, 성장성, 활동성 4개 영역 종합 평가
- 각 영역별 가중치 적용 (사용자 설정 가능)
- 100점 만점 기준 점수화

### 뉴스 감성 분석
- 키워드 기반 감성 분석 알고리즘
- 긍정/부정/중립 3단계 분류
- 투자 영향도 평가 모델

### 투자 신호 생성
- 다중 요소 종합 평가 모델
- 신뢰도 기반 신호 강도 조정
- 5단계 투자 신호 (Strong Buy ~ Sell)

## 📋 면책 조항
본 분석 리포트는 정보 제공 목적으로 작성되었으며, 투자 권유나 매매 추천을 위한 것이 아닙니다. 
투자 결정은 개인의 판단과 책임 하에 이루어져야 하며, 본 리포트의 내용에 따른 투자 손실에 대해서는 책임지지 않습니다.

## 📞 문의사항
OpenCorpInsight 개발팀
- GitHub: https://github.com/your-repo/OpenCorpInsight
- 생성 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
"""
        return appendix
    
    def _combine_report_sections(self, corp_name: str, sections: Dict[str, str]) -> str:
        """리포트 섹션들을 하나로 결합"""
        header = f"""# 📊 {corp_name} 종합 기업 분석 리포트

**OpenCorpInsight** 기업 분석 시스템
생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}

---

"""
        
        # 섹션 순서 정의
        section_order = [
            'executive_summary',
            'financial_analysis', 
            'news_analysis',
            'investment_signal',
            'risk_analysis',
            'appendix'
        ]
        
        combined_report = header
        for section_name in section_order:
            if section_name in sections:
                combined_report += sections[section_name] + "\n\n"
        
        return combined_report
    
    def _format_list_items(self, items: List[str]) -> str:
        """리스트 아이템을 마크다운 형식으로 포맷"""
        if not items:
            return "- 해당 없음"
        return "\n".join(f"- {item}" for item in items)
    
    def _format_financial_ratios(self, ratios_data: Dict[str, Any]) -> str:
        """재무비율 데이터 포맷팅"""
        if not ratios_data:
            return "- 재무비율 데이터 없음"
        
        # 간단한 표 형식으로 포맷팅
        formatted = "| 지표 | 값 |\n|------|----|\n"
        for key, value in ratios_data.items():
            if isinstance(value, (int, float)):
                formatted += f"| {key} | {value:.2f} |\n"
            else:
                formatted += f"| {key} | {value} |\n"
        
        return formatted
    
    def _format_sentiment_distribution(self, distribution: Dict[str, int]) -> str:
        """감성 분포 포맷팅"""
        if not distribution:
            return "- 감성 분석 데이터 없음"
        
        total = sum(distribution.values())
        if total == 0:
            return "- 분석된 기사 없음"
        
        formatted = ""
        for sentiment, count in distribution.items():
            percentage = (count / total) * 100
            formatted += f"- {sentiment.title()}: {count}개 ({percentage:.1f}%)\n"
        
        return formatted.strip()
    
    def _format_financial_events(self, events_summary: Dict[str, List]) -> str:
        """재무 이벤트 포맷팅"""
        if not events_summary:
            return "- 탐지된 이벤트 없음"
        
        formatted = ""
        for event_type, events in events_summary.items():
            formatted += f"### {event_type.replace('_', ' ').title()}\n"
            formatted += f"- 탐지된 이벤트: {len(events)}개\n"
            if events:
                latest_event = max(events, key=lambda x: x.get('article_date', ''))
                formatted += f"- 최근 이벤트: {latest_event.get('article_title', 'N/A')}\n"
            formatted += "\n"
        
        return formatted
    
    def _generate_market_trend_analysis(self, sentiment_data: Dict, events_data: Dict) -> str:
        """시장 트렌드 분석 생성"""
        avg_sentiment = sentiment_data.get('average_sentiment_score', 0)
        event_count = events_data.get('total_events_detected', 0)
        
        if avg_sentiment > 0.2 and event_count > 0:
            return "긍정적인 뉴스 흐름과 활발한 기업 활동이 관찰됩니다. 시장 관심도가 높은 상태로 판단됩니다."
        elif avg_sentiment < -0.2:
            return "부정적인 뉴스 흐름이 감지됩니다. 시장 심리 악화에 주의가 필요합니다."
        else:
            return "중립적인 시장 상황으로, 추가적인 모멘텀 발생 여부를 지켜볼 필요가 있습니다."
    
    def _assess_financial_risk(self, health_data: Dict) -> str:
        """재무 리스크 평가"""
        stability_score = health_data.get('stability', {}).get('score', 50)
        if stability_score >= 70:
            return "낮음"
        elif stability_score >= 50:
            return "보통"
        else:
            return "높음"
    
    def _assess_market_risk(self, analysis_data: Dict) -> str:
        """시장 리스크 평가"""
        sentiment_score = analysis_data.get('news_sentiment', {}).get('average_sentiment_score', 0)
        if sentiment_score > 0.3:
            return "낮음"
        elif sentiment_score > -0.3:
            return "보통"
        else:
            return "높음"
    
    def _assess_operational_risk(self, analysis_data: Dict) -> str:
        """운영 리스크 평가"""
        # 이벤트 데이터를 기반으로 운영 리스크 평가
        events = analysis_data.get('financial_events', {}).get('event_types_found', [])
        risk_events = ['audit_opinion', 'major_contract']
        
        if any(event in events for event in risk_events):
            return "보통"
        else:
            return "낮음"
    
    def _generate_risk_mitigation_suggestions(self, analysis_data: Dict) -> str:
        """리스크 완화 방안 제안"""
        suggestions = [
            "포트폴리오 분산을 통한 리스크 분산",
            "정기적인 재무 상태 모니터링",
            "시장 변동성에 대비한 손실 제한 전략 수립",
            "기업 공시 및 뉴스 지속적 추적"
        ]
        return self._format_list_items(suggestions)
    
    def _format_data_sources(self, analysis_data: Dict) -> str:
        """데이터 출처 포맷팅"""
        sources = []
        
        # 각 분석 데이터에서 출처 정보 추출
        for key, data in analysis_data.items():
            if isinstance(data, dict) and 'data_source' in data:
                source = data['data_source']
                if source not in sources:
                    sources.append(source)
        
        if not sources:
            sources = ['금융감독원 전자공시시스템(DART)', 'Mock 데이터']
        
        formatted = ""
        for i, source in enumerate(sources, 1):
            formatted += f"{i}. {source}\n"
        
        return formatted
    
    def _extract_data_sources(self, analysis_data: Dict) -> List[str]:
        """분석 데이터에서 데이터 출처 추출"""
        sources = set()
        
        for data in analysis_data.values():
            if isinstance(data, dict) and 'data_source' in data:
                sources.add(data['data_source'])
        
        return list(sources)

# 전역 리포트 생성기 인스턴스
report_generator = ReportGenerator() 