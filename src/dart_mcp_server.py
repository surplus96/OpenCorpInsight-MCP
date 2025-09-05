#!/usr/bin/env python3
"""
DART MCP Server - Open DART API를 MCP 도구로 제공하는 서버
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import requests
import pandas as pd
import zipfile
import io
import re
import xml.etree.ElementTree as ET

# PDF 파싱 라이브러리(선택)
try:
    import pdfplumber
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

# AWS Secrets Manager (선택)
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO_AVAILABLE = True
except Exception:
    BOTO_AVAILABLE = False

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool
import mcp.types as types

# 프로젝트 모듈 import
from cache_manager import cache_manager, cached_api_call
from news_analyzer import news_analyzer
from report_generator import report_generator
from portfolio_analyzer import portfolio_analyzer
from time_series_analyzer import time_series_analyzer
from benchmark_analyzer import benchmark_analyzer

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dart-mcp-server")

# 전역 변수
API_KEY = None
CORP_CODE_CACHE = {}
# Perplexity API 키도 함께 로드할 수 있도록 전역에 보관
PERPLEXITY_API_KEY = None

# 주요 기업 매핑 테이블 (정확한 매칭을 위해)
MAJOR_COMPANIES = {
    '삼성전자': '삼성전자주식회사',
    '현대자동차': '현대자동차주식회사', 
    'SK하이닉스': 'SK하이닉스주식회사',
    'LG전자': 'LG전자주식회사',
    'NAVER': '네이버주식회사',
    '카카오': '주식회사카카오',
    '포스코': '포스코홀딩스주식회사',
    '삼성SDI': '삼성SDI주식회사',
    'LG화학': 'LG화학주식회사',
    '현대모비스': '현대모비스주식회사',
    'KB금융': 'KB금융지주주식회사',
    '신한지주': '신한지주주식회사',
    'SK': 'SK주식회사',
    'LG': 'LG주식회사'
}

# AWS Secrets Manager에서만 API 키 로드
try:
    if BOTO_AVAILABLE:
        try:
            region_name = os.getenv("AWS_REGION", "ap-northeast-2")
            session = boto3.session.Session()
            client = session.client(service_name='secretsmanager', region_name=region_name)

            # 1) 통합 시크릿(JSON) 우선: OPENCORPINSIGHT_SECRETS { DART_API_KEY, PERPLEXITY_API_KEY }
            for secret_name in ["OPENCORPINSIGHT_SECRETS", "DART_API_KEY", "PERPLEXITY_API_KEY"]:
                try:
                    resp = client.get_secret_value(SecretId=secret_name)
                except ClientError:
                    continue
                secret_string = resp.get('SecretString')
                if not secret_string:
                    continue
                s = secret_string.strip()
                if s.startswith('{'):
                    import json as _json
                    data = _json.loads(s)
                    API_KEY = API_KEY or data.get('DART_API_KEY') or data.get('dart_api_key')
                    PERPLEXITY_API_KEY = PERPLEXITY_API_KEY or data.get('PERPLEXITY_API_KEY') or data.get('perplexity_api_key')
                else:
                    if secret_name == "DART_API_KEY" and not API_KEY:
                        API_KEY = s
                    if secret_name == "PERPLEXITY_API_KEY" and not PERPLEXITY_API_KEY:
                        PERPLEXITY_API_KEY = s
            if API_KEY:
                logger.info("DART API 키를 AWS Secrets Manager에서 로드했습니다")
            if PERPLEXITY_API_KEY:
                logger.info("PERPLEXITY_API_KEY를 AWS Secrets Manager에서 로드했습니다")
        except Exception as e:
            logger.warning(f"Secrets Manager 처리 중 예외: {e}")
    if not API_KEY:
        logger.error("DART API 키 로드 실패: AWS Secrets Manager에 키를 저장해 주세요")
    if not PERPLEXITY_API_KEY:
        logger.warning("PERPLEXITY_API_KEY 미설정: 뉴스 관련 도구가 제한될 수 있습니다")
except Exception as e:
    logger.warning(f"초기화 중 예외: {e}")

# MCP 서버 생성 및 초기화
app = Server("OpenCorpInsight")

# Perplexity MCP 검색 함수 (실제 API 호출)
async def perplexity_search_wrapper(query: str, recency_filter: Optional[str] = None):
    """Perplexity API를 통해 JSON 뉴스 목록을 받아 반환합니다.
    반환 형식: {"articles": [{"title":...,"content":...,"url":...,"source":...,"published_date":"YYYY-MM-DD"}, ...]}
    """
    try:
        if not PERPLEXITY_API_KEY:
            logger.warning("PERPLEXITY_API_KEY 미설정 - Mock으로 대체될 수 있습니다")
            return {"articles": []}
        period_map = {'day': '지난 24시간', 'week': '지난 7일', 'month': '지난 30일'}
        period_text = period_map.get(recency_filter or '', '최근')

        api_url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "X-API-Key": PERPLEXITY_API_KEY,
            "Content-Type": "application/json"
        }
        prompt = (
            "아래 질의에 대해 한국어 뉴스 10건을 JSON 객체로만 반환하세요. 키는 'articles'이며, 각 항목은 "
            "{title, content, url, source, published_date(YYYY-MM-DD)} 필드를 포함합니다. 추가 설명/서문 금지.\n"
            f"질의: {query} 관련 {period_text} 최신 뉴스"
        )
        body = {
            "model": "sonar-small-online",
            "messages": [
                {"role": "system", "content": "너는 뉴스 수집기이다. 반드시 JSON만 반환한다."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 800,
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(api_url, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"Perplexity API 호출 실패: {resp.status_code} {resp.text[:200]}")
            return {"articles": []}
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and 'articles' in parsed:
                return parsed
        except Exception:
            pass
        return {"articles": []}
    except Exception as e:
        logger.error(f"Perplexity 검색 오류: {e}")
        return {"articles": []}

# 뉴스 분석기에 Perplexity 검색 함수 연결 (Secrets 키 필요)
try:
    if PERPLEXITY_API_KEY:
        news_analyzer.set_perplexity_search_function(perplexity_search_wrapper)
        logger.info("뉴스 분석기에 Perplexity 검색 함수가 연결되었습니다")
    else:
        logger.warning("PERPLEXITY_API_KEY 미설정 - 뉴스 도구 비활성화")
except Exception:
    logger.warning("Perplexity 검색 함수 연결 실패")

async def get_corp_code(corp_name: str) -> str:
    """기업 고유번호 조회"""
    # 디버깅 정보 추가
    logger.info(f"get_corp_code 호출됨 - corp_name: {corp_name}")
    logger.info(f"현재 API_KEY 상태: {API_KEY[:10] if API_KEY else 'None'}...")
    logger.info(f"API_KEY 타입: {type(API_KEY)}")
    
    if not API_KEY:
        raise ValueError("API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")
    
    # 캐시에서 먼저 확인
    if corp_name in CORP_CODE_CACHE:
        return CORP_CODE_CACHE[corp_name]
    
    # 주요 기업 매핑 확인
    search_name = MAJOR_COMPANIES.get(corp_name, corp_name)
    if search_name != corp_name:
        logger.info(f"주요 기업 매핑 사용: {corp_name} -> {search_name}")
        # 매핑된 이름도 캐시에서 확인
        if search_name in CORP_CODE_CACHE:
            CORP_CODE_CACHE[corp_name] = CORP_CODE_CACHE[search_name]
            return CORP_CODE_CACHE[search_name]
    
    # corpCode API 호출
    zip_url = f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={API_KEY}'
    resp = requests.get(zip_url, timeout=20)
    if resp.status_code != 200:
        raise ValueError(f"고유번호 목록 요청 실패: HTTP {resp.status_code}")
    zip_bytes = resp.content

    bio = io.BytesIO(zip_bytes)
    if not zipfile.is_zipfile(bio):
        # DART가 오류 JSON/문자열을 반환했을 수 있으므로 메시지 추출 시도
        try:
            j = resp.json(); status = j.get('status'); msg = j.get('message')
            raise ValueError(f"고유번호 조회 오류: {status} {msg}")
        except Exception:
            text_snippet = zip_bytes[:200].decode('utf-8', errors='ignore')
            raise ValueError(f"고유번호 ZIP 아님 응답: {text_snippet}")
    bio.seek(0)
    with zipfile.ZipFile(bio) as zf:
        corp_bytes = zf.read('CORPCODE.xml')
        try:
            xml_str = corp_bytes.decode('euc-kr')
        except UnicodeDecodeError:
            xml_str = corp_bytes.decode('utf-8')
    
    root = ET.fromstring(xml_str)
    
    # 정확한 매칭을 위한 후보 목록 (상장사만 허용)
    exact_matches = []
    partial_matches = []
    
    for item in root.findall('.//list'):
        name = item.find('corp_name').text
        code = item.find('corp_code').text
        stock_code = (item.find('stock_code').text or '').strip()
        if not stock_code:
            continue  # 비상장(E 등) 제외
        
        # 정확한 매칭 우선 (원래 이름과 매핑된 이름 모두 확인)
        if (name == corp_name or name == search_name or 
            name == corp_name + "주식회사" or name == "주식회사" + corp_name or
            name == search_name + "주식회사" or name == "주식회사" + search_name):
            exact_matches.append((name, code))
        # 부분 매칭 (원래 이름과 매핑된 이름 모두 확인)
        elif corp_name in name or search_name in name:
            partial_matches.append((name, code))
    
    # 정확한 매칭이 있으면 우선 선택
    if exact_matches:
        # 가장 짧은 이름 선택 (본사 우선)
        best_match = min(exact_matches, key=lambda x: len(x[0]))
        CORP_CODE_CACHE[corp_name] = best_match[1]
        logger.info(f"정확한 매칭(상장사) 발견: {corp_name} -> {best_match[0]} ({best_match[1]})")
        return best_match[1]
    
    # 부분 매칭에서 가장 적합한 것 선택
    if partial_matches:
        # 특정 키워드가 포함된 것 제외 (서비스, 써비스, 자회사 등)
        filtered_matches = []
        exclude_keywords = ['서비스', '써비스', '케이', 'CS', '씨에스', '에스']
        
        for name, code in partial_matches:
            if not any(keyword in name for keyword in exclude_keywords):
                filtered_matches.append((name, code))
        
        if filtered_matches:
            # 가장 짧은 이름 선택 (본사 우선)
            best_match = min(filtered_matches, key=lambda x: len(x[0]))
            CORP_CODE_CACHE[corp_name] = best_match[1]
            logger.info(f"필터링된 매칭(상장사) 발견: {corp_name} -> {best_match[0]} ({best_match[1]})")
            return best_match[1]
        else:
            # 필터링 후에도 결과가 없으면 실패 처리(비상장 제외 정책)
            raise ValueError(f"상장 기업 '{corp_name}'을(를) 찾을 수 없습니다. 정확한 상장사 명칭/티커를 사용해 주세요.")
    
    raise ValueError(f"기업 '{corp_name}'을 찾을 수 없습니다.")

# API 키 설정 함수
async def set_dart_api_key(api_key: str) -> List[types.TextContent]:
    """DART API 키 설정"""
    global API_KEY
    API_KEY = api_key
    logger.info(f"API 키 설정됨: {API_KEY[:10]}...")
    return [types.TextContent(type="text", text=f"✅ DART API 키가 설정되었습니다: {api_key[:10]}...")]

# corp_code 해석 유틸: 프론트가 corp_code를 직접 넘기면 그대로 사용
def resolve_corp_code_arg(corp_name: Optional[str] = None, corp_code: Optional[str] = None) -> str:
    if corp_code:
        return corp_code
    if not corp_name:
        raise ValueError("corp_code 또는 corp_name 중 하나는 반드시 필요합니다.")
    return asyncio.get_event_loop().run_until_complete(get_corp_code(corp_name))

# 기업 정보 조회
async def get_company_info(corp_name: Optional[str] = None, corp_code: Optional[str] = None) -> List[types.TextContent]:
    """기업 정보 조회 (corp_code 우선)"""
    try:
        corp_code = corp_code or (await get_corp_code(corp_name))
        
        url = 'https://opendart.fss.or.kr/api/company.json'
        params = {
            'crtfc_key': API_KEY,
            'corp_code': corp_code
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data['status'] != '000':
            return [types.TextContent(type="text", text=f"오류: {data['message']}")]
        
        info = data
        display_name = corp_name or info.get('corp_name', 'N/A')
        result = f"""
