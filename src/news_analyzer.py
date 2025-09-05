#!/usr/bin/env python3
"""
News Analyzer with Perplexity Integration
Perplexity MCP를 활용한 뉴스 수집 및 감성 분석
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

# 캐시 매니저 import 추가
from cache_manager import cache_manager

logger = logging.getLogger("news-analyzer")

class NewsAnalyzer:
    """Perplexity MCP 연동 뉴스 분석기"""
    
    def __init__(self):
        self.sentiment_keywords = {
            'positive': [
                '성장', '증가', '상승', '호조', '개선', '확대', '투자', '혁신', '성공', '수익',
                '이익', '흑자', '돌파', '달성', '기대', '긍정', '우수', '강세', '회복', '도약',
                '신기록', '최고', '확장', '발전', '진전', '성과', '수주', '계약', '협력'
            ],
            'negative': [
                '하락', '감소', '부진', '악화', '축소', '손실', '적자', '위기', '리스크', '우려',
                '불안', '부정', '저조', '침체', '둔화', '타격', '충격', '문제', '어려움', '곤란',
                '최저', '급락', '폭락', '취소', '연기', '중단', '실패', '좌절', '논란'
            ],
            'neutral': [
                '발표', '공시', '보고', '계획', '예정', '진행', '검토', '논의', '회의', '협의',
                '발언', '언급', '설명', '분석', '전망', '예측', '조사', '연구', '개발', '준비'
            ]
        }
        # Perplexity MCP 호출을 위한 함수 참조 저장
        self._perplexity_search = None
        
    def set_perplexity_search_function(self, search_func):
        """Perplexity 검색 함수 설정 (MCP 호출 함수)"""
        self._perplexity_search = search_func

    async def search_company_news(self, corp_name: str, search_period: str = "week") -> Dict[str, Any]:
        """Perplexity를 통한 기업 뉴스 검색"""
        try:
            # 기간 동의어 표준화
            norm_map = {
                'day': 'day', '1일': 'day', '하루': 'day', '오늘': 'day',
                'week': 'week', '1주': 'week', '1주일': 'week', '일주일': 'week', '7일': 'week',
                'month': 'month', '1개월': 'month', '한달': 'month', '30일': 'month'
            }
            normalized = norm_map.get(str(search_period).strip().lower(), 'week')

            # 캐시에서 먼저 조회 (표준화된 키 사용)
            cached_result = cache_manager.get('company_news', corp_name=corp_name, search_period=normalized)
            if cached_result:
                logger.info(f"뉴스 검색 결과 캐시 히트: {corp_name}")
                return cached_result
            
            # Perplexity 검색 쿼리 구성
            search_query = f"{corp_name} 뉴스 실적 주가 투자 공시"
            
            # 검색 기간 필터
            recency_filter = normalized
            
            # Perplexity MCP 호출
            search_results = None
            if self._perplexity_search:
                try:
                    # Perplexity 검색 결과도 별도 캐시
                    cached_search = cache_manager.get('perplexity_search', query=search_query, filter=recency_filter or 'none')

                    if cached_search:
                        search_results = cached_search
                        logger.info(f"Perplexity 검색 결과 캐시 히트: {search_query}")
                    else:
                        if recency_filter:
                            search_results = await self._perplexity_search(search_query, recency_filter)
                        else:
                            search_results = await self._perplexity_search(search_query)

                        # Perplexity 검색 결과 캐시 저장
                        cache_manager.set('perplexity_search', search_results, query=search_query, filter=recency_filter or 'none')

                    # JSON 형태를 우선 사용, 문자열이면 파싱 로직으로 처리
                    if isinstance(search_results, dict) and 'articles' in search_results:
                        articles = search_results['articles']
                        news_data = {
                            'company': corp_name,
                            'search_period': search_period,
                            'total_articles': len(articles),
                            'articles': articles[:10],
                            'search_timestamp': datetime.now().isoformat(),
                            'data_source': 'perplexity_live'
                        }
                    else:
                        news_data = self._parse_perplexity_results(str(search_results), corp_name, search_period)

                except Exception as e:
                    logger.warning(f"Perplexity 검색 실패, Mock 데이터 사용: {e}")
                    news_data = self._get_mock_news_data(corp_name, search_period)
            else:
                logger.info("Perplexity 검색 함수가 설정되지 않음, Mock 데이터 사용")
                news_data = self._get_mock_news_data(corp_name, search_period)
            
            # 결과를 캐시에 저장
            cache_manager.set('company_news', news_data, corp_name=corp_name, search_period=search_period)
            logger.info(f"뉴스 검색 결과 캐시 저장: {corp_name}")
            
            return news_data
                
        except Exception as e:
            logger.error(f"뉴스 검색 중 오류 발생: {e}")
            return self._get_mock_news_data(corp_name, search_period)
    
    def _parse_perplexity_results(self, search_results: str, corp_name: str, search_period: str) -> Dict[str, Any]:
        """Perplexity 검색 결과를 뉴스 데이터 구조로 파싱"""
        try:
            # Perplexity 결과에서 뉴스 정보 추출
            articles = []
            
            # 간단한 파싱 로직 (실제로는 더 정교한 파싱이 필요)
            lines = search_results.split('\n')
            current_article = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 제목으로 보이는 라인 감지 (예: "- 제목" 형태)
                if line.startswith('- ') or line.startswith('* '):
                    if current_article:
                        articles.append(current_article)
                    current_article = {
                        'title': line[2:].strip(),
                        'content': '',
                        'published_date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'Perplexity Search',
                        'url': '#'
                    }
                elif current_article and line:
                    # 내용으로 추가
                    current_article['content'] += line + ' '
            
            # 마지막 기사 추가
            if current_article:
                articles.append(current_article)
            
            # 기사가 없으면 기본 구조라도 반환
            if not articles:
                articles = [{
                    'title': f'{corp_name} 관련 최신 뉴스',
                    'content': search_results[:500] + '...' if len(search_results) > 500 else search_results,
                    'published_date': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'Perplexity Search',
                    'url': '#'
                }]
            
            return {
                'company': corp_name,
                'search_period': search_period,
                'total_articles': len(articles),
                'articles': articles[:10],  # 최대 10개 기사만
                'search_timestamp': datetime.now().isoformat(),
                'data_source': 'perplexity_live'
            }
            
        except Exception as e:
            logger.error(f"Perplexity 결과 파싱 실패: {e}")
            return self._get_mock_news_data(corp_name, search_period)
    
    def _get_mock_news_data(self, corp_name: str, search_period: str) -> Dict[str, Any]:
        """Mock 뉴스 데이터 반환 (Perplexity 호출 실패시 대체)"""
        mock_articles = [
            {
                'title': f'{corp_name} 3분기 실적 발표, 전년 대비 성장세 지속',
                'content': f'{corp_name}이 3분기 실적을 발표하며 전년 동기 대비 매출과 영업이익이 모두 증가했다고 밝혔습니다. 주요 사업부문에서의 견조한 성과가 전체 실적 개선을 이끌었습니다.',
                'published_date': (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),
                'source': 'Mock Financial News',
                'url': '#mock1'
            },
            {
                'title': f'{corp_name} 신기술 투자 확대, 미래 성장 동력 확보',
                'content': f'{corp_name}이 차세대 기술 개발을 위한 대규모 투자 계획을 발표했습니다. 이번 투자는 장기적인 경쟁력 강화를 위한 전략적 결정으로 평가됩니다.',
                'published_date': (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'),
                'source': 'Mock Tech News',
                'url': '#mock2'
            },
            {
                'title': f'{corp_name} 주가 상승, 시장 기대감 반영',
                'content': f'{corp_name} 주가가 최근 긍정적인 실적 전망과 신사업 진출 소식에 힘입어 상승세를 보이고 있습니다. 투자자들의 관심이 집중되고 있습니다.',
                'published_date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                'source': 'Mock Market News',
                'url': '#mock3'
            }
        ]
        
        return {
            'company': corp_name,
            'search_period': search_period,
            'total_articles': len(mock_articles),
            'articles': mock_articles,
            'search_timestamp': datetime.now().isoformat(),
            'data_source': 'mock_fallback'
        }

    def analyze_sentiment(self, text: str) -> Tuple[float, str, List[str]]:
        """텍스트 감성 분석 (keyword-based)"""
        text_lower = text.lower()
        
        positive_count = sum(1 for word in self.sentiment_keywords['positive'] if word in text_lower)
        negative_count = sum(1 for word in self.sentiment_keywords['negative'] if word in text_lower)
        neutral_count = sum(1 for word in self.sentiment_keywords['neutral'] if word in text_lower)
        
        total_count = positive_count + negative_count + neutral_count
        
        if total_count == 0:
            return 0.0, 'neutral', []
        
        # 감성 점수 계산 (-1.0 ~ 1.0)
        sentiment_score = (positive_count - negative_count) / total_count
        
        # 감성 레이블 결정
        if sentiment_score > 0.2:
            sentiment_label = 'positive'
        elif sentiment_score < -0.2:
            sentiment_label = 'negative'
        else:
            sentiment_label = 'neutral'
        
        # 감지된 키워드 수집
        detected_keywords = []
        for category, keywords in self.sentiment_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    detected_keywords.append(f"{keyword}({category})")
        
        return sentiment_score, sentiment_label, detected_keywords

    async def analyze_company_news_sentiment(self, corp_name: str, search_period: str = "week", 
                                           analysis_depth: str = "detailed") -> Dict[str, Any]:
        """기업 뉴스 종합 감성 분석"""
        try:
            # 캐시에서 먼저 조회
            cached_result = cache_manager.get('news_sentiment', corp_name=corp_name, search_period=search_period, analysis_depth=analysis_depth)
            if cached_result:
                logger.info(f"감성 분석 결과 캐시 히트: {corp_name}")
                return cached_result
            
            # 뉴스 데이터 수집
            news_data = await self.search_company_news(corp_name, search_period)
            
            sentiment_results = []
            total_sentiment_score = 0.0
            sentiment_distribution = {'positive': 0, 'negative': 0, 'neutral': 0}
            
            for article in news_data['articles']:
                # 제목과 내용을 합쳐서 분석
                full_text = f"{article['title']} {article['content']}"
                score, label, keywords = self.analyze_sentiment(full_text)
                
                sentiment_results.append({
                    'title': article['title'],
                    'sentiment_score': score,
                    'sentiment_label': label,
                    'detected_keywords': keywords[:5],  # 상위 5개 키워드만
                    'published_date': article['published_date']
                })
                
                total_sentiment_score += score
                sentiment_distribution[label] += 1
            
            # 전체 평균 감성 점수
            avg_sentiment = total_sentiment_score / len(news_data['articles']) if news_data['articles'] else 0.0
            
            # 투자 영향도 평가
            if avg_sentiment > 0.3:
                investment_impact = "긍정적 영향 예상"
            elif avg_sentiment < -0.3:
                investment_impact = "부정적 영향 우려"
            else:
                investment_impact = "중립적 영향"
            
            analysis_result = {
                'company': corp_name,
                'analysis_period': search_period,
                'analysis_depth': analysis_depth,
                'total_articles_analyzed': len(news_data['articles']),
                'average_sentiment_score': round(avg_sentiment, 3),
                'sentiment_distribution': sentiment_distribution,
                'investment_impact': investment_impact,
                'article_sentiments': sentiment_results,
                'analysis_timestamp': datetime.now().isoformat(),
                'data_source': news_data['data_source']
            }
            
            # 결과를 캐시에 저장
            cache_manager.set('news_sentiment', analysis_result, corp_name=corp_name, search_period=search_period, analysis_depth=analysis_depth)
            logger.info(f"감성 분석 결과 캐시 저장: {corp_name}")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"감성 분석 중 오류 발생: {e}")
            # 오류 시 기본 결과 반환
            return {
                'company': corp_name,
                'analysis_period': search_period,
                'analysis_depth': analysis_depth,
                'total_articles_analyzed': 0,
                'average_sentiment_score': 0.0,
                'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0},
                'investment_impact': '분석 불가',
                'article_sentiments': [],
                'analysis_timestamp': datetime.now().isoformat(),
                'data_source': 'error',
                'error_message': str(e)
            }

    async def detect_market_events(self, corp_name: str, monitoring_period: int = 30) -> Dict[str, Any]:
        """시장 이벤트 탐지"""
        try:
            # 캐시에서 먼저 조회
            cached_result = cache_manager.get('financial_events', corp_name=corp_name, monitoring_period=monitoring_period)
            if cached_result:
                logger.info(f"이벤트 탐지 결과 캐시 히트: {corp_name}")
                return cached_result
            
            # 뉴스 데이터 수집 (월간 검색)
            news_data = await self.search_company_news(corp_name, "month")
            
            # 이벤트 키워드 정의
            event_keywords = {
                'earnings': ['실적', '분기', '매출', '영업이익', '순이익', '어닝스'],
                'dividend': ['배당', '배당금', '주주환원', '배당수익률'],
                'capital_increase': ['증자', '유상증자', '무상증자', '자본확충'],
                'merger': ['인수', '합병', 'M&A', '통합'],
                'acquisition': ['인수', '매수', '지분취득', '투자'],
                'audit_opinion': ['감사', '감사의견', '회계', '재무제표'],
                'major_contract': ['계약', '수주', '협약', '업무협약']
            }
            
            detected_events = []
            
            for article in news_data['articles']:
                full_text = f"{article['title']} {article['content']}".lower()
                
                for event_type, keywords in event_keywords.items():
                    for keyword in keywords:
                        if keyword in full_text:
                            detected_events.append({
                                'event_type': event_type,
                                'event_keyword': keyword,
                                'article_title': article['title'],
                                'article_date': article['published_date'],
                                'relevance_score': full_text.count(keyword),
                                'source': article['source']
                            })
                            break  # 하나의 이벤트 타입당 하나의 매칭만
            
            # 이벤트 타입별 집계
            event_summary = {}
            for event in detected_events:
                event_type = event['event_type']
                if event_type not in event_summary:
                    event_summary[event_type] = []
                event_summary[event_type].append(event)
            
            event_result = {
                'company': corp_name,
                'monitoring_period_days': monitoring_period,
                'total_events_detected': len(detected_events),
                'event_types_found': list(event_summary.keys()),
                'event_summary': event_summary,
                'detailed_events': detected_events,
                'detection_timestamp': datetime.now().isoformat(),
                'data_source': news_data['data_source']
            }
            
            # 결과를 캐시에 저장
            cache_manager.set('financial_events', event_result, corp_name=corp_name, monitoring_period=monitoring_period)
            logger.info(f"이벤트 탐지 결과 캐시 저장: {corp_name}")
            
            return event_result
            
        except Exception as e:
            logger.error(f"이벤트 탐지 중 오류 발생: {e}")
            # 오류 시 기본 결과 반환
            return {
                'company': corp_name,
                'monitoring_period_days': monitoring_period,
                'total_events_detected': 0,
                'event_types_found': [],
                'event_summary': {},
                'detailed_events': [],
                'detection_timestamp': datetime.now().isoformat(),
                'data_source': 'error',
                'error_message': str(e)
            }

# 전역 뉴스 분석기 인스턴스
news_analyzer = NewsAnalyzer() 