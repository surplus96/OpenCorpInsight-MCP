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
import xml.etree.ElementTree as ET

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

# 환경변수에서 API 키 자동 로드
try:
    from dotenv import load_dotenv
    from pathlib import Path
    
    # 여러 경로에서 .env 파일 시도
    possible_paths = [
        Path(__file__).parent.parent / ".env",  # 프로젝트 루트
        Path.cwd() / ".env",  # 현재 작업 디렉토리
        Path("/Users/choetaeyeong/projects/OpenCorpInsight/.env")  # 절대 경로
    ]
    
    env_loaded = False
    for env_file in possible_paths:
        if env_file.exists():
            logger.info(f".env 파일 발견: {env_file}")
            load_dotenv(env_file, override=True)
            API_KEY = os.getenv('DART_API_KEY')
            if API_KEY:
                logger.info(f"DART API 키 자동 로드됨: {API_KEY[:10]}...")
                env_loaded = True
                break
            else:
                logger.warning(f"DART API 키가 {env_file}에서 비어있음")
    
    # 환경변수 로드 실패 시 하드코딩된 키 사용 (임시)
    if not env_loaded or not API_KEY:
        logger.warning("환경변수에서 API 키 로드 실패 - 하드코딩된 키 사용")
        API_KEY = "4fde700d04b755c3dd2989a85b742aa35bf65062"
        logger.info(f"하드코딩된 DART API 키 사용: {API_KEY[:10]}...")
        
except ImportError:
    logger.warning("python-dotenv가 설치되지 않음 - 하드코딩된 키 사용")
    API_KEY = "4fde700d04b755c3dd2989a85b742aa35bf65062"
    logger.info(f"하드코딩된 DART API 키 사용: {API_KEY[:10]}...")

# MCP 서버 생성 및 초기화
app = Server("OpenCorpInsight")

# Perplexity MCP 검색 함수 (실제 MCP 호출)
async def perplexity_search_wrapper(query: str, recency_filter: Optional[str] = None):
    """Perplexity MCP를 통한 뉴스 검색"""
    try:
        # 실제 Perplexity MCP 호출 로직
        # 현재는 Mock 데이터 반환
        return {
            "results": [
                {"title": f"{query} 관련 뉴스 1", "content": "Mock 뉴스 내용 1", "url": "https://example.com/1"},
                {"title": f"{query} 관련 뉴스 2", "content": "Mock 뉴스 내용 2", "url": "https://example.com/2"}
            ]
        }
    except Exception as e:
        logger.error(f"Perplexity 검색 오류: {e}")
        return {"results": []}

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
    
    # corpCode API 호출
    zip_url = f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={API_KEY}'
    zip_bytes = requests.get(zip_url).content
    
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        corp_bytes = zf.read('CORPCODE.xml')
        try:
            xml_str = corp_bytes.decode('euc-kr')
        except UnicodeDecodeError:
            xml_str = corp_bytes.decode('utf-8')
    
    root = ET.fromstring(xml_str)
    
    for item in root.findall('.//list'):
        name = item.find('corp_name').text
        code = item.find('corp_code').text
        
        if corp_name in name:
            CORP_CODE_CACHE[corp_name] = code
            return code
    
    raise ValueError(f"기업 '{corp_name}'을 찾을 수 없습니다.")

# API 키 설정 함수
async def set_dart_api_key(api_key: str) -> List[types.TextContent]:
    """DART API 키 설정"""
    global API_KEY
    API_KEY = api_key
    logger.info(f"API 키 설정됨: {API_KEY[:10]}...")
    return [types.TextContent(type="text", text=f"✅ DART API 키가 설정되었습니다: {api_key[:10]}...")]

# 기업 정보 조회
async def get_company_info(corp_name: str) -> List[types.TextContent]:
    """기업 정보 조회"""
    try:
        corp_code = await get_corp_code(corp_name)
        
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
        result = f"""
## {corp_name} 기업 정보

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
async def get_financial_statements(corp_name: str, bsns_year: str, reprt_code: str, fs_div: str, statement_type: str) -> List[types.TextContent]:
    """재무제표 조회"""
    try:
        corp_code = await get_corp_code(corp_name)
        
        url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
        params = {
            'crtfc_key': API_KEY,
            'corp_code': corp_code,
            'bsns_year': bsns_year,
            'reprt_code': reprt_code,
            'fs_div': fs_div
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data['status'] != '000':
            return [types.TextContent(type="text", text=f"오류: {data['message']}")]
        
        df = pd.DataFrame(data['list'])
        statement_df = df[df['sj_nm'] == statement_type].copy()
        
        if statement_df.empty:
            return [types.TextContent(type="text", text=f"{statement_type} 데이터를 찾을 수 없습니다.")]
        
        # 금액 컬럼 동적 선택
        amount_cols = [c for c in ['thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount'] if c in statement_df.columns]
        
        result_df = statement_df[['account_nm', *amount_cols]].rename(columns={
            'account_nm': '계정',
            'thstrm_amount': '당기',
            'frmtrm_amount': '전기',
            'bfefrmtrm_amount': '전전기'
        })
        
        result = f"""
## {corp_name} {bsns_year}년 {statement_type}

{result_df.to_string(index=False)}
"""
        
        return [types.TextContent(type="text", text=result)]
        
    except Exception as e:
        return [types.TextContent(type="text", text=f"재무제표 조회 중 오류 발생: {str(e)}")]

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
                    "corp_name": {
                        "type": "string",
                        "description": "회사명"
                    }
                },
                "required": ["corp_name"]
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
                    }
                },
                "required": ["corp_name"]
            }
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """도구를 실행합니다"""
    if name == "set_dart_api_key":
        return await set_dart_api_key(arguments["api_key"])
    elif name == "get_company_info":
        return await get_company_info(arguments["corp_name"])
    elif name == "get_financial_statements":
        return await get_financial_statements(
            arguments["corp_name"],
            arguments.get("bsns_year", "2024"),
            arguments.get("reprt_code", "11014"),
            arguments.get("fs_div", "CFS"),
            arguments.get("statement_type", "손익계산서")
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