## {display_name} 기업 정보

- **회사명**: {info.get('corp_name', 'N/A')}
- **대표자명**: {info.get('ceo_nm', 'N/A')}
- **설립일**: {info.get('est_dt', 'N/A')}
- **주소**: {info.get('adres', 'N/A')}
- **홈페이지**: {info.get('hm_url', 'N/A')}
- **업종**: {info.get('bizr_no', 'N/A')}
"""
        
        return [types.TextContent(type="text", text=result)]
        
    except Exception as e:
        return [types.TextContent(type="text", text=f"기업 정보 조회 중 오류 발생: {str(e)}")]

# 재무제표 조회
async def get_financial_statements(corp_name: Optional[str], bsns_year: str, reprt_code: str, fs_div: str, statement_type: str, corp_code: Optional[str] = None) -> List[types.TextContent]:
    """재무제표 조회 (corp_code 우선)"""
    try:
        corp_code = corp_code or (await get_corp_code(corp_name))
        # corp_name이 없으면 회사명 보강
        display_name = corp_name
        if not display_name:
            try:
                info = requests.get('https://opendart.fss.or.kr/api/company.json', params={'crtfc_key': API_KEY, 'corp_code': corp_code}).json()
                if info.get('status') == '000':
                    display_name = info.get('corp_name')
            except Exception:
                pass
        logger.info(f"재무제표 조회 시작: {display_name or corp_code} ({corp_code}) - {bsns_year}년 {statement_type}")

        # 공시검색으로 우선순위 결정: pblntf_ty A(정기/사업보고서 우선) → F(감사보고서)
        def _prefer_report_code(corp_code: str, year: str) -> Optional[tuple[str, str]]:
            try:
                base_params = {
                    'crtfc_key': API_KEY,
                    'corp_code': corp_code,
                    'bgn_de': f"{year}0101",
                    'end_de': f"{year}1231",
                    'page_count': 100
                }
                # 1) A 우선
                params_a = dict(base_params); params_a['pblntf_ty'] = 'A'
                res_a = requests.get('https://opendart.fss.or.kr/api/list.json', params=params_a).json()
                if res_a.get('status') == '000' and any('사업보고서' in (it.get('report_nm','')) for it in (res_a.get('list') or [])):
                    return ('11014', 'A')
                # 2) F (감사보고서)
                params_f = dict(base_params); params_f['pblntf_ty'] = 'F'
                res_f = requests.get('https://opendart.fss.or.kr/api/list.json', params=params_f).json()
                if res_f.get('status') == '000' and any('감사보고서' in (it.get('report_nm','')) for it in (res_f.get('list') or [])):
                    return ('11014', 'F')  # 연간 기준으로 11014 우선 시도
            except Exception:
                pass
            return None

        pref = _prefer_report_code(corp_code, bsns_year)
        preferred_code, preferred_source = (pref[0], pref[1]) if pref else (None, None)

        # 요청된 보고서 코드
        requested_code = reprt_code

        # 공시 우선 탐지 실패 시 처리
        # - 연간(11014) 요청이면 실패 즉시 반환(이전 정책 유지)
        # - 분기/반기(11013/11012/11011) 요청이면 탐지 없어도 진행 허용
        if not preferred_code and requested_code == '11014':
            msg = f"## {display_name or corp_code} {bsns_year}년 재무제표 조회 실패\n\n❌ **데이터 없음**: 정기(A)·감사(F) 공시에서 해당 연도 보고서가 탐지되지 않았습니다.\n\n🔎 공시 우선 탐지: 없음\n"
            return [types.TextContent(type="text", text=msg)]

        # 보고서 코드 목록 구성
        def unique(seq: List[str]) -> List[str]:
            seen = set(); out = []
            for x in seq:
                if x not in seen and x is not None:
                    seen.add(x); out.append(x)
            return out
        if requested_code in ['11013','11012','11011']:
            # 분기/반기 요청: 요청 코드 우선, 그 외 분기 코드를 보조 순서로 시도
            quarterly_order = ['11013','11012','11011']
            report_codes = [requested_code] + [c for c in quarterly_order if c != requested_code]
        else:
            # 연간 요청: 우선 탐지 코드(있으면) → 11014만 시도
            report_codes = ['11014'] if requested_code == '11014' else unique([requested_code, preferred_code])
        fs_divisions = unique([fs_div, 'CFS', 'OFS'])

        best_result = None
        attempted_combinations: List[str] = []

        for rcode in report_codes:
            for fsdiv in fs_divisions:
                try:
                    url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
                    params = {
                        'crtfc_key': API_KEY,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': rcode,
                        'fs_div': fsdiv
                    }

                    combo = f"{rcode}-{fsdiv}"
                    attempted_combinations.append(combo)
                    logger.info(f"시도 중: {rcode} ({_get_report_name(rcode)}) - {fsdiv}")

                    response = requests.get(url, params=params)
                    data = response.json()

                    if data.get('status') == '000' and 'list' in data:
                        df = pd.DataFrame(data['list'])
                        if df.empty:
                            continue
                        # 요청한 재무제표 타입 찾기
                        statement_df = df[df['sj_nm'] == statement_type].copy()

                        if not statement_df.empty:
                            amount_cols = [c for c in ['thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount'] if c in statement_df.columns]
                            if amount_cols:
                                result_df = statement_df[['account_nm', *amount_cols]].rename(columns={
                                    'account_nm': '계정',
                                    'thstrm_amount': '당기',
                                    'frmtrm_amount': '전기',
                                    'bfefrmtrm_amount': '전전기'
                                })
                                report_name = _get_report_name(rcode)
                                fs_name = "연결" if fsdiv == "CFS" else "별도"
                                prefer_text = f" (공시기반 우선: {'정기(A)' if preferred_source=='A' else '감사(F)'} 감지)" if preferred_source else ""
                                result = f"""
## {display_name or corp_code} {bsns_year}년 {statement_type} ({report_name}, {fs_name}){prefer_text}

{result_df.to_string(index=False)}

📊 **데이터 정보**
- 보고서: {report_name} ({rcode})
- 재무제표: {fs_name} ({fsdiv})
- 항목 수: {len(result_df)}개
"""
                                logger.info(f"재무제표 조회 성공: {rcode}-{fsdiv}, {len(result_df)}개 항목")
                                return [types.TextContent(type="text", text=result)]
                        else:
                            # 표준 API에서 비어있으면 XBRL 백업 시도 (모든 재무제표 유형)
                            xbrl_info = _detect_report_rcept_no(corp_code, bsns_year)
                            if xbrl_info:
                                rcept_no, src = xbrl_info
                                xdf = _try_fetch_statement_from_xbrl(rcept_no, statement_type)
                                if xdf is not None and not xdf.empty:
                                    report_name = '사업/감사(XBRL)'
                                    fs_name = '연결/별도 식별불가'
                                    prefer_text = f" (공시기반 우선: {'정기(A)' if src=='A' else '감사(F)'} 감지)"
                                    result = f"""
## {display_name or corp_code} {bsns_year}년 {statement_type} ({report_name}, {fs_name}){prefer_text}

{xdf.to_string(index=False)}

