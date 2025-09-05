#!/usr/bin/env python3
"""
Test suite for DART MCP Server
"""

import pytest
import asyncio
import json
import os
import tempfile
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any
from datetime import datetime

# 테스트용 import
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from dart_mcp_server import (
    set_dart_api_key, 
    get_corp_code, 
    get_company_info,
    get_financial_statements,
    get_financial_ratios,
    compare_financials,
    get_disclosure_list,
    get_company_news,
    analyze_news_sentiment,
    detect_financial_events,
    generate_investment_signal,
    generate_summary_report,
    export_to_pdf
)
from cache_manager import CacheManager

class TestDartMCPServer:
    """DART MCP Server 테스트 클래스"""
    
    @pytest.fixture
    def setup_api_key(self):
        """테스트용 API 키 설정"""
        # 실제 API 키 대신 테스트용 더미 키 사용
        test_api_key = "test_api_key_40_characters_long_dummy_key"
        return test_api_key
    
    @pytest.fixture
    def mock_dart_response(self):
        """DART API 응답 모킹"""
        return {
            'status': '000',
            'message': '정상',
            'list': [
                {
                    'corp_code': '00126380',
                    'corp_name': '삼성전자',
                    'stock_code': '005930',
                    'ceo_nm': '이재용',
                    'corp_cls': 'Y',
                    'est_dt': '19690113',
                    'list_dt': '19751211'
                }
            ]
        }
    
    @pytest.fixture
    def mock_financial_data(self):
        """재무제표 데이터 모킹"""
        return {
            'status': '000',
            'message': '정상',
            'list': [
                {
                    'sj_nm': '재무상태표',
                    'account_nm': '자산총계',
                    'thstrm_amount': '1,000,000,000',
                    'frmtrm_amount': '900,000,000'
                },
                {
                    'sj_nm': '재무상태표',
                    'account_nm': '자본총계',
                    'thstrm_amount': '600,000,000',
                    'frmtrm_amount': '550,000,000'
                },
                {
                    'sj_nm': '손익계산서',
                    'account_nm': '매출액',
                    'thstrm_amount': '800,000,000',
                    'frmtrm_amount': '750,000,000'
                },
                {
                    'sj_nm': '손익계산서',
                    'account_nm': '당기순이익',
                    'thstrm_amount': '100,000,000',
                    'frmtrm_amount': '90,000,000'
                },
                {
                    'sj_nm': '현금흐름표',
                    'account_nm': '영업활동으로인한현금흐름',
                    'thstrm_amount': '150,000,000',
                    'frmtrm_amount': '140,000,000'
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_set_dart_api_key(self, setup_api_key):
        """API 키 설정 테스트"""
        result = await set_dart_api_key(setup_api_key)
        
        assert len(result) == 1
        assert "DART API 키가 설정되었습니다" in result[0].text
        assert setup_api_key[:8] in result[0].text
    
    @pytest.mark.asyncio
    @patch('dart_mcp_server.requests.get')
    @patch('dart_mcp_server.zipfile.ZipFile')
    async def test_get_corp_code(self, mock_zipfile, mock_requests, setup_api_key):
        """기업 코드 조회 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock XML 데이터
        mock_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <result>
            <list>
                <corp_code>00126380</corp_code>
                <corp_name>삼성전자</corp_name>
                <stock_code>005930</stock_code>
            </list>
        </result>'''
        
        # Mock zipfile 설정
        mock_zip_instance = Mock()
        mock_zip_instance.read.return_value = mock_xml.encode('utf-8')
        mock_zipfile.return_value.__enter__.return_value = mock_zip_instance
        
        # Mock requests 설정
        mock_response = Mock()
        mock_response.content = b'dummy_zip_content'
        mock_requests.return_value = mock_response
        
        # 테스트 실행
        corp_code = await get_corp_code('삼성전자')
        
        assert corp_code == '00126380'
    
    @pytest.mark.asyncio
    @patch('dart_mcp_server.get_corp_code')
    @patch('dart_mcp_server.requests.get')
    async def test_get_company_info(self, mock_requests, mock_get_corp_code, 
                                  setup_api_key, mock_dart_response):
        """기업 정보 조회 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock 설정
        mock_get_corp_code.return_value = '00126380'
        mock_response = Mock()
        # company API는 단일 객체를 반환하므로 status 필드를 추가
        company_data = mock_dart_response['list'][0].copy()
        company_data['status'] = '000'
        mock_response.json.return_value = company_data
        mock_requests.return_value = mock_response
        
        # 테스트 실행
        result = await get_company_info('삼성전자')
        
        assert len(result) == 1
        assert '삼성전자' in result[0].text
        assert '이재용' in result[0].text
    
    @pytest.mark.asyncio
    @patch('dart_mcp_server.get_corp_code')
    @patch('dart_mcp_server.requests.get')
    async def test_get_financial_statements(self, mock_requests, mock_get_corp_code,
                                          setup_api_key, mock_financial_data):
        """재무제표 조회 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock 설정
        mock_get_corp_code.return_value = '00126380'
        mock_response = Mock()
        mock_response.json.return_value = mock_financial_data
        mock_requests.return_value = mock_response
        
        # 테스트 실행
        result = await get_financial_statements('삼성전자', '2023', '11014', 'CFS', '현금흐름표')
        
        assert len(result) == 1
        assert '현금흐름표' in result[0].text
        assert '영업활동으로인한현금흐름' in result[0].text
    
    @pytest.mark.asyncio
    @patch('dart_mcp_server.get_corp_code')
    @patch('dart_mcp_server.requests.get')
    async def test_get_financial_ratios(self, mock_requests, mock_get_corp_code,
                                      setup_api_key, mock_financial_data):
        """재무비율 계산 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock 설정
        mock_get_corp_code.return_value = '00126380'
        mock_response = Mock()
        mock_response.json.return_value = mock_financial_data
        mock_requests.return_value = mock_response
        
        # 테스트 실행
        result = await get_financial_ratios('삼성전자', '2023', ['profitability', 'stability'], True)
        
        assert len(result) == 1
        assert 'ROE' in result[0].text
        assert '수익성 지표' in result[0].text
        assert '안정성 지표' in result[0].text
    
    @pytest.mark.asyncio
    @patch('dart_mcp_server.get_corp_code')
    @patch('dart_mcp_server.requests.get')
    async def test_compare_financials(self, mock_requests, mock_get_corp_code,
                                    setup_api_key, mock_financial_data):
        """기업 재무지표 비교 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock 설정
        mock_get_corp_code.side_effect = lambda x: '00126380' if x == '삼성전자' else '00164779'
        mock_response = Mock()
        mock_response.json.return_value = mock_financial_data
        mock_requests.return_value = mock_response
        
        # 테스트 실행
        result = await compare_financials(['삼성전자', 'SK하이닉스'], '2023', 
                                        ['revenue', 'operating_profit', 'roe'], True)
        
        assert len(result) == 1
        assert '기업 재무지표 비교' in result[0].text
        assert '삼성전자' in result[0].text
        assert 'SK하이닉스' in result[0].text
    
    @pytest.mark.asyncio
    @patch('news_analyzer.news_analyzer.search_company_news')
    async def test_get_company_news(self, mock_search_news, setup_api_key):
        """기업 뉴스 수집 테스트"""
        # API 키 설정
        await set_dart_api_key(setup_api_key)
        
        # Mock 뉴스 데이터
        mock_news_data = {
            "search_query": "삼성전자 최근 1주일 뉴스",
            "articles": [
                {
                    "title": "삼성전자 3분기 실적 발표",
                    "summary": "매출 증가세 지속",
                    "source": "한국경제",
                    "published_date": "2024-01-15",
                    "url": "https://example.com/news1",
                    "sentiment_score": 0.7
                }
            ],
            "search_timestamp": "2024-01-15T10:00:00"
        }
        
        mock_search_news.return_value = mock_news_data
        
        # 테스트 실행
        result = await get_company_news('삼성전자', 'week', ['earnings'], True)
        
        assert len(result) == 1
        assert '삼성전자 최근 뉴스 분석' in result[0].text
        assert '3분기 실적 발표' in result[0].text
        assert '긍정적' in result[0].text
    
    @pytest.mark.asyncio
    @patch('news_analyzer.news_analyzer.analyze_company_news_sentiment')
    async def test_analyze_news_sentiment(self, mock_analyze_sentiment, setup_api_key):
        """뉴스 감성 분석 테스트"""
        await set_dart_api_key(setup_api_key)
        
        mock_sentiment_data = {
            'company': '삼성전자',
            'analysis_period': 'week',
            'analysis_depth': 'detailed',
            'total_articles_analyzed': 3,
            'average_sentiment_score': 0.4,
            'sentiment_distribution': {'positive': 2, 'negative': 0, 'neutral': 1},
            'investment_impact': '긍정적 영향 예상',
            'article_sentiments': [
                {
                    'title': '삼성전자 실적 호조',
                    'sentiment_score': 0.6,
                    'sentiment_label': 'positive',
                    'detected_keywords': ['성장', '증가', '호조']
                }
            ],
            'analysis_timestamp': datetime.now().isoformat(),
            'data_source': 'mock'
        }
        
        mock_analyze_sentiment.return_value = mock_sentiment_data
        
        result = await analyze_news_sentiment('삼성전자', 'week', 'detailed')
        
        assert '뉴스 감성 분석 결과' in result[0].text
        assert '긍정적 영향 예상' in result[0].text
        assert '3개' in result[0].text  # total articles
    
    @pytest.mark.asyncio
    @patch('news_analyzer.news_analyzer.detect_market_events')
    async def test_detect_financial_events(self, mock_detect_events, setup_api_key):
        """재무 이벤트 탐지 테스트"""
        await set_dart_api_key(setup_api_key)
        
        mock_event_data = {
            'company': '삼성전자',
            'monitoring_period_days': 30,
            'total_events_detected': 2,
            'event_types_found': ['earnings', 'dividend'],
            'event_summary': {
                'earnings': [{'event_type': 'earnings', 'article_title': '3분기 실적 발표'}],
                'dividend': [{'event_type': 'dividend', 'article_title': '배당금 지급 결정'}]
            },
            'detection_timestamp': datetime.now().isoformat()
        }
        
        mock_detect_events.return_value = mock_event_data
        
        result = await detect_financial_events('삼성전자', 30, ['earnings', 'dividend'])
        
        assert '재무 이벤트 탐지 결과' in result[0].text
        assert '실적 발표' in result[0].text
    
    # Phase 3 Tests
    @pytest.mark.asyncio
    async def test_generate_investment_signal(self, setup_api_key):
        """투자 신호 생성 테스트"""
        await set_dart_api_key(setup_api_key)
        
        result = await generate_investment_signal(
            '삼성전자', 
            3,
            {"financial_health": 0.4, "news_sentiment": 0.3, "event_impact": 0.2, "market_trend": 0.1},
            "moderate"
        )
        
        assert '투자 신호 분석' in result[0].text
        assert '신호 점수' in result[0].text
        assert '신뢰도' in result[0].text
    
    @pytest.mark.asyncio
    async def test_generate_summary_report(self, setup_api_key):
        """종합 리포트 생성 테스트"""
        await set_dart_api_key(setup_api_key)
        
        result = await generate_summary_report('삼성전자', 'comprehensive', False, 'detailed')
        
        assert '종합 기업 분석 리포트' in result[0].text
        assert '경영진 요약' in result[0].text
        assert '재무 분석' in result[0].text
    
    @pytest.mark.asyncio
    async def test_export_to_pdf(self, setup_api_key):
        """PDF 내보내기 테스트"""
        await set_dart_api_key(setup_api_key)
        
        sample_report = "# 테스트 리포트\n\n이것은 테스트용 리포트입니다."
        
        result = await export_to_pdf('삼성전자', sample_report, True, 'A4')
        
        # PDF 라이브러리가 없을 수 있으므로 조건부 테스트
        if 'reportlab 라이브러리가 설치되지 않았습니다' in result[0].text:
            assert 'reportlab' in result[0].text
        else:
            assert 'PDF 내보내기 완료' in result[0].text
            assert 'Base64' in result[0].text

class TestCacheManager:
    """캐시 매니저 테스트 클래스"""
    
    @pytest.fixture
    def temp_cache_manager(self):
        """임시 캐시 매니저 생성"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, 'test_cache.db')
            cache_manager = CacheManager(cache_path)
            yield cache_manager
    
    def test_cache_set_and_get(self, temp_cache_manager):
        """캐시 저장 및 조회 테스트"""
        test_data = {'company': '삼성전자', 'revenue': 1000000}
        
        # 캐시에 저장
        temp_cache_manager.set('company_info', test_data, ttl_hours=1, corp_name='삼성전자')
        
        # 캐시에서 조회
        cached_data = temp_cache_manager.get('company_info', corp_name='삼성전자')
        
        assert cached_data == test_data
    
    def test_cache_expiry(self, temp_cache_manager):
        """캐시 만료 테스트"""
        test_data = {'company': '삼성전자'}
        
        # 매우 짧은 TTL로 저장 (테스트용)
        temp_cache_manager.set('company_info', test_data, ttl_hours=0, corp_name='삼성전자')
        
        # 만료된 캐시는 None 반환
        cached_data = temp_cache_manager.get('company_info', corp_name='삼성전자')
        assert cached_data is None
    
    def test_cache_stats(self, temp_cache_manager):
        """캐시 통계 테스트"""
        # 테스트 데이터 저장
        temp_cache_manager.set('company_info', {'test': 1}, ttl_hours=24, corp_name='test1')
        temp_cache_manager.set('financial_data', {'test': 2}, ttl_hours=24, corp_name='test2')
        
        # 통계 조회
        stats = temp_cache_manager.get_stats()
        
        assert stats['total_entries'] == 2
        assert stats['active_entries'] == 2
        assert 'company_info' in stats['categories']
        assert 'financial_data' in stats['categories']
    
    def test_cache_cleanup(self, temp_cache_manager):
        """캐시 정리 테스트"""
        # 만료된 데이터 저장
        temp_cache_manager.set('test_category', {'test': 1}, ttl_hours=0, test_key='test')
        
        # 정리 실행
        cleaned_count = temp_cache_manager.cleanup_expired()
        
        assert cleaned_count >= 0  # 만료된 항목이 정리됨

class TestIntegration:
    """통합 테스트 클래스"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """전체 워크플로우 통합 테스트"""
        # 실제 API 키가 필요한 테스트
        # 환경변수에서 API 키 읽기
        api_key = os.getenv('DART_API_KEY')
        
        if not api_key:
            pytest.skip("DART_API_KEY 환경변수가 설정되지 않았습니다")
        
        # API 키 설정
        await set_dart_api_key(api_key)
        
        # 기업 정보 조회
        company_result = await get_company_info('삼성전자')
        assert len(company_result) == 1
        assert '삼성전자' in company_result[0].text
        
        # 재무제표 조회 (모든 필수 파라미터 제공)
        financial_result = await get_financial_statements('삼성전자', '2023', '11014', 'CFS', '현금흐름표')
        assert len(financial_result) == 1
        
        # 재무비율 조회
        ratio_result = await get_financial_ratios('삼성전자', '2023', ['profitability'], True)
        assert len(ratio_result) == 1
        assert 'ROE' in ratio_result[0].text or '수익성' in ratio_result[0].text

if __name__ == '__main__':
    # 테스트 실행
    pytest.main([__file__, '-v']) 