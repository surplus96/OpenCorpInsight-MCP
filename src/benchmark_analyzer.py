#!/usr/bin/env python3
"""
Benchmark Analyzer for OpenCorpInsight
업계 벤치마크 비교 분석 (간소화 버전)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import warnings
warnings.filterwarnings('ignore')

import os
import requests
import zipfile
import io
import xml.etree.ElementTree as ET

try:
    import numpy as np
    import pandas as pd
    from scipy import stats
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False

from cache_manager import cache_manager

logger = logging.getLogger("benchmark-analyzer")

class BenchmarkAnalyzer:
    """벤치마크 비교 분석 클래스"""
    
    def __init__(self):
        # 한국 업종 분류(기본 그룹)
        self.industry_classification = {
            '반도체': ['삼성전자', 'SK하이닉스', '동진쎄미켐'],
            '전기전자': ['LG전자', '삼성SDI', 'LG디스플레이'],
            '화학': ['LG화학', 'SK이노베이션', '롯데케미칼'],
            '자동차': ['현대차', '기아', '현대모비스'],
            '금융': ['KB금융', '신한지주', 'NH투자증권'],
            '인터넷': ['NAVER', '카카오', '넷마블']
        }
        
        self.key_metrics = ['ROE', 'ROA', '부채비율', '유동비율', '매출액증가율', 'PER', 'PBR']
    
    def _parse_amount(self, s: str) -> float:
        if not s or s == '-':
            return 0.0
        s2 = str(s).replace(',', '').strip()
        neg = s2.startswith('(') and s2.endswith(')')
        if neg:
            s2 = s2[1:-1]
        try:
            v = float(s2)
        except Exception:
            return 0.0
        return -v if neg else v

    def _fetch_single_year(self, api_key: str, corp_code: str, year: str) -> pd.DataFrame:
        url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
        for rc, fd in [('11014','CFS'), ('11014','OFS'), ('11013','CFS')]:
            params = {'crtfc_key': api_key,'corp_code': corp_code,'bsns_year': year,'reprt_code': rc,'fs_div': fd}
            j = requests.get(url, params=params).json()
            if j.get('status') == '000' and j.get('list'):
                return pd.DataFrame(j['list'])
        return pd.DataFrame()

    def _get_account(self, df: pd.DataFrame, sj: List[str], patterns: List[str]) -> float:
        if df.empty:
            return 0.0
        target = df[df['sj_nm'].isin(sj)] if 'sj_nm' in df.columns else df
        for p in patterns:
            try:
                m = target[target['account_nm'].str.contains(p, na=False, regex=True)]
            except Exception:
                m = pd.DataFrame()
            if not m.empty:
                for col in ['thstrm_amount','frmtrm_amount','bfefrmtrm_amount']:
                    if col in m.columns:
                        val = self._parse_amount(m.iloc[0][col])
                        if val != 0.0:
                            return val
        if 'account_id' in target.columns:
            for pid in ['ProfitLoss','NetIncome','Revenue','Sales','OperatingIncome']:
                m2 = target[target['account_id'].str.contains(pid, na=False)]
                if not m2.empty:
                    for col in ['thstrm_amount','frmtrm_amount','bfefrmtrm_amount']:
                        if col in m2.columns:
                            val = self._parse_amount(m2.iloc[0][col])
                            if val != 0.0:
                                return val
        return 0.0

    async def compare_with_industry(self, corp_name: str, industry: str, 
                                  comparison_metrics: List[str]) -> Dict[str, Any]:
        """업계 벤치마크 비교 (DART 실데이터 기반)"""
        try:
            cache_key = f"{corp_name}_{industry}_{'-'.join(sorted(comparison_metrics))}"
            cached_result = cache_manager.get('industry_benchmark', cache_key=cache_key)
            if cached_result:
                return cached_result

            # 비교 대상 기업 목록 확보
            companies = self.industry_classification.get(industry, [])
            if corp_name not in companies:
                companies = [corp_name] + companies
            companies = list(dict.fromkeys(companies))[:6]

            # API 키는 런타임에서 환경변수로 받음
            api_key = os.getenv('DART_API_KEY')
            if not api_key:
                raise RuntimeError('DART_API_KEY not set')

            # corp_code 조회 (로컬 간단 버전)
            def get_corp_code(name: str) -> Optional[str]:
                try:
                    zip_url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
                    z = zipfile.ZipFile(io.BytesIO(requests.get(zip_url).content))
                    xml_bytes = z.read('CORPCODE.xml')
                    try:
                        xml_str = xml_bytes.decode('euc-kr')
                    except Exception:
                        xml_str = xml_bytes.decode('utf-8')
                    root = ET.fromstring(xml_str)
                    candidates = []
                    for item in root.findall('.//list'):
                        nm = item.find('corp_name').text
                        cd = item.find('corp_code').text
                        if nm == name or nm == name + '주식회사' or nm.endswith(name):
                            candidates.append((nm, cd))
                    if candidates:
                        return sorted(candidates, key=lambda x: len(x[0]))[0][1]
                except Exception:
                    return None
                return None

            results: Dict[str, Dict[str, float]] = {}
            for c in companies:
                code = get_corp_code(c)
                if not code:
                    continue
                df = self._fetch_single_year(api_key, code, str(datetime.now().year - 1))
                if df.empty:
                    continue
                total_assets = self._get_account(df, ['재무상태표'], ['자산총계'])
                total_equity = self._get_account(df, ['재무상태표'], ['자본총계'])
                total_liabilities = self._get_account(df, ['재무상태표'], ['부채총계'])
                current_assets = self._get_account(df, ['재무상태표'], ['유동자산'])
                current_liabilities = self._get_account(df, ['재무상태표'], ['유동부채'])
                revenue = self._get_account(df, ['손익계산서','포괄손익계산서'], ['매출액','수익\(매출액\)','영업수익'])
                operating = self._get_account(df, ['손익계산서','포괄손익계산서'], ['영업이익'])
                net = self._get_account(df, ['손익계산서','포괄손익계산서'], ['당기순이익','당기순이익\(손실\)','지배주주지분\s*순이익','지배기업\s*소유주지분\s*순이익','연결당기순이익'])

                metrics: Dict[str, float] = {}
                for m in comparison_metrics:
                    if m in ['ROE','roe'] and total_equity:
                        metrics['ROE'] = round(net / total_equity * 100, 2) if net else 0.0
                    elif m in ['ROA','roa'] and total_assets:
                        metrics['ROA'] = round(net / total_assets * 100, 2) if net else 0.0
                    elif m in ['부채비율','debt_ratio'] and total_equity:
                        metrics['부채비율'] = round(total_liabilities / total_equity * 100, 2)
                    elif m in ['유동비율','current_ratio'] and current_liabilities:
                        metrics['유동비율'] = round(current_assets / current_liabilities * 100, 2)
                    elif m in ['매출액','revenue']:
                        metrics['매출액'] = round(revenue / 1e8, 1)  # 억원
                    elif m in ['영업이익','operating_profit']:
                        metrics['영업이익'] = round(operating / 1e8, 1)
                    elif m in ['순이익','net_profit']:
                        metrics['순이익'] = round(net / 1e8, 1)
                results[c] = metrics

            result = {
                'company': corp_name,
                'industry': industry,
                'comparison_metrics': comparison_metrics,
                'industry_companies_count': len(companies),
                'benchmark_results': results,
                'comparison_timestamp': datetime.now().isoformat()
            }
            cache_manager.set('industry_benchmark', result, cache_key=cache_key)
            return result
        except Exception as e:
            logger.error(f"업계 벤치마크 비교 중 오류: {e}")
            return self._get_mock_industry_comparison(corp_name, industry, comparison_metrics)
    
    async def analyze_competitive_position(self, corp_name: str, competitors: List[str], 
                                         analysis_metrics: List[str]) -> Dict[str, Any]:
        """경쟁 포지션 분석"""
        try:
            cache_key = f"{corp_name}_vs_{'-'.join(sorted(competitors))}"
            cached_result = cache_manager.get('competitive_analysis', cache_key=cache_key)
            if cached_result:
                return cached_result
            
            result = self._get_mock_competitive_analysis(corp_name, competitors, analysis_metrics)
            
            cache_manager.set('competitive_analysis', result, cache_key=cache_key)
            return result
            
        except Exception as e:
            logger.error(f"경쟁 포지션 분석 중 오류: {e}")
            return self._get_mock_competitive_analysis(corp_name, competitors, analysis_metrics)
    
    async def generate_industry_report(self, industry: str, report_type: str = "comprehensive") -> Dict[str, Any]:
        """업계 분석 리포트 생성"""
        try:
            cache_key = f"industry_report_{industry}_{report_type}"
            cached_result = cache_manager.get('industry_report', cache_key=cache_key)
            if cached_result:
                return cached_result
            
            result = self._get_mock_industry_report(industry, report_type)
            
            cache_manager.set('industry_report', result, cache_key=cache_key)
            return result
            
        except Exception as e:
            logger.error(f"업계 리포트 생성 중 오류: {e}")
            return self._get_mock_industry_report(industry, report_type)
    
    def _get_mock_industry_comparison(self, corp_name: str, industry: str, metrics: List[str]) -> Dict[str, Any]:
        """Mock 업계 비교 결과"""
        mock_benchmark = {}
        for metric in metrics:
            if metric == 'ROE':
                company_val, industry_mean = 15.2, 12.8
            elif metric == 'ROA':
                company_val, industry_mean = 8.5, 7.2
            elif metric == '부채비율':
                company_val, industry_mean = 45.0, 52.0
            else:
                company_val, industry_mean = 12.0, 10.0
            
            percentile = 72.5 if company_val > industry_mean else 35.0
            performance = '양호' if percentile > 60 else '보통' if percentile > 40 else '부족'
            
            mock_benchmark[metric] = {
                'company_value': company_val,
                'industry_mean': industry_mean,
                'percentile': percentile,
                'performance': performance,
                'vs_mean_pct': (company_val - industry_mean) / industry_mean * 100
            }
        
        return {
            'company': corp_name,
            'industry': industry,
            'comparison_metrics': metrics,
            'industry_companies_count': len(self.industry_classification.get(industry, [])),
            'benchmark_results': mock_benchmark,
            'performance_assessment': {
                'overall_grade': 'B+',
                'strong_areas': [m for m in metrics if mock_benchmark[m]['percentile'] > 70],
                'weak_areas': [m for m in metrics if mock_benchmark[m]['percentile'] < 40]
            },
            'comparison_timestamp': datetime.now().isoformat()
        }
    
    def _get_mock_competitive_analysis(self, corp_name: str, competitors: List[str], metrics: List[str]) -> Dict[str, Any]:
        """Mock 경쟁 분석 결과"""
        return {
            'company': corp_name,
            'competitors': competitors,
            'analysis_metrics': metrics,
            'swot_analysis': {
                'strengths': ['ROE 우수', '안정적 재무구조'],
                'weaknesses': ['성장률 개선 필요'],
                'opportunities': ['디지털 전환', 'ESG 경영'],
                'threats': ['경쟁 심화', '규제 변화']
            },
            'market_position': '강자',
            'strategic_recommendations': [
                '핵심 강점 영역 확대',
                '약점 영역 집중 개선',
                '지속적 벤치마킹'
            ],
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _get_mock_industry_report(self, industry: str, report_type: str) -> Dict[str, Any]:
        """Mock 업계 리포트 결과"""
        return {
            'industry': industry,
            'report_type': report_type,
            'companies_analyzed': len(self.industry_classification.get(industry, [])),
            'industry_overview': {
                'market_characteristics': f"{industry} 업계는 지속적인 성장세를 보이고 있습니다.",
                'key_trends': ['디지털 전환', 'ESG 경영', '글로벌 경쟁']
            },
            'market_leaders': self.industry_classification.get(industry, [])[:3],
            'growth_companies': self.industry_classification.get(industry, [])[:2],
            'report_timestamp': datetime.now().isoformat()
        }

# 전역 벤치마크 분석기 인스턴스
benchmark_analyzer = BenchmarkAnalyzer() 