📊 **데이터 정보**
- 소스: XBRL 파싱 (rcept_no={rcept_no})
- 항목 수: {len(xdf)}개
"""
                                    return [types.TextContent(type="text", text=result)]

                        # 다른 재무제표 타입들도 확인
                        available_statements = df['sj_nm'].unique().tolist()
                        if available_statements and not best_result:
                            best_result = {
                                'corp_name': display_name or corp_code,
                                'year': bsns_year,
                                'report_code': rcode,
                                'fs_div': fsdiv,
                                'available_statements': available_statements,
                                'total_records': len(df)
                            }

                except Exception as e:
                    logger.warning(f"조회 실패 ({rcode}-{fsdiv}): {e}")
                    continue

        # 비상장 및 비표준 문서 우회(XBRL/PDF) 비활성화 정책
        # 상장사 단일계정 API 기준만 사용

        # 데이터를 찾지 못한 경우
        unique_attempts = unique(attempted_combinations)
        if best_result:
            result = f"""
## {best_result.get('corp_name')} {bsns_year}년 재무제표 조회 결과

❌ **요청한 재무제표 없음**: {statement_type}

✅ **사용 가능한 재무제표**:
{chr(10).join([f"- {stmt}" for stmt in best_result['available_statements']])}

📋 **조회 정보**:
- 보고서: {_get_report_name(best_result['report_code'])}
- 재무제표 구분: {"연결" if best_result['fs_div'] == "CFS" else "별도"}
- 총 데이터 수: {best_result['total_records']}개

🔎 공시 우선 탐지: {('정기(A)' if preferred_source=='A' else '감사(F)') if preferred_source else '없음'}
"""
        else:
            result = f"""
## {display_name or corp_code} {bsns_year}년 재무제표 조회 실패

❌ **데이터 없음**: 해당 기업의 {bsns_year}년 재무제표 데이터를 찾을 수 없습니다.

🔎 공시 우선 탐지: {('정기(A)' if preferred_source=='A' else '감사(F)') if preferred_source else '없음'}
🔍 **시도한 조합**: {', '.join(unique_attempts)}

💡 **가능한 원인**:
- 해당 연도의 공시 데이터가 아직 등록되지 않음
- 기업이 해당 연도에 공시 의무가 없었음
- 다른 연도 (예: {int(bsns_year)-1}년, {int(bsns_year)-2}년)의 데이터는 있을 수 있음

🔄 **대안**: 다른 연도로 조회하거나 DART 전자공시시스템에서 직접 확인해보세요.
"""

        return [types.TextContent(type="text", text=result)]

    except Exception as e:
        return [types.TextContent(type="text", text=f"재무제표 조회 중 오류 발생: {str(e)}")]

# 추가 기능: 재무비율 계산
async def get_financial_ratios(corp_name: Optional[str], bsns_year: str, ratio_categories: List[str], include_industry_avg: bool, corp_code: Optional[str] = None) -> List[types.TextContent]:
    """재무비율 계산 및 조회 (ROE, ROA, 부채비율, 유동비율 등)
    - 계정명/표 양식 편차를 고려해 다중 패턴 및 포괄손익계산서까지 탐색
    - (1,234) 형식 음수 처리, '-' 무시 처리
    - 연간 보고서(CFS) 기준, 필요 시 다른 조합으로 보조 조회
    """
    try:
        corp_code = corp_code or (await get_corp_code(corp_name))

        def parse_amount(val: str) -> float:
            if not val or val == '-':
                return 0.0
            s = str(val).replace(',', '').strip()
            neg = s.startswith('(') and s.endswith(')')
            if neg:
                s = s[1:-1]
            try:
                num = float(s)
            except Exception:
                return 0.0
            return -num if neg else num

        def fetch_df(reprt_code: str, fs_div: str) -> pd.DataFrame:
            url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
            params = {
                'crtfc_key': API_KEY,
                'corp_code': corp_code,
                'bsns_year': bsns_year,
                'reprt_code': reprt_code,
                'fs_div': fs_div,
            }
            resp = requests.get(url, params=params)
            j = resp.json()
            if j.get('status') != '000':
                return pd.DataFrame()
            return pd.DataFrame(j.get('list', []))

        # 우선 조합들: 연간/연결 → 연간/별도 → 3분기/연결
        tried: List[tuple[str, str]] = [('11014', 'CFS'), ('11014', 'OFS'), ('11013', 'CFS')]
        df = pd.DataFrame()
        for rc, fd in tried:
            df = fetch_df(rc, fd)
            if not df.empty:
                break
        if df.empty:
            return [types.TextContent(type='text', text='재무 데이터가 없습니다. 연도/보고서 코드를 변경해 다시 시도해주세요.')]

        def get_value(sj_candidates: List[str], account_patterns: List[str]) -> float:
            target = df[df['sj_nm'].isin(sj_candidates)] if 'sj_nm' in df.columns else df
            if target.empty:
                return 0.0
            for pattern in account_patterns:
                try:
                    m = target[target['account_nm'].str.contains(pattern, na=False, regex=True)]
                except Exception:
                    continue
                if not m.empty:
                    # thstrm 우선, 없으면 과거 항목 보조 조회
                    for col in ['thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount']:
                        if col in m.columns:
                            val = m.iloc[0][col]
                            amt = parse_amount(val)
                            if amt != 0.0:
                                return amt
            return 0.0

        # 계정 추출
        total_assets = get_value(['재무상태표'], ['자산총계'])
        total_equity = get_value(['재무상태표'], ['자본총계'])
        total_liabilities = get_value(['재무상태표'], ['부채총계'])
        current_assets = get_value(['재무상태표'], ['유동자산'])
        current_liabilities = get_value(['재무상태표'], ['유동부채'])

        revenue = get_value(['손익계산서', '포괄손익계산서'], ['매출액', '수익\(매출액\)', '영업수익'])
        operating_profit = get_value(['손익계산서', '포괄손익계산서'], ['영업이익'])
        net_profit = get_value(['손익계산서', '포괄손익계산서'], [
            '당기순이익', '당기순이익\(손실\)', '지배주주지분\s*순이익', '지배기업\s*소유주지분\s*순이익', '연결당기순이익'
        ])

        ratios: Dict[str, Dict[str, float]] = {}
        if 'profitability' in ratio_categories:
            ratios['profitability'] = {}
            if total_equity > 0 and net_profit != 0:
                ratios['profitability']['ROE'] = round((net_profit / total_equity) * 100, 2)
            if total_assets > 0 and net_profit != 0:
                ratios['profitability']['ROA'] = round((net_profit / total_assets) * 100, 2)
            if revenue > 0:
                ratios['profitability']['영업이익률'] = round((operating_profit / revenue) * 100, 2)
                if net_profit != 0:
                    ratios['profitability']['순이익률'] = round((net_profit / revenue) * 100, 2)
        if 'stability' in ratio_categories:
            ratios['stability'] = {}
            if total_equity > 0 and total_liabilities >= 0:
                ratios['stability']['부채비율'] = round((total_liabilities / total_equity) * 100, 2)
            if current_liabilities > 0:
                ratios['stability']['유동비율'] = round((current_assets / current_liabilities) * 100, 2)
            if total_assets > 0 and total_equity >= 0:
                ratios['stability']['자기자본비율'] = round((total_equity / total_assets) * 100, 2)
        if 'activity' in ratio_categories and total_assets > 0 and revenue > 0:
            ratios.setdefault('activity', {})['총자산회전율'] = round(revenue / total_assets, 2)

        # 결과 구성
        result = f"## {corp_name} {bsns_year}년 재무비율 분석\n\n"
        names = {'profitability': '수익성 지표', 'stability': '안정성 지표', 'activity': '활동성 지표', 'growth': '성장성 지표'}
        for cat, vals in ratios.items():
            result += f"### {names.get(cat, cat)}\n\n"
            for k, v in vals.items():
                suffix = '%' if k not in ['총자산회전율'] else ''
                result += f"- **{k}**: {v}{suffix}\n"
            result += "\n"
        if not ratios:
            result += "- 유효한 지표를 계산할 수 없습니다. 연도/보고서 코드를 변경하거나 다른 재무제표 구분을 시도해 주세요.\n"
        return [types.TextContent(type='text', text=result)]
    except Exception as e:
        return [types.TextContent(type='text', text=f"재무비율 조회 중 오류 발생: {str(e)}")]

# 추가 기능: 시계열 분석 (래퍼)
async def analyze_time_series(corp_name: str, analysis_period: int, metrics: List[str], forecast_periods: int) -> List[types.TextContent]:
    """기업의 재무 성과 시계열 분석을 수행합니다
    - 첫 호출에서 실제 DART 데이터를 연도별로 수집하여 사용(연간 보고서 기준)
    - 매출액/영업이익/순이익을 최근 N년 수집, 누락 년도는 건너뜀
    """
    try:
        if not API_KEY:
            return [types.TextContent(type='text', text='❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.')]

        corp_code = await get_corp_code(corp_name)
        # 최근 analysis_period년 (올해-1 기준) 역산 수집
        end_year = datetime.now().year - 1
        years = list(range(end_year - analysis_period + 1, end_year + 1))

        def parse_amount(val: str) -> float:
            if not val or val == '-':
                return 0.0
            s = str(val).replace(',', '').strip()
            neg = s.startswith('(') and s.endswith(')')
            if neg:
                s = s[1:-1]
            try:
                num = float(s)
            except Exception:
                return 0.0
            return -num if neg else num

        def fetch_year(year: int) -> dict:
            url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
            params = {'crtfc_key': API_KEY,'corp_code': corp_code,'bsns_year': str(year),'reprt_code': '11014','fs_div': 'CFS'}
            j = requests.get(url, params=params).json()
            if j.get('status') != '000':
                return {}
            df = pd.DataFrame(j.get('list', []))
            if df.empty:
                return {}
            def get_value(sj_candidates, patterns):
                target = df[df['sj_nm'].isin(sj_candidates)] if 'sj_nm' in df.columns else df
                for pattern in patterns:
                    try:
                        m = target[target['account_nm'].str.contains(pattern, na=False, regex=True)]
                    except Exception:
                        m = pd.DataFrame()
                    if not m.empty:
                        for col in ['thstrm_amount','frmtrm_amount','bfefrmtrm_amount']:
                            if col in m.columns:
                                amt = parse_amount(m.iloc[0][col])
                                if amt != 0.0:
                                    return amt
                if 'account_id' in target.columns:
                    for pid in ['Revenue','Sales','OperatingIncome','ProfitLoss','NetIncome', 'ProfitLossAttributableToOwnersOfParent']:
                        m2 = target[target['account_id'].str.contains(pid, na=False)]
                        if not m2.empty:
                            for col in ['thstrm_amount','frmtrm_amount','bfefrmtrm_amount']:
                                if col in m2.columns:
                                    amt = parse_amount(m2.iloc[0][col])
                                    if amt != 0.0:
                                        return amt
                return 0.0
            revenue = get_value(['손익계산서','포괄손익계산서'], ['매출액','수익\(매출액\)','영업수익'])
            operating = get_value(['손익계산서','포괄손익계산서'], ['영업이익'])
            net = get_value(['손익계산서','포괄손익계산서'], ['당기순이익','당기순이익\(손실\)','지배주주지분\s*순이익','지배기업\s*소유주지분\s*순이익','연결당기순이익'])
            return {'year': year, '매출액': revenue, '영업이익': operating, '순이익': net}

        collected = [fetch_year(y) for y in years]
        collected = [c for c in collected if c]
        if not collected:
            return [types.TextContent(type='text', text='시계열 데이터가 없습니다. 다른 기간으로 다시 시도해주세요.')]

        dates = [f"{c['year']}-12-31" for c in collected]
        financial_data = {
            'dates': dates,
            '매출액': [c['매출액'] for c in collected],
            '영업이익': [c['영업이익'] for c in collected],
            '순이익': [c['순이익'] for c in collected],
        }

        trend_result = await time_series_analyzer.analyze_financial_trends(corp_name, financial_data, len(collected), metrics)
        forecast_result = await time_series_analyzer.forecast_performance(corp_name, financial_data, forecast_periods, metrics)

        text = f"""# 📈 {corp_name} 시계열 분석 결과

## 📊 분석 개요
- **분석 기간**: {len(collected)}년 (연간)
- **분석 지표**: {', '.join(metrics)}
- **데이터 포인트**: {trend_result.get('data_points', 0)}개
- **예측 기간**: {forecast_periods}분기
"""
        for metric, analysis in (trend_result.get('trend_results', {}) or {}).items():
            basic = analysis.get('basic_stats', {})
            trend = analysis.get('trend_analysis', {})
            text += f"\n### {metric}\n- **평균값**: {basic.get('mean', 0):,.1f}\n- **성장률 (CAGR)**: {basic.get('growth_rate', {}).get('cagr', 0):.1f}%\n- **트렌드 방향**: {trend.get('direction', 'N/A')}\n- **트렌드 강도**: {trend.get('strength', 0):.2f}\n"
        return [types.TextContent(type='text', text=text)]
    except Exception as e:
        logger.error(f"시계열 분석 중 오류: {e}")
        return [types.TextContent(type='text', text=f"❌ 시계열 분석 중 오류가 발생했습니다: {str(e)}")]

# 추가 기능: 업계 벤치마크 비교 (래퍼)
async def compare_with_industry(corp_name: str, industry: str, comparison_metrics: List[str], analysis_type: str) -> List[types.TextContent]:
    """기업을 동종 업계와 벤치마크 비교합니다 (실데이터 표 출력)"""
    try:
        if not API_KEY:
            return [types.TextContent(type='text', text='❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.')]

        result = await benchmark_analyzer.compare_with_industry(corp_name, industry, comparison_metrics)
        bench = result.get('benchmark_results', {}) or {}
        companies = list(bench.keys())

        # 표 구성: 지표 행, 기업 열
        rows = []
        metric_order = [
            '매출액', '영업이익', '순이익', 'ROE', 'ROA', '부채비율', '유동비율', '영업이익률'
        ]
        # 요청 지표 우선 배치
        ordered_metrics = [m for m in metric_order if m in set(comparison_metrics + metric_order)]

        header = "| 지표 |" + " ".join(f"{c} |" for c in companies)
        sep = "|------|" + ("------|" * len(companies))
        table = [header, sep]
        for m in ordered_metrics:
            row = [f"| **{m}** |"]
            for c in companies:
                v = bench.get(c, {}).get(m)
                if v is None:
                    row.append(" - |")
                else:
                    if m in ['매출액', '영업이익', '순이익']:
                        row.append(f" {v:,.1f}억원 |")
                    elif m in ['ROE', 'ROA', '부채비율', '유동비율', '영업이익률']:
                        row.append(f" {v:.2f}% |")
                    else:
                        row.append(f" {v} |")
            table.append("".join(row))

        text = f"""# 🏆 {corp_name} 업계 벤치마크 비교

## 📊 비교 개요
- **업종**: {industry}
- **비교 지표**: {', '.join(comparison_metrics)}
- **분석 유형**: {analysis_type.title()}

## 📋 지표별 비교 결과
""" + "\n".join(table)
        return [types.TextContent(type='text', text=text)]
    except Exception as e:
        logger.error(f"벤치마크 비교 중 오류: {e}")
        return [types.TextContent(type='text', text=f"❌ 벤치마크 비교 중 오류가 발생했습니다: {str(e)}")]

# 추가 기능: 공시 목록 조회
async def get_disclosure_list(corp_name: Optional[str], bgn_de: str, end_de: str, page_count: int, corp_code: Optional[str] = None) -> List[types.TextContent]:
    """공시 목록 조회 (corp_code 우선)"""
    try:
        corp_code = corp_code or (await get_corp_code(corp_name))
        url = 'https://opendart.fss.or.kr/api/list.json'
        params = {
            'crtfc_key': API_KEY,
            'corp_code': corp_code,
            'bgn_de': bgn_de,
            'end_de': end_de,
            'page_count': page_count,
        }
        response = requests.get(url, params=params)
        data = response.json()
        if data.get('status') != '000':
            return [types.TextContent(type="text", text=f"오류: {data.get('message', '알 수 없는 오류')}")]
        disclosures = data.get('list', [])
        result = f"## {corp_name} 공시 목록 ({bgn_de} ~ {end_de})\n\n"
        for disclosure in disclosures:
            result += f"- **{disclosure.get('report_nm','')}** ({disclosure.get('rcept_dt','')})\n"
            result += f"  - 접수번호: {disclosure.get('rcept_no','')}\n"
            result += f"  - 제출인: {disclosure.get('flr_nm','')}\n\n"
        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"공시 목록 조회 중 오류 발생: {str(e)}")]

# 추가 기능: 기업 간 재무지표 비교
async def compare_financials(companies: List[str], bsns_year: str, comparison_metrics: List[str], visualization: bool = True, corp_codes: Optional[List[str]] = None) -> List[types.TextContent]:
    """여러 기업의 재무지표를 비교
    - 한글/영문 지표명을 모두 허용하고 내부 표준 키로 정규화
    - 다중 보고서 조합 및 포괄손익계산서까지 탐색하여 누락 최소화
    """
    try:
        # 1) 지표 정규화
        metric_alias = {
            '매출액': 'revenue', 'revenue': 'revenue',
            '영업이익': 'operating_profit', 'operating_profit': 'operating_profit',
            '순이익': 'net_profit', 'net_profit': 'net_profit',
            'ROE': 'roe', 'roe': 'roe',
            '부채비율': 'debt_ratio', 'debt_ratio': 'debt_ratio',
            '영업이익률': 'operating_margin', 'operating_margin': 'operating_margin',
        }
        normalized = [metric_alias.get(m, m) for m in comparison_metrics]
        wanted = set(normalized)

        # 2) 헬퍼: 데이터 획득
        def parse_amount(val: str) -> float:
            if not val or val == '-':
                return 0.0
            s = str(val).replace(',', '').strip()
            neg = s.startswith('(') and s.endswith(')')
            if neg:
                s = s[1:-1]
            try:
                num = float(s)
            except Exception:
                return 0.0
            return -num if neg else num

        def fetch_df(corp_code: str, reprt_code: str, fs_div: str) -> pd.DataFrame:
            url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
            params = {'crtfc_key': API_KEY,'corp_code': corp_code,'bsns_year': bsns_year,'reprt_code': reprt_code,'fs_div': fs_div}
            j = requests.get(url, params=params).json()
            if j.get('status') != '000':
                return pd.DataFrame()
            return pd.DataFrame(j.get('list', []))

        def get_value(df: pd.DataFrame, sj_candidates: List[str], patterns: List[str]) -> float:
            target = df[df['sj_nm'].isin(sj_candidates)] if 'sj_nm' in df.columns else df
            if target.empty:
                return 0.0
            # 1) 계정명으로 우선 매칭
            for pattern in patterns:
                try:
                    m = target[target['account_nm'].str.contains(pattern, na=False, regex=True)]
                except Exception:
                    m = pd.DataFrame()
                if not m.empty:
                    for col in ['thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount']:
                        if col in m.columns:
                            amt = parse_amount(m.iloc[0][col])
                            if amt != 0.0:
                                return amt
            # 2) account_id로 보조 매칭 (IFRS 표준 코드)
            if 'account_id' in target.columns:
                id_patterns = ['ProfitLoss', 'NetIncome', 'ComprehensiveIncome', 'ProfitLossAttributableToOwnersOfParent']
                for pid in id_patterns:
                    m2 = target[target['account_id'].str.contains(pid, na=False, regex=False)]
                    if not m2.empty:
                        for col in ['thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount']:
                            if col in m2.columns:
                                amt = parse_amount(m2.iloc[0][col])
                                if amt != 0.0:
                                    return amt
            return 0.0

        # 3) 각 회사별 수집/계산
        comparison_data: Dict[str, Dict[str, Any]] = {}
        for idx, company in enumerate(companies):
            try:
                corp_code = (corp_codes[idx] if corp_codes and idx < len(corp_codes) and corp_codes[idx] else None) or (await get_corp_code(company))
                df = pd.DataFrame()
                for rc, fd in [('11014','CFS'), ('11014','OFS'), ('11013','CFS')]:
                    df = fetch_df(corp_code, rc, fd)
                    if not df.empty:
                        break
                if df.empty:
                    comparison_data[company] = {'오류': '데이터 없음'}
                    continue

                total_assets = get_value(df, ['재무상태표'], ['자산총계'])
                total_equity = get_value(df, ['재무상태표'], ['자본총계'])
                total_liabilities = get_value(df, ['재무상태표'], ['부채총계'])
                revenue = get_value(df, ['손익계산서','포괄손익계산서'], ['매출액','수익\(매출액\)','영업수익'])
                operating_profit = get_value(df, ['손익계산서','포괄손익계산서'], ['영업이익'])
                net_profit = get_value(df, ['손익계산서','포괄손익계산서'], ['당기순이익','당기순이익\(손실\)','지배주주지분\s*순이익','지배기업\s*소유주지분\s*순이익','연결당기순이익'])

                metrics: Dict[str, Any] = {}
                if 'revenue' in wanted:
                    metrics['매출액'] = revenue / 100000000
                if 'operating_profit' in wanted:
                    metrics['영업이익'] = operating_profit / 100000000
                if 'net_profit' in wanted:
                    metrics['순이익'] = net_profit / 100000000
                if 'roe' in wanted and total_equity > 0 and net_profit != 0:
                    metrics['ROE'] = (net_profit / total_equity) * 100
                if 'debt_ratio' in wanted and total_equity > 0:
                    metrics['부채비율'] = (total_liabilities / total_equity) * 100
                if 'operating_margin' in wanted and revenue > 0:
                    metrics['영업이익률'] = (operating_profit / revenue) * 100
                comparison_data[company] = metrics
            except Exception as company_error:
                comparison_data[company] = {"오류": str(company_error)}

        # 4) 표 생성
        result = f"## 기업 재무지표 비교 ({bsns_year}년)\n\n"
        if not comparison_data:
            return [types.TextContent(type="text", text="비교할 수 있는 데이터가 없습니다.")]
        metrics_list = set()
        for d in comparison_data.values():
            if isinstance(d, dict):
                metrics_list.update(d.keys())
        metrics_list = [m for m in ['매출액','영업이익','순이익','ROE','부채비율','영업이익률'] if m in metrics_list]

        result += "| 지표 |" + " ".join(f"{c} |" for c in companies) + "\n"
        result += "|------|" + ("------|" * len(companies)) + "\n"
        for metric in metrics_list:
            result += f"| **{metric}** |"
            for company in companies:
                val = comparison_data.get(company, {}).get(metric)
                if val is None:
                    result += " - |"
                    continue
                if isinstance(val, float):
                    if metric in ['매출액','영업이익','순이익']:
                        result += f" {val:,.1f}억원 |"
                    elif metric in ['ROE','부채비율','영업이익률']:
                        result += f" {val:.2f}% |"
                    else:
                        result += f" {val:.2f} |"
                else:
                    result += f" {val} |"
            result += "\n"

        if visualization:
            # 간단한 차트 데이터(막대 그래프용) 포함
            chart = {
                'metrics': metrics_list,
                'series': {company: [comparison_data.get(company, {}).get(m) for m in metrics_list] for company in companies}
            }
            result += "\n### 시각화 데이터\n" + json.dumps(chart, ensure_ascii=False)
        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"재무지표 비교 중 오류 발생: {str(e)}")]

# 추가 기능: 뉴스/감성/이벤트 도구 래퍼
async def get_company_news(corp_name: str, search_period: str, news_categories: List[str], include_sentiment: bool) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        news_data = await news_analyzer.search_company_news(corp_name, search_period)
        result_text = f"""# 📰 {corp_name} 최근 뉴스 분석

## 📊 수집 정보
- **검색 기간**: {search_period}
- **수집된 기사**: {news_data.get('total_articles', 0)}개
- **데이터 출처**: {news_data.get('data_source', 'N/A')}
- **수집 시점**: {news_data.get('search_timestamp', 'N/A')}

## 📋 주요 뉴스
"""
        for i, article in enumerate(news_data.get('articles', [])[:5], 1):
            result_text += f"""### {i}. {article.get('title', 'N/A')}
- **발행일**: {article.get('published_date', 'N/A')}
- **출처**: {article.get('source', 'N/A')}
- **내용**: {article.get('content', 'N/A')[:200]}...

"""
        if include_sentiment:
            total_articles = len(news_data.get('articles', []))
            if total_articles > 0:
                positive_count = sum(1 for article in news_data.get('articles', []) if any(word in (article.get('title','') + article.get('content','')).lower() for word in ['성장','증가','상승','성공','긍정']))
                sentiment_ratio = positive_count / total_articles
                sentiment_summary = '긍정적' if sentiment_ratio > 0.6 else '부정적' if sentiment_ratio < 0.4 else '중립적'
                result_text += f"## 💭 감성 분석 요약\n- **전체 감성**: {sentiment_summary}\n- **긍정적 기사 비율**: {sentiment_ratio:.1%}\n"
        result_text += f"\n---\n*분석 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        return [types.TextContent(type="text", text=result_text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 뉴스 수집 중 오류가 발생했습니다: {str(e)}")]

async def analyze_news_sentiment(corp_name: str, search_period: str, analysis_depth: str) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        sentiment_result = await news_analyzer.analyze_company_news_sentiment(corp_name, search_period, analysis_depth)
        result_text = f"""# 💭 {corp_name} 뉴스 감성 분석 결과

## 📊 분석 개요
- **분석 기간**: {sentiment_result.get('analysis_period', 'N/A')}
- **분석 깊이**: {sentiment_result.get('analysis_depth', 'N/A')}
- **분석 기사 수**: {sentiment_result.get('total_articles_analyzed', 0)}개
- **평균 감성 점수**: {sentiment_result.get('average_sentiment_score', 0):.3f}

## 🎯 감성 분포
- **긍정**: {sentiment_result.get('sentiment_distribution', {}).get('positive', 0)}개
- **중립**: {sentiment_result.get('sentiment_distribution', {}).get('neutral', 0)}개
- **부정**: {sentiment_result.get('sentiment_distribution', {}).get('negative', 0)}개
"""
        for article in sentiment_result.get('article_sentiments', [])[:5]:
            result_text += f"""\n### {article.get('title', 'N/A')}
- **감성 점수**: {article.get('sentiment_score', 0):.3f}
- **감성 분류**: {article.get('sentiment_label', 'N/A')}
- **키워드**: {', '.join(article.get('detected_keywords', [])[:3])}
"""
        result_text += f"\n---\n*분석 완료: {sentiment_result.get('analysis_timestamp', 'N/A')}*\n*데이터 출처: {sentiment_result.get('data_source', 'N/A')}*\n"
        return [types.TextContent(type="text", text=result_text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 감성 분석 중 오류가 발생했습니다: {str(e)}")]

async def detect_financial_events(corp_name: str, monitoring_period: int, event_types: List[str]) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        events_result = await news_analyzer.detect_market_events(corp_name, monitoring_period)
        result_text = f"""# 🎯 {corp_name} 재무 이벤트 탐지 결과

## 📊 탐지 개요
- **모니터링 기간**: {events_result.get('monitoring_period_days', 0)}일
- **탐지된 이벤트**: {events_result.get('total_events_detected', 0)}개
- **이벤트 유형**: {', '.join(events_result.get('event_types_found', []))}

## 📋 이벤트 상세
"""
        for event_type, events in (events_result.get('event_summary', {}) or {}).items():
            event_name = event_type.replace('_', ' ').title()
            result_text += f"### {event_name}\n- **탐지 건수**: {len(events)}개\n"
            for event in events[:3]:
                result_text += f"  - {event.get('article_title','N/A')} ({event.get('article_date','N/A')})\n"
            result_text += "\n"
        if not events_result.get('event_summary'):
            result_text += "- 탐지된 이벤트가 없습니다.\n"
        result_text += f"\n---\n*탐지 완료: {events_result.get('detection_timestamp', 'N/A')}*\n*데이터 출처: {events_result.get('data_source', 'N/A')}*\n"
        return [types.TextContent(type="text", text=result_text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 이벤트 탐지 중 오류가 발생했습니다: {str(e)}")]

# 추가 기능: 투자 신호 및 리포트
async def generate_investment_signal(corp_name: str, analysis_period: int, weight_config: Dict[str, float], risk_tolerance: str) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        # 간소화: 건강성/뉴스/이벤트 데이터를 모아 점수화 (상세 로직은 backup 참고)
        # 여기서는 news_analyzer와 간단한 가중 합으로 대체
        sentiment = await news_analyzer.analyze_company_news_sentiment(corp_name, "week", "detailed")
        avg_sent = sentiment.get('average_sentiment_score', 0.0)
        total_score = 50 + avg_sent * 50
        signal = 'STRONG BUY' if total_score >= 85 else 'BUY' if total_score >= 70 else 'HOLD' if total_score >= 50 else 'SELL'
        text = f"""# 🎯 {corp_name} 투자 신호 분석

## 📊 종합 투자 신호
- **신호**: {signal}
- **신호 점수**: {total_score:.1f}/100점
- **리스크 허용도**: {risk_tolerance.title()}

## 💡 요약
- 최근 뉴스 감성 기반 간단 신호입니다. 상세 종합 분석 로직은 차후 고도화 예정입니다.
"""
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 투자 신호 생성 중 오류가 발생했습니다: {str(e)}")]

async def generate_summary_report(corp_name: str, report_type: str, include_charts: bool, analysis_depth: str) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        # 간단 래퍼: 모듈에서 리포트 생성 (실제 구현은 report_generator 내부)
        analysis_data = {"corp_name": corp_name, "analysis_depth": analysis_depth}
        report_result = await report_generator.generate_comprehensive_report(corp_name, analysis_data)
        if report_result.get('success'):
            return [types.TextContent(type="text", text=report_result.get('report_content',''))]
        return [types.TextContent(type="text", text=f"❌ 리포트 생성 실패: {report_result.get('metadata',{}).get('error','알 수 없는 오류')}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 종합 리포트 생성 중 오류가 발생했습니다: {str(e)}")]

async def export_to_pdf(corp_name: str, report_content: str, include_metadata: bool, page_format: str) -> List[types.TextContent]:
    try:
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            import io, base64
        except Exception:
            return [types.TextContent(type="text", text="❌ PDF 생성을 위한 reportlab 라이브러리가 설치되지 않았습니다.")]
        buffer = io.BytesIO()
        page_size = A4 if page_format == "A4" else letter
        doc = SimpleDocTemplate(buffer, pagesize=page_size)
        styles = getSampleStyleSheet()
        story = [Paragraph(f"{corp_name} 기업 분석 리포트", styles['Title']), Spacer(1, 12)]
        if include_metadata:
            story.append(Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), styles['Normal']))
            story.append(Spacer(1, 12))
        for line in report_content.split('\n'):
            if line.strip():
                story.append(Paragraph(line, styles['Normal']))
                story.append(Spacer(1, 6))
        doc.build(story)
        pdf_data = buffer.getvalue(); buffer.close()
        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        text = f"""# 📄 PDF 내보내기 완료

- **기업명**: {corp_name}
- **파일 크기**: {len(pdf_data):,} bytes

```
{pdf_base64[:200]}...
```
"""
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ PDF 내보내기 중 오류가 발생했습니다: {str(e)}")]

# 추가 기능: 포트폴리오/경쟁/업계 리포트
async def optimize_portfolio(companies: List[str], investment_amount: int, risk_tolerance: str, optimization_method: str) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        portfolio_result = await portfolio_analyzer.optimize_portfolio(companies, investment_amount, risk_tolerance, optimization_method)
        text = f"""# 📊 포트폴리오 최적화 결과

## 🎯 최적화 설정
- **기업 구성**: {', '.join(companies)}
- **총 투자금액**: {investment_amount:,}원
- **리스크 허용도**: {risk_tolerance.title()}
- **최적화 방법**: {optimization_method.title()}

## 💰 최적 투자 비중
"""
        for company, weight in (portfolio_result.get('optimal_weights', {}) or {}).items():
            allocation = (portfolio_result.get('allocations', {}) or {}).get(company, 0)
            text += f"- **{company}**: {weight:.1%} ({allocation:,.0f}원)\n"
        text += f"\n## 📈 예상 성과\n- **연간 기대수익률**: {portfolio_result.get('expected_annual_return', 0):.1f}%\n- **연간 변동성**: {portfolio_result.get('annual_volatility', 0):.1f}%\n- **샤프 비율**: {portfolio_result.get('sharpe_ratio', 0):.2f}\n"
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 포트폴리오 최적화 중 오류가 발생했습니다: {str(e)}")]

async def analyze_competitive_position(corp_name: str, competitors: List[str], analysis_metrics: List[str], include_swot: bool) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        competitive_result = await benchmark_analyzer.analyze_competitive_position(corp_name, competitors, analysis_metrics)
        text = f"""# ⚔️ {corp_name} 경쟁 포지션 분석

## 📊 분석 개요
- **대상 기업**: {corp_name}
- **경쟁사**: {', '.join(competitors)}
- **분석 지표**: {', '.join(analysis_metrics)}
- **시장 포지션**: {competitive_result.get('market_position', 'N/A')}
"""
        if include_swot and 'swot_analysis' in competitive_result:
            swot = competitive_result['swot_analysis']
            text += f"""\n## 🎯 SWOT 분석

### ⚡ 강점 (Strengths)
{chr(10).join(f"- {s}" for s in swot.get('strengths', []))}

### ⚠️ 약점 (Weaknesses)
{chr(10).join(f"- {w}" for w in swot.get('weaknesses', []))}

### 🌟 기회 (Opportunities)
{chr(10).join(f"- {o}" for o in swot.get('opportunities', []))}

### 🚨 위협 (Threats)
{chr(10).join(f"- {t}" for t in swot.get('threats', []))}
"""
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 경쟁 포지션 분석 중 오류가 발생했습니다: {str(e)}")]

async def generate_industry_report(industry: str, report_type: str, include_rankings: bool) -> List[types.TextContent]:
    try:
        if not API_KEY:
            return [types.TextContent(type="text", text="❌ API 키가 설정되지 않았습니다. set_dart_api_key를 먼저 호출하세요.")]
        industry_result = await benchmark_analyzer.generate_industry_report(industry, report_type)
        text = f"""# 🏭 {industry} 업계 분석 리포트

## 📊 업계 개요
- **업종**: {industry}
- **분석 기업 수**: {industry_result.get('companies_analyzed', 0)}개
- **리포트 유형**: {report_type.title()}

## 🌟 업계 특성
{industry_result.get('industry_overview', {}).get('market_characteristics', 'N/A')}

## 🔍 주요 트렌드
"""
        for trend in industry_result.get('industry_overview', {}).get('key_trends', []):
            text += f"- {trend}\n"
        if include_rankings:
            text += "\n## 📋 기업 순위 (주요 지표 기준)\n- ROE, 매출액증가율 등 핵심 지표 종합 평가\n"
        text += f"\n---\n*리포트 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 업계 리포트 생성 중 오류가 발생했습니다: {str(e)}")]

def _get_report_name(reprt_code: str) -> str:
    """보고서 코드를 이름으로 변환"""
    code_names = {
        '11011': '1분기보고서',
        '11012': '반기보고서', 
        '11013': '3분기보고서',
        '11014': '사업보고서',
        '11001': '정기공시'
    }
    return code_names.get(reprt_code, f'보고서({reprt_code})')

# XBRL 백업 루틴 (경량 구현)
def _detect_report_rcept_no(corp_code: str, year: str) -> Optional[tuple[str, str]]:
    """해당 연도의 사업/감사 보고서 접수번호(rcept_no) 탐지 (A→F 순)"""
    try:
        base_params = {
            'crtfc_key': API_KEY,
            'corp_code': corp_code,
            'bgn_de': f"{year}0101",
            'end_de': f"{year}1231",
            'page_count': 100,
            'last_reprt_at': 'Y'
        }
        for src in ['A', 'F']:
            params = dict(base_params); params['pblntf_ty'] = src
            res = requests.get('https://opendart.fss.or.kr/api/list.json', params=params).json()
            if res.get('status') == '000':
                # 사업/감사보고서 우선, 최신 접수일 우선
                items = sorted(res.get('list') or [], key=lambda x: x.get('rcept_dt', ''), reverse=True)
                for it in items:
                    rn = it.get('report_nm', '')
                    if ('사업보고서' in rn) or ('감사보고서' in rn):
                        rno = it.get('rcept_no')
                        if rno:
                            return (rno, src)
    except Exception:
        pass
    return None

def _fetch_attachments(rcept_no: str) -> list[dict]:
    """접수번호의 첨부목록(문서/파일) 조회.
    - OpenDART document.xml을 우선 시도하여 첨부 URL을 수집
    - 파싱 실패 시 빈 배열 반환
    """
    try:
        url = 'https://opendart.fss.or.kr/api/document.xml'
        resp = requests.get(url, params={'crtfc_key': API_KEY, 'rcept_no': rcept_no}, timeout=20)
        if resp.status_code != 200:
            return []
        xml_text = resp.content
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            # 응답이 XML이 아닐 수 있음
            return []
        attachments: list[dict] = []
        # document.xml 스키마가 공개 포맷과 다를 수 있어, URL 형태 텍스트를 전수 탐색
        for elem in root.iter():
            text = (elem.text or '').strip()
            if text.startswith('http') and any(ext in text.lower() for ext in ['.xbrl', '.xml', '.zip']):
                attachments.append({'url': text, 'name': elem.tag})
            # 속성에도 URL이 있을 수 있음
            for k, v in (elem.attrib or {}).items():
                if isinstance(v, str) and v.startswith('http') and any(ext in v.lower() for ext in ['.xbrl', '.xml', '.zip']):
                    attachments.append({'url': v, 'name': f"{elem.tag}:{k}"})
        # 중복 제거
        seen = set(); uniq = []
        for a in attachments:
            u = a['url']
            if u not in seen:
                seen.add(u); uniq.append(a)
        return uniq
    except Exception:
        return []

def _download_any_attachment(rcept_no: str, exts: list[str]) -> Optional[bytes]:
    """document.xml에서 특정 확장자 후보를 우선 다운로드."""
    try:
        candidates = _fetch_attachments(rcept_no)
        for att in candidates:
            u = att.get('url')
            if not u:
                continue
            if any(ext in u.lower() for ext in exts):
                try:
                    r = requests.get(u, timeout=25)
                    if r.status_code == 200 and r.content:
                        return r.content
                except Exception:
                    continue
    except Exception:
        return None
    return None

def _download_xbrl_stream(rcept_no: str) -> Optional[bytes]:
    """XBRL(또는 zip) 원문 바이트를 다운로드 (가능한 경우). 실패 시 None."""
    data = _download_any_attachment(rcept_no, ['.xbrl', '.xml', '.zip'])
    if data:
        return data
    # 백업: 알려진 API 경로 시도
    try:
        for url in [
            'https://opendart.fss.or.kr/api/xbrl.zip',
            'https://opendart.fss.or.kr/api/xbrl.xml'
        ]:
            resp = requests.get(url, params={'crtfc_key': API_KEY, 'rcept_no': rcept_no}, timeout=20)
            if resp.status_code == 200 and resp.content:
                return resp.content
    except Exception:
        pass
    return None

# PDF 백업: 다운로드 및 테이블 파싱(간단)
def _download_pdf_stream(rcept_no: str) -> Optional[bytes]:
    if not PDF_AVAILABLE:
        return None
    return _download_any_attachment(rcept_no, ['.pdf'])

def _parse_tables_from_pdf(pdf_bytes: bytes) -> list[pd.DataFrame]:
    if not PDF_AVAILABLE:
        return []
    try:
        import io as _io
        tables: list[pd.DataFrame] = []
        with pdfplumber.open(_io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                try:
                    ts = page.extract_tables()
                    for t in ts or []:
                        if not t or len(t) < 2:
                            continue
                        df = pd.DataFrame(t[1:], columns=t[0])
                        tables.append(df)
                except Exception:
                    continue
        return tables
    except Exception:
        return []

def _pick_statement_table_from_pdf(tables: list[pd.DataFrame], statement_type: str) -> Optional[pd.DataFrame]:
    # 간단 키워드 필터로 재무제표 테이블 후보 선택
    keys = {
        '현금흐름표': ['현금흐름', '영업활동', '투자활동', '재무활동'],
        '손익계산서': ['손익', '매출', '영업이익', '당기순이익'],
        '재무상태표': ['재무상태', '자산총계', '부채총계', '자본총계'],
        '자본변동표': ['자본변동', '자본금', '이익잉여금'],
    }.get(statement_type, [])
    for df in tables:
        text = ' '.join(map(str, df.columns)) + ' ' + ' '.join(df.astype(str).fillna('').values.flatten())
        if any(k in text for k in keys):
            return df
    return None

def _parse_cashflow_from_xbrl_bytes(content: bytes) -> Optional[pd.DataFrame]:
    """XBRL(XML/ZIP) 내용에서 현금흐름표를 파싱. 실패 시 None."""
    try:
        data = content
        # ZIP이면 압축 해제 후 첫 XML 후보 사용
        bio = io.BytesIO(data)
        if zipfile.is_zipfile(bio):
            with zipfile.ZipFile(bio) as zf:
                # XBRL 파일 후보
                xml_names = [n for n in zf.namelist() if n.lower().endswith(('.xml', '.xbrl'))]
                for name in xml_names:
                    try:
                        xml_bytes = zf.read(name)
                        df = _parse_cashflow_xml(xml_bytes)
                        if df is not None and not df.empty:
                            return df
                    except Exception:
                        continue
            return None
        # XML/XBRL 바로 파싱
        return _parse_cashflow_xml(data)
    except Exception:
        return None

_cashflow_patterns = [
    re.compile(r"영업활동[^\n]*현금흐름"),
    re.compile(r"투자활동[^\n]*현금흐름"),
    re.compile(r"재무활동[^\n]*현금흐름"),
    re.compile(r"(?:현금[^\n]*?(?:증가|감소|증감))"),
]

def _parse_cashflow_xml(xml_bytes: bytes) -> Optional[pd.DataFrame]:
    """XBRL XML에서 현금흐름표 후보 노드를 찾아 표로 변환."""
    try:
        # 단순 트리 파싱 + 텍스트 기반 후보 탐색(환경 독립적 경량 파서)
        text = xml_bytes.decode('utf-8', errors='ignore')
        # 행 단위 후보 추출
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        rows = []
        for ln in lines:
            if any(p.search(ln) for p in _cashflow_patterns):
                # 금액 패턴 추출(숫자/콤마/괄호)
                m = re.findall(r"([-\w가-힣\s\(\)]+)[\s:]+([\-\(\),0-9]+)(?:[\s,/]+([\-\(\),0-9]+))?(?:[\s,/]+([\-\(\),0-9]+))?", ln)
                for acc, th, fr, bf in m:
                    rows.append({'계정': acc.strip(), '당기': th, '전기': fr, '전전기': bf})
        if rows:
            return pd.DataFrame(rows)
    except Exception:
        return None
    return None

def _try_fetch_cashflow_from_xbrl(rcept_no: str) -> Optional[pd.DataFrame]:
    """정식 엔드포인트 기반으로 XBRL에서 현금흐름표 추출을 강화한 백업 루틴."""
    _ = _fetch_attachments(rcept_no)
    content = _download_xbrl_stream(rcept_no)
    if not content:
        return None
    return _parse_cashflow_from_xbrl_bytes(content)

# 일반화된 XBRL 파싱 (모든 재무제표 유형)
_def_stmt_map = {
    '현금흐름표': [r"영업활동[^\n]*현금흐름", r"투자활동[^\n]*현금흐름", r"재무활동[^\n]*현금흐름", r"현금[^\n]*증가|감소|증감"],
    '손익계산서': [r"매출액|수익\(매출액\)|영업수익", r"영업이익", r"법인세비용차감전순이익", r"당기순이익|당기순이익\(손실\)"],
    '재무상태표': [r"자산총계", r"부채총계", r"자본총계", r"유동자산", r"유동부채", r"현금및현금성자산"],
    '자본변동표': [r"자본금", r"기타포괄손익누계액", r"이익잉여금|결손금", r"지배기업?소유주지분", r"비지배지분"],
}

def _get_statement_patterns(statement_type: str) -> list[re.Pattern]:
    pats = _def_stmt_map.get(statement_type, [])
    return [re.compile(p) for p in pats]

def _parse_statement_xml(xml_bytes: bytes, patterns: list[re.Pattern]) -> Optional[pd.DataFrame]:
    try:
        text = xml_bytes.decode('utf-8', errors='ignore')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        rows = []
        for ln in lines:
            if any(p.search(ln) for p in patterns):
                m = re.findall(r"([-\w가-힣\s\(\)]+)[\s:]+([\-\(\),0-9]+)(?:[\s,/]+([\-\(\),0-9]+))?(?:[\s,/]+([\-\(\),0-9]+))?", ln)
                for acc, th, fr, bf in m:
                    rows.append({'계정': acc.strip(), '당기': th, '전기': fr, '전전기': bf})
        if rows:
            return pd.DataFrame(rows)
    except Exception:
        return None
    return None

def _parse_statement_from_xbrl_bytes(content: bytes, statement_type: str) -> Optional[pd.DataFrame]:
    try:
        pats = _get_statement_patterns(statement_type)
        if not pats:
            return None
        bio = io.BytesIO(content)
        if zipfile.is_zipfile(bio):
            with zipfile.ZipFile(bio) as zf:
                xml_names = [n for n in zf.namelist() if n.lower().endswith(('.xml', '.xbrl'))]
                for name in xml_names:
                    try:
                        xml_bytes = zf.read(name)
                        df = _parse_statement_xml(xml_bytes, pats)
                        if df is not None and not df.empty:
                            return df
                    except Exception:
                        continue
            return None
        return _parse_statement_xml(content, pats)
    except Exception:
        return None

def _try_fetch_statement_from_xbrl(rcept_no: str, statement_type: str) -> Optional[pd.DataFrame]:
    _ = _fetch_attachments(rcept_no)
    content = _download_xbrl_stream(rcept_no)
    if not content:
        return None
    return _parse_statement_from_xbrl_bytes(content, statement_type)

@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """사용 가능한 도구 목록을 반환합니다"""
    return [
        Tool(
            name="set_dart_api_key",
            description="DART API 키를 설정합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {
                        "type": "string",
                        "description": "DART API 키"
                    }
                },
                "required": ["api_key"]
            }
        ),
        Tool(
            name="get_company_info",
            description="기업의 기본 정보를 조회합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "corp_code": {"type": "string", "description": "기업 고유번호 (선택: 지정 시 회사명 검색 생략)"}
                }
            }
        ),
        Tool(
            name="get_financial_statements",
            description="기업의 재무제표를 조회합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {
                        "type": "string",
                        "description": "회사명"
                    },
                    "bsns_year": {
                        "type": "string",
                        "description": "사업연도 (예: 2024)",
                        "default": "2024"
                    },
                    "reprt_code": {
                        "type": "string",
                        "description": "보고서 코드 (11011: 1분기, 11012: 반기, 11013: 3분기, 11014: 사업보고서)",
                        "default": "11014"
                    },
                    "fs_div": {
                        "type": "string",
                        "description": "재무제표 구분 (CFS: 연결, OFS: 별도)",
                        "default": "CFS"
                    },
                    "statement_type": {
                        "type": "string",
                        "description": "재무제표 종류 (재무상태표, 손익계산서, 현금흐름표, 자본변동표)",
                        "default": "손익계산서"
                    },
                    "corp_code": {"type": "string", "description": "기업 고유번호 (선택)"}
                }
            }
        ),
        Tool(
            name="get_financial_ratios",
            description="주요 재무비율을 계산합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "bsns_year": {"type": "string", "description": "사업연도 (예: 2024)", "default": "2024"},
                    "ratio_categories": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["profitability", "stability", "activity", "growth"]},
                        "default": ["profitability", "stability"]
                    },
                    "include_industry_avg": {"type": "boolean", "default": True},
                    "corp_code": {"type": "string", "description": "기업 고유번호 (선택)"}
                }
            }
        ),
        Tool(
            name="analyze_time_series",
            description="기업의 재무 성과 시계열 분석을 수행합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string"},
                    "analysis_period": {"type": "integer", "default": 5},
                    "metrics": {"type": "array", "items": {"type": "string"}, "default": ["매출액", "영업이익", "순이익"]},
                    "forecast_periods": {"type": "integer", "default": 8}
                },
                "required": ["corp_name"]
            }
        ),
        Tool(
            name="compare_with_industry",
            description="기업을 동종 업계와 벤치마크 비교합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string"},
                    "industry": {"type": "string", "enum": ["반도체", "전기전자", "화학", "자동차", "금융", "인터넷"]},
                    "comparison_metrics": {"type": "array", "items": {"type": "string"}, "default": ["ROE", "ROA", "부채비율"]},
                    "analysis_type": {"type": "string", "enum": ["basic", "detailed"], "default": "basic"}
                },
                "required": ["corp_name", "industry"]
            }
        ),
        Tool(
            name="get_disclosure_list",
            description="기업의 공시 목록을 조회합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "bgn_de": {"type": "string", "description": "검색 시작일 (YYYYMMDD)"},
                    "end_de": {"type": "string", "description": "검색 종료일 (YYYYMMDD)"},
                    "page_count": {"type": "integer", "description": "페이지 당 데이터 수", "default": 10}
                },
                "required": ["corp_name", "bgn_de", "end_de"]
            }
        ),
        Tool(
            name="compare_financials",
            description="여러 기업의 재무지표를 비교합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "companies": {"type": "array", "items": {"type": "string"}, "description": "비교할 기업 목록"},
                    "corp_codes": {"type": "array", "items": {"type": "string"}, "description": "기업 고유번호 목록(선택, companies와 동일 순서)"},
                    "bsns_year": {"type": "string", "description": "비교할 연도 (예: 2024)", "default": "2024"},
                    "comparison_metrics": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["매출액", "영업이익", "순이익", "ROE", "부채비율", "영업이익률"]},
                        "default": ["매출액", "영업이익", "순이익"]
                    },
                    "visualization": {"type": "boolean", "default": True, "description": "차트 시각화 포함 여부"}
                },
                "required": ["companies", "bsns_year"]
            }
        ),
        Tool(
            name="get_company_news",
            description="기업의 최근 뉴스를 검색합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "search_period": {"type": "string", "description": "검색할 기간 (day/1일, week/1주일, month/1개월)", "default": "week"}
                },
                "required": ["corp_name", "search_period"]
            }
        ),
        Tool(
            name="analyze_news_sentiment",
            description="기업 뉴스의 감성 분석을 수행합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "search_period": {"type": "string", "description": "분석할 기간 (day/1일, week/1주일, month/1개월)", "default": "week"},
                    "analysis_depth": {"type": "string", "enum": ["basic", "detailed"], "default": "basic", "description": "분석 깊이"}
                },
                "required": ["corp_name", "search_period"]
            }
        ),
        Tool(
            name="detect_financial_events",
            description="기업의 재무 이벤트를 탐지합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "monitoring_period": {"type": "integer", "default": 30, "description": "모니터링 기간 (일)"},
                    "event_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["전체", "신규 공시", "신규 재무제표", "신규 손익계산서", "신규 재무상태표", "신규 현금흐름표", "신규 자본변동표", "기타"]},
                        "default": ["전체"]
                    }
                },
                "required": ["corp_name", "monitoring_period"]
            }
        ),
        Tool(
            name="generate_investment_signal",
            description="기업의 투자 신호를 생성합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "analysis_period": {"type": "integer", "default": 5, "description": "분석 기간 (년)"},
                    "weight_config": {
                        "type": "object",
                        "properties": {
                            "news_sentiment": {"type": "number", "default": 0.5, "description": "뉴스 감성 가중치"},
                            "market_events": {"type": "number", "default": 0.3, "description": "재무 이벤트 가중치"},
                            "financial_ratios": {"type": "number", "default": 0.2, "description": "재무비율 가중치"}
                        },
                        "required": ["news_sentiment", "market_events", "financial_ratios"]
                    },
                    "risk_tolerance": {"type": "string", "enum": ["낮음", "보통", "높음"], "default": "보통", "description": "리스크 허용도"}
                },
                "required": ["corp_name", "analysis_period", "weight_config", "risk_tolerance"]
            }
        ),
        Tool(
            name="generate_summary_report",
            description="기업의 종합 리포트를 생성합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "report_type": {"type": "string", "enum": ["basic", "detailed"], "default": "basic", "description": "리포트 유형"},
                    "include_charts": {"type": "boolean", "default": True, "description": "차트 포함 여부"},
                    "analysis_depth": {"type": "string", "enum": ["basic", "detailed"], "default": "basic", "description": "분석 깊이"}
                },
                "required": ["corp_name", "report_type"]
            }
        ),
        Tool(
            name="export_to_pdf",
            description="리포트 내용을 PDF로 내보냅니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "report_content": {"type": "string", "description": "리포트 내용"},
                    "include_metadata": {"type": "boolean", "default": True, "description": "메타데이터 포함 여부"},
                    "page_format": {"type": "string", "enum": ["A4", "Letter"], "default": "A4", "description": "페이지 형식"}
                },
                "required": ["corp_name", "report_content"]
            }
        ),
        Tool(
            name="optimize_portfolio",
            description="포트폴리오를 최적화합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "companies": {"type": "array", "items": {"type": "string"}, "description": "포트폴리오 구성 기업 목록"},
                    "investment_amount": {"type": "integer", "default": 100000000, "description": "총 투자금액 (원)"},
                    "risk_tolerance": {"type": "string", "enum": ["낮음", "보통", "높음"], "default": "보통", "description": "리스크 허용도"},
                    "optimization_method": {"type": "string", "enum": ["최대 수익", "최소 리스크", "균형"], "default": "균형", "description": "최적화 방법"}
                },
                "required": ["companies", "investment_amount", "risk_tolerance", "optimization_method"]
            }
        ),
        Tool(
            name="analyze_competitive_position",
            description="기업의 경쟁 포지션을 분석합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "corp_name": {"type": "string", "description": "회사명"},
                    "competitors": {"type": "array", "items": {"type": "string"}, "description": "경쟁사 목록"},
                    "analysis_metrics": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["SWOT", "재무비율", "시장 점유율", "성장성", "위험성"]},
                        "default": ["SWOT", "재무비율"]
                    },
                    "include_swot": {"type": "boolean", "default": True, "description": "SWOT 분석 포함 여부"}
                },
                "required": ["corp_name", "competitors"]
            }
        ),
        Tool(
            name="generate_industry_report",
            description="특정 업계의 분석 리포트를 생성합니다",
            inputSchema={
                "type": "object",
                "properties": {
                    "industry": {"type": "string", "description": "업계명 (예: 반도체, 전기전자, 화학, 자동차, 금융, 인터넷)"},
                    "report_type": {"type": "string", "enum": ["basic", "detailed"], "default": "basic", "description": "리포트 유형"},
                    "include_rankings": {"type": "boolean", "default": True, "description": "기업 순위 포함 여부"}
                },
                "required": ["industry", "report_type"]
            }
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """도구를 실행합니다"""
    if name == "set_dart_api_key":
        return await set_dart_api_key(arguments["api_key"])
    elif name == "get_company_info":
        return await get_company_info(arguments.get("corp_name"), arguments.get("corp_code"))
    elif name == "get_financial_statements":
        return await get_financial_statements(
            arguments.get("corp_name"),
            arguments.get("bsns_year", "2024"),
            arguments.get("reprt_code", "11014"),
            arguments.get("fs_div", "CFS"),
            arguments.get("statement_type", "손익계산서"),
            arguments.get("corp_code")
        )
    elif name == "get_financial_ratios":
        return await get_financial_ratios(
            arguments.get("corp_name"),
            arguments["bsns_year"],
            arguments.get("ratio_categories", ["profitability", "stability"]),
            arguments.get("include_industry_avg", True),
            arguments.get("corp_code")
        )
    elif name == "analyze_time_series":
        return await analyze_time_series(
            arguments["corp_name"],
            arguments.get("analysis_period", 5),
            arguments.get("metrics", ["매출액", "영업이익", "순이익"]),
            arguments.get("forecast_periods", 8)
        )
    elif name == "compare_with_industry":
        return await compare_with_industry(
            arguments["corp_name"],
            arguments["industry"],
            arguments.get("comparison_metrics", ["ROE", "ROA", "부채비율"]),
            arguments.get("analysis_type", "basic")
        )
    elif name == "get_disclosure_list":
        return await get_disclosure_list(
            arguments.get("corp_name"),
            arguments["bgn_de"],
            arguments["end_de"],
            arguments.get("page_count", 10),
            arguments.get("corp_code")
        )
    elif name == "compare_financials":
        return await compare_financials(
            arguments["companies"],
            arguments["bsns_year"],
            arguments.get("comparison_metrics", ["매출액", "영업이익", "순이익"]),
            arguments.get("visualization", True),
            arguments.get("corp_codes")
        )
    elif name == "get_company_news":
        return await get_company_news(
            arguments["corp_name"],
            arguments["search_period"],
            arguments.get("news_categories", ["전체"]),
            arguments.get("include_sentiment", True)
        )
    elif name == "analyze_news_sentiment":
        return await analyze_news_sentiment(
            arguments["corp_name"],
            arguments["search_period"],
            arguments.get("analysis_depth", "basic")
        )
    elif name == "detect_financial_events":
        return await detect_financial_events(
            arguments["corp_name"],
            arguments["monitoring_period"],
            arguments.get("event_types", ["전체"])
        )
    elif name == "generate_investment_signal":
        return await generate_investment_signal(
            arguments["corp_name"],
            arguments["analysis_period"],
            arguments["weight_config"],
            arguments["risk_tolerance"]
        )
    elif name == "generate_summary_report":
        return await generate_summary_report(
            arguments["corp_name"],
            arguments["report_type"],
            arguments.get("include_charts", True),
            arguments.get("analysis_depth", "basic")
        )
    elif name == "export_to_pdf":
        return await export_to_pdf(
            arguments["corp_name"],
            arguments["report_content"],
            arguments.get("include_metadata", True),
            arguments.get("page_format", "A4")
        )
    elif name == "optimize_portfolio":
        return await optimize_portfolio(
            arguments["companies"],
            arguments["investment_amount"],
            arguments["risk_tolerance"],
            arguments["optimization_method"]
        )
    elif name == "analyze_competitive_position":
        return await analyze_competitive_position(
            arguments["corp_name"],
            arguments["competitors"],
            arguments.get("analysis_metrics", ["SWOT", "재무비율"]),
            arguments.get("include_swot", True)
        )
    elif name == "generate_industry_report":
        return await generate_industry_report(
            arguments["industry"],
            arguments["report_type"],
            arguments.get("include_rankings", True)
        )
    else:
        return [types.TextContent(type="text", text=f"알 수 없는 도구: {name}")]

async def main():
    """MCP 서버 메인 함수"""
    # stdio_server를 사용하여 MCP 서버 실행
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="OpenCorpInsight",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main()) 