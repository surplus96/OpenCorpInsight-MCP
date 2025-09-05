import os
import json
import logging
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    import boto3
    from botocore.exceptions import ClientError
    
    def get_secret():
        secret_name = "DART_API_KEY"
        region_name = "ap-northeast-2"
        
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )
        
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(get_secret_value_response['SecretString'])
            return {
                'DART_API_KEY': secret_data.get('DART_API_KEY'),
                'GPT_API_KEY': secret_data.get('GPT_API_KEY'), 
                'PERPLEXITY_API_KEY': secret_data.get('PERPLEXITY_API_KEY')
            }
        except ClientError as e:
            print(f"AWS Secrets Manager 오류: {e}")
            return None
            
except ImportError:
    print("boto3가 설치되지 않음 - 환경변수 사용")
    def get_secret():
        return None

secrets = get_secret()
if not secrets:
    print("❌ AWS Secrets Manager에서 키를 가져올 수 없습니다!")
    exit(1)

DART_API_KEY = secrets['DART_API_KEY']
PERPLEXITY_API_KEY = secrets['PERPLEXITY_API_KEY']
GPT_API_KEY = secrets['GPT_API_KEY']

# 필수 키 검증
if not DART_API_KEY:
    print("❌ DART_API_KEY가 AWS Secrets Manager에 없습니다!")
    exit(1)

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# DB API 서버 설정 (기존 배포된 서버)
DB_API_BASE_URL = "http://43.203.170.37:8080"  # 실제 서버 주소

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 글로벌 캐시
CORP_CODE_CACHE = {}

def get_corp_code(corp_name: str) -> str:
    """기업 고유번호 조회"""
    if corp_name in CORP_CODE_CACHE:
        return CORP_CODE_CACHE[corp_name]
    
    try:
        zip_url = f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}'
        response = requests.get(zip_url, timeout=30)
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
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
        
    except Exception as e:
        logger.error(f"기업 코드 조회 오류: {e}")
        raise

def get_financial_data(corp_code: str, year: str = '2023') -> Dict:
    """재무제표 데이터 조회 - pandas 없이 순수 Python 사용"""
    try:
        # 올바른 API 엔드포인트 사용
        url = 'https://opendart.fss.or.kr/api/fnlttSinglAcnt.json'
        params = {
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bsns_year': year,
            'reprt_code': '11011'  # 사업보고서 (연간 데이터)
        }
        
        logger.info(f"DART API 호출: {url} with params: {params}")
        
        response = requests.get(url, params=params, timeout=30)
        
        logger.info(f"DART API 응답 상태: {response.status_code}")
        
        if response.status_code != 200:
            raise ValueError(f"HTTP 오류: {response.status_code}")
        
        data = response.json()
        logger.info(f"DART API 응답 데이터: status={data.get('status')}, message={data.get('message')}")
        
        if data['status'] != '000':
            raise ValueError(f"DART API 오류: {data.get('message', '알 수 없는 오류')}")
        
        if 'list' not in data or not data['list']:
            raise ValueError(f"재무 데이터가 없습니다: {year}년 {corp_code}")
        
        # pandas 대신 순수 Python 사용
        financial_list = data['list']
        financial_data = {}
        
        # CFS (연결재무제표) 우선, 없으면 OFS (개별재무제표) 사용
        cfs_data = [item for item in financial_list if item.get('fs_div') == 'CFS']
        if not cfs_data:
            ofs_data = [item for item in financial_list if item.get('fs_div') == 'OFS']
            if ofs_data:
                filtered_data = ofs_data
                logger.info("CFS 없음, OFS 사용")
            else:
                raise ValueError("연결재무제표(CFS)와 개별재무제표(OFS) 모두 없습니다")
        else:
            filtered_data = cfs_data
            logger.info("CFS 사용")
        
        # 손익계산서(IS)에서 주요 지표 추출
        income_statement = [item for item in filtered_data if item.get('sj_div') == 'IS']
        if income_statement:
            # 매출액 찾기 (다양한 계정명 고려)
            revenue_patterns = ['매출액', '수익(매출액)', '영업수익', '매출', '총매출액']
            for pattern in revenue_patterns:
                for item in income_statement:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['revenue'] = float(amount.replace(',', ''))
                                logger.info(f"매출액 발견: {pattern} = {financial_data['revenue']}")
                                break
                            except ValueError:
                                continue
                if 'revenue' in financial_data:
                    break
            
            # 영업이익 찾기
            operating_patterns = ['영업이익', '영업손익', '영업이익(손실)']
            for pattern in operating_patterns:
                for item in income_statement:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['operating_profit'] = float(amount.replace(',', ''))
                                logger.info(f"영업이익 발견: {pattern} = {financial_data['operating_profit']}")
                                break
                            except ValueError:
                                continue
                if 'operating_profit' in financial_data:
                    break
            
            # 당기순이익 찾기
            net_patterns = ['당기순이익', '순이익', '당기순손익', '당기순이익(손실)']
            for pattern in net_patterns:
                for item in income_statement:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['net_profit'] = float(amount.replace(',', ''))
                                logger.info(f"당기순이익 발견: {pattern} = {financial_data['net_profit']}")
                                break
                            except ValueError:
                                continue
                if 'net_profit' in financial_data:
                    break
        
        # 재무상태표(BS)에서 주요 지표 추출
        balance_sheet = [item for item in filtered_data if item.get('sj_div') == 'BS']
        if balance_sheet:
            # 자산총계 찾기
            asset_patterns = ['자산총계', '총자산', '자산합계']
            for pattern in asset_patterns:
                for item in balance_sheet:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['total_assets'] = float(amount.replace(',', ''))
                                logger.info(f"자산총계 발견: {pattern} = {financial_data['total_assets']}")
                                break
                            except ValueError:
                                continue
                if 'total_assets' in financial_data:
                    break
            
            # 부채총계 찾기
            debt_patterns = ['부채총계', '총부채', '부채합계']
            for pattern in debt_patterns:
                for item in balance_sheet:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['total_debt'] = float(amount.replace(',', ''))
                                logger.info(f"부채총계 발견: {pattern} = {financial_data['total_debt']}")
                                break
                            except ValueError:
                                continue
                if 'total_debt' in financial_data:
                    break
            
            # 자본총계 찾기
            equity_patterns = ['자본총계', '총자본', '자본합계', '자본']
            for pattern in equity_patterns:
                for item in balance_sheet:
                    account_nm = item.get('account_nm', '')
                    if pattern in account_nm:
                        amount = item.get('thstrm_amount', '')
                        if amount and amount != '-':
                            try:
                                financial_data['total_equity'] = float(amount.replace(',', ''))
                                logger.info(f"자본총계 발견: {pattern} = {financial_data['total_equity']}")
                                break
                            except ValueError:
                                continue
                if 'total_equity' in financial_data:
                    break
        
        logger.info(f"추출된 재무 데이터: {financial_data}")
        
        if not financial_data:
            raise ValueError("유효한 재무 데이터를 찾을 수 없습니다")
        
        return financial_data
        
    except Exception as e:
        logger.error(f"재무 데이터 조회 오류: {e}")
        raise

def search_news_perplexity(company_name: str, period: str = 'month') -> List[Dict]:
    """Perplexity API를 통한 뉴스 검색 - 개선된 버전"""
    if not PERPLEXITY_API_KEY:
        return []
    
    try:
        period_map = {'day': '지난 24시간', 'week': '지난 7일', 'month': '지난 30일'}
        period_text = period_map.get(period, '최근')
        
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 더 구체적인 프롬프트로 개선
        prompt = f"""
{company_name}의 {period_text} 재무, 실적, 투자 관련 뉴스 5건을 다음 JSON 형태로만 반환하세요:

{{
  "articles": [
    {{
      "title": "기사 제목",
      "content": "기사 내용 전체",
      "summary": "핵심 내용 3줄 요약",
      "published_date": "YYYY-MM-DD",
      "source": "언론사명",
      "url": "기사 URL (있는 경우)"
    }}
  ]
}}

반드시 재무/실적/투자 관련 뉴스만 선별하고, summary는 정확히 3줄로 요약해주세요.
"""
        
        data = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "당신은 재무 뉴스 수집 및 요약 전문가입니다. 반드시 JSON만 반환하고, summary는 정확히 3줄로 작성합니다."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1200,  
            "temperature": 0.2
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            try:
                # JSON 추출 및 파싱
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                news_data = json.loads(content)
                articles = news_data.get('articles', [])
                
                # 데이터 검증 및 정제
                processed_articles = []
                for article in articles[:5]:  # 최대 5개만
                    processed_article = {
                        'title': article.get('title', '제목 없음')[:100],  # 제목 길이 제한
                        'content': article.get('content', '내용 없음'),
                        'summary': article.get('summary', '요약 없음'),
                        'published_date': article.get('published_date', datetime.now().strftime('%Y-%m-%d')),
                        'source': article.get('source', '출처 미상'),
                        'url': article.get('url', '')
                    }
                    
                    # summary가 3줄이 아닌 경우 자동 조정
                    if processed_article['summary'] == '요약 없음' and processed_article['content'] != '내용 없음':
                        # content에서 3줄 요약 생성
                        content_lines = processed_article['content'].split('. ')[:3]
                        processed_article['summary'] = '. '.join(content_lines) + '.' if content_lines else '요약 생성 불가'
                    
                    processed_articles.append(processed_article)
                
                return processed_articles
                
            except json.JSONDecodeError as e:
                logger.error(f"Perplexity 응답 JSON 파싱 실패: {e}")
                
    except Exception as e:
        logger.error(f"Perplexity API 호출 오류: {e}")
 
    return []

def get_corp_name_from_dart(corp_code: str) -> str:
    """DART API를 통해 corp_code로 corp_name 조회"""
    try:
        url = 'https://opendart.fss.or.kr/api/list.json'
        params = {
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bgn_de': '20240101',  # 최근 1년 데이터에서 조회
            'end_de': '20241231',
            'pblntf_ty': 'A',  # 정기공시
            'page_no': 1,
            'page_count': 1  # 1건만 조회해서 기업명 확인
        }
        
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        
        if data['status'] == '000' and data['list']:
            corp_name = data['list'][0]['corp_name']
            logger.info(f"DART에서 조회된 기업명: {corp_name} (코드: {corp_code})")
            return corp_name
        else:
            # 공시가 없으면 기업코드 XML에서 조회 (기존 방식)
            logger.warning(f"DART 공시 목록에서 {corp_code} 기업명 조회 실패, XML 방식으로 대체")
            return get_corp_name_from_xml(corp_code)
            
    except Exception as e:
        logger.error(f"DART API 기업명 조회 오류: {e}")
        # 실패 시 기존 XML 방식으로 대체
        return get_corp_name_from_xml(corp_code)

def get_corp_name_from_xml(corp_code: str) -> str:
    """기존 XML 방식으로 기업명 조회 (백업용)"""
    try:
        zip_url = f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}'
        response = requests.get(zip_url, timeout=30)
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            corp_bytes = zf.read('CORPCODE.xml')
            try:
                xml_str = corp_bytes.decode('euc-kr')
            except UnicodeDecodeError:
                xml_str = corp_bytes.decode('utf-8')
        
        root = ET.fromstring(xml_str)
        
        for item in root.findall('.//list'):
            code = item.find('corp_code').text
            if code == corp_code:
                corp_name = item.find('corp_name').text
                return corp_name
                
        return f"기업_{corp_code}"  # 최후의 대체값
        
    except Exception as e:
        logger.error(f"XML에서 기업명 조회 오류: {e}")
        return f"기업_{corp_code}"

def generate_dashboard_data(corp_code: str, bgn_de: str, end_de: str, user_info: Dict) -> Dict:
    """대시보드 데이터 생성 로직 - DART에서 기업명 자동 조회"""
    # DART API로 corp_code에서 corp_name 자동 조회
    corp_name = get_corp_name_from_dart(corp_code)
    actual_corp_code = corp_code
    
    # 다년도 재무 데이터 수집
    financial_summary = {}
    years = list(range(int(bgn_de), int(end_de) + 1))
    
    for year in reversed(years):
        try:
            financial_data = get_financial_data(actual_corp_code, str(year))
            financial_summary[str(year)] = financial_data
        except Exception as year_error:
            logger.warning(f"{year}년 데이터 조회 실패: {year_error}")
            continue
    
    if not financial_summary:
        raise ValueError('재무 데이터를 찾을 수 없습니다')
    
    # 뉴스 데이터 수집 (개선된 버전)
    news_articles = search_news_perplexity(corp_name, "month")
    
    # 최신년도 데이터 추출
    latest_year = max(financial_summary.keys()) if financial_summary else end_de
    latest_financial = financial_summary.get(latest_year, {})
    
    # 연도별 트렌드 데이터
    revenue_trend = []
    operating_profit_trend = []
    net_profit_trend = []
    
    for year in sorted(financial_summary.keys()):
        revenue_trend.append(financial_summary[year].get('revenue', 0))
        operating_profit_trend.append(financial_summary[year].get('operating_profit', 0))
        net_profit_trend.append(financial_summary[year].get('net_profit', 0))
    
    # 대시보드용 고정 JSON 구조 - 뉴스 섹션 강화
    return {
        'company_info': {
            'corp_code': actual_corp_code,
            'corp_name': corp_name,  # 팝업에서 받은 정확한 기업명
            'analysis_period': f"{bgn_de}-{end_de}",
            'latest_year': latest_year
        },
        'financial_summary': {
            'revenue': latest_financial.get('revenue', 0),
            'operating_profit': latest_financial.get('operating_profit', 0),
            'net_profit': latest_financial.get('net_profit', 0),
            'total_assets': latest_financial.get('total_assets', 0),
            'total_debt': latest_financial.get('total_debt', 0),
            'total_equity': latest_financial.get('total_equity', 0)
        },
        'yearly_trends': {
            'years': sorted(financial_summary.keys()),
            'revenue': revenue_trend,
            'operating_profit': operating_profit_trend,
            'net_profit': net_profit_trend
        },
        # 🆕 뉴스 섹션 - 실제 데이터만 포함
        'news_data': {
            'total_articles': len(news_articles),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'has_news': len(news_articles) > 0,
            'status': 'success' if len(news_articles) > 0 else 'no_news_found',
            'articles': [
                {
                    'id': idx + 1,
                    'title': article['title'],
                    'summary': article['summary'],  # 3줄 요약
                    'full_content': article['content'],  # 전체 내용
                    'published_date': article['published_date'],
                    'source': article['source'],
                    'url': article.get('url', ''),
                    'relevance': 'high'  # 관련도 (추후 AI로 판단 가능)
                }
                for idx, article in enumerate(news_articles[:5])  # 실제 뉴스만, 최대 5개
            ] if len(news_articles) > 0 else [],
            'summary_stats': {
                'positive_news': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장'])]) if news_articles else 0,
                'neutral_news': len([a for a in news_articles if not any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장', '감소', '하락', '부진', '악화'])]) if news_articles else 0,
                'negative_news': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['감소', '하락', '부진', '악화'])]) if news_articles else 0
            } if len(news_articles) > 0 else {'positive_news': 0, 'neutral_news': 0, 'negative_news': 0},
            'message': '최신 뉴스를 성공적으로 가져왔습니다.' if len(news_articles) > 0 else f'{corp_name}에 대한 최근 뉴스를 찾을 수 없습니다. Perplexity API 상태를 확인해주세요.'
        },
        'user_context': user_info,
        'generated_at': datetime.now().isoformat()
    }


@app.route('/api/news/<company_name>', methods=['GET'])
def get_company_news(company_name):
    """특정 기업의 뉴스 조회 - 개선된 버전"""
    try:
        period = request.args.get('period', 'month')
        limit = min(int(request.args.get('limit', 5)), 5)
        news_articles = search_news_perplexity(company_name, period)
        
        return jsonify({
            'status': 'success',
            'data': {
                'company_name': company_name,
                'period': period,
                'total_count': len(news_articles),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'articles': [
                    {
                        'id': idx + 1,
                        'title': article['title'],
                        'summary': article['summary'],
                        'full_content': article['content'],
                        'published_date': article['published_date'],
                        'source': article['source'],
                        'url': article.get('url', ''),
                        'word_count': len(article['content'].split())
                    }
                    for idx, article in enumerate(news_articles[:limit])
                ],
                'sentiment_analysis': {
                    'positive': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장'])]),
                    'neutral': len([a for a in news_articles if not any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장', '감소', '하락', '부진', '악화'])]),
                    'negative': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['감소', '하락', '부진', '악화'])])
                }
            }
        })
        
    except Exception as e:
        logger.error(f"뉴스 조회 오류: {e}")
        return jsonify({'error': str(e)}), 500

def save_chat_to_db(user_sno: str, message: str, response: str, chat_type: str = 'general') -> bool:
    """채팅 기록을 DB API 서버에 저장"""
    try:
        # 사용자 메시지 저장
        user_msg_response = requests.post(f'{DB_API_BASE_URL}/api/chat', 
            json={
                'user_sno': int(user_sno),
                'content': message,
                'role': 'user'
            },
            timeout=10
        )
        
        # AI 응답 저장
        ai_msg_response = requests.post(f'{DB_API_BASE_URL}/api/chat',
            json={
                'user_sno': int(user_sno),
                'content': response,
                'role': 'assistant'
            },
            timeout=10
        )
        
        return user_msg_response.ok and ai_msg_response.ok
        
    except Exception as e:
        logger.error(f"DB 저장 오류: {e}")
        return False

def validate_user_exists(user_sno: str) -> bool:
    """사용자 존재 여부 확인"""
    try:
        response = requests.get(f'{DB_API_BASE_URL}/api/users/{user_sno}', timeout=10)
        return response.ok
    except Exception as e:
        logger.error(f"사용자 확인 오류: {e}")
        return False

def call_llm_for_company_chat(message: str, user_info: Dict, company_data: Dict) -> str:
    """기업 분석 채팅용 LLM 호출"""
    if not GPT_API_KEY:
        return f"LLM API 키가 설정되지 않았습니다. '{message}' 질문에 답변하려면 GPT API 연동이 필요합니다."
    
    try:
        # GPT API 호출
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GPT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 대시보드 데이터를 컨텍스트로 구성
        company_info = company_data.get('company_info', {})
        financial_summary = company_data.get('financial_summary', {})
        yearly_trends = company_data.get('yearly_trends', {})
        news_data = company_data.get('news_data', {})
        
        system_prompt = f"""당신은 재무 분석 전문가입니다.
사용자: {user_info.get('nickname', '사용자')}
레벨: {user_info.get('difficulty', 'intermediate')}
관심사: {user_info.get('interest', '')}
목적: {user_info.get('purpose', '')}

분석 대상 기업: {company_info.get('corp_name', '')}
최신 재무 데이터:
- 매출액: {financial_summary.get('revenue', 0):,}백만원
- 영업이익: {financial_summary.get('operating_profit', 0):,}백만원
- 순이익: {financial_summary.get('net_profit', 0):,}백만원
- 총자산: {financial_summary.get('total_assets', 0):,}백만원

연도별 트렌드:
- 연도: {yearly_trends.get('years', [])}
- 매출: {yearly_trends.get('revenue', [])}
- 영업이익: {yearly_trends.get('operating_profit', [])}

뉴스 정보: {news_data.get('total_articles', 0)}건의 최신 기사 분석됨

사용자 레벨에 맞게 전문적이고 상세한 재무 분석을 제공하세요."""

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            logger.error(f"GPT API 호출 실패: {response.status_code}")
            return "죄송합니다. 현재 답변을 생성할 수 없습니다."
            
    except Exception as e:
        logger.error(f"LLM 호출 오류: {e}")
        return f"답변 생성 중 오류가 발생했습니다: {str(e)}"

def analyze_message_with_llm(message: str, user_info: Dict) -> Dict:
    """LLM을 사용하여 메시지에서 기업명 언급 및 의도 분석"""
    if not GPT_API_KEY:
        return {
            'has_company_mention': False,
            'mentioned_company': None,
            'intent': 'general',
            'confidence': 0.0
        }
    
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GPT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = """당신은 메시지 분석 전문가입니다. 사용자의 메시지를 분석하여 다음 정보를 JSON 형태로 반환하세요:

{
  "has_company_mention": boolean,  // 기업명이 언급되었는지
  "mentioned_company": string or null,  // 언급된 기업명 (있는 경우)
  "intent": string,  // "company_analysis", "general_finance", "other" 중 하나
  "confidence": float  // 분석 신뢰도 (0.0 ~ 1.0)
}

기업명 언급 기준:
- 구체적인 회사명 (삼성전자, 애플, 구글 등)
- 기업/회사/주식회사 등의 일반적 언급
- 특정 산업의 기업들에 대한 질문

의도 분류:
- company_analysis: 특정 기업의 재무/투자 분석
- general_finance: 일반적인 재무/투자 상담
- other: 기타"""

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"분석할 메시지: '{message}'"}
            ],
            "max_tokens": 200,
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            try:
                # JSON 추출 (마크다운 코드 블록이 있을 수 있음)
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                analysis_result = json.loads(content)
                return analysis_result
                
            except json.JSONDecodeError as e:
                logger.error(f"LLM 분석 결과 JSON 파싱 실패: {e}")
                
    except Exception as e:
        logger.error(f"LLM 메시지 분석 오류: {e}")
    
    # 기본값 반환
    return {
        'has_company_mention': False,
        'mentioned_company': None,
        'intent': 'general',
        'confidence': 0.0
    }

def call_llm_for_general_chat(message: str, user_info: Dict) -> str:
    """일반 채팅용 LLM 호출"""
    if not GPT_API_KEY:
        return f"LLM API 키가 설정되지 않았습니다. '{message}' 질문에 답변하려면 GPT API 연동이 필요합니다."
    
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GPT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = f"""당신은 재무 및 투자 상담 전문가입니다.
사용자 정보:
- 닉네임: {user_info.get('nickname', '사용자')}
- 레벨: {user_info.get('difficulty', 'intermediate')}
- 관심사: {user_info.get('interest', '')}
- 목적: {user_info.get('purpose', '')}

사용자의 레벨에 맞게 재무, 투자, 경제에 대한 전문적이고 유용한 조언을 제공하세요.
구체적인 기업 분석이 필요한 경우, 기업 검색을 통해 정확한 정보를 제공할 수 있다고 안내하세요."""

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            logger.error(f"GPT API 호출 실패: {response.status_code}")
            return "죄송합니다. 현재 답변을 생성할 수 없습니다."
            
    except Exception as e:
        logger.error(f"LLM 호출 오류: {e}")
        return f"답변 생성 중 오류가 발생했습니다: {str(e)}"

# ========== API 엔드포인트들 ==========

@app.route('/api/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'services': {
            'dart_api': bool(DART_API_KEY),
            'perplexity_api': bool(PERPLEXITY_API_KEY),
            'gpt_api': bool(GPT_API_KEY),
            'db_api': 'connected'  # DB API 연결 상태는 별도 체크 가능
        }
    })

@app.route('/api/dashboard', methods=['POST'])
def generate_dashboard():
    """순수 대시보드 데이터 생성 (메시지 없음)"""
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        if 'corp_code' not in data:
            return jsonify({'error': '기업 고유번호(corp_code)가 필요합니다'}), 400
        
        corp_code = data['corp_code']
        bgn_de = data.get('bgn_de', '2019')
        end_de = data.get('end_de', '2023')
        
        # 사용자 정보 (선택적)
        user_info = {
            'user_sno': data.get('user_sno', ''),
            'nickname': data.get('nickname', ''),
            'difficulty': data.get('difficulty', 'intermediate'),
            'interest': data.get('interest', ''),
            'purpose': data.get('purpose', '')
        }
        
        # 대시보드 데이터 생성
        dashboard_data = generate_dashboard_data(corp_code, bgn_de, end_de, user_info)
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        logger.error(f"대시보드 생성 오류: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """채팅 API - chat_type에 따라 분기 처리"""
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        required_fields = ['user_sno', 'nickname', 'difficulty', 'interest', 'purpose', 'chat_type', 'message']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'필수 정보 누락: {field}'}), 400
        
        # 사용자 정보 추출
        user_info = {
            'user_sno': data['user_sno'],
            'nickname': data['nickname'],
            'difficulty': data['difficulty'],
            'interest': data['interest'],
            'purpose': data['purpose']
        }
        
        message = data['message']
        chat_type = data['chat_type']
        
        # 사용자 존재 여부 확인 (선택적)
        if not validate_user_exists(user_info['user_sno']):
            logger.warning(f"존재하지 않는 사용자: {user_info['user_sno']}")
            # 경고만 하고 계속 진행 (DB 서버 다운 시에도 동작하도록)
        
        # chat_type에 따른 분기 처리
        if chat_type == 'company_analysis':
            # 기업 분석 채팅 - 대시보드 데이터 필요
            if 'company_data' not in data:
                return jsonify({'error': '기업 분석을 위해 company_data가 필요합니다. 먼저 /api/dashboard를 호출하세요.'}), 400
            
            company_data = data['company_data']
            
            # LLM을 통한 기업 분석 답변 생성
            response_message = call_llm_for_company_chat(message, user_info, company_data)
            
            # 채팅 기록 DB에 저장
            save_success = save_chat_to_db(
                user_info['user_sno'], 
                message, 
                response_message, 
                'company_analysis'
            )
            
            return jsonify({
                'chat_type': 'company_analysis',
                'user_message': message,
                'response': response_message,
                'db_saved': save_success,
                'generated_at': datetime.now().isoformat()
            })
        
        elif chat_type == 'general_chat':
            # 일반 채팅 - LLM을 통한 메시지 분석
            analysis_result = analyze_message_with_llm(message, user_info)
            
            if analysis_result['has_company_mention'] and analysis_result['intent'] == 'company_analysis':
                # 기업 분석이 필요한 경우 팝업 유도
                response_message = "구체적인 기업 분석을 위해 정확한 기업 정보가 필요합니다. 기업을 검색하여 상세한 재무 분석을 받아보세요."
                
                # 채팅 기록 저장 (팝업 유도 메시지도 저장)
                save_success = save_chat_to_db(user_info['user_sno'], message, response_message, 'general_popup')
                
                return jsonify({
                    'chat_type': 'general_chat',
                    'user_message': message,
                    'response': response_message,
                    'analysis': analysis_result,
                    'action_required': {
                        'type': 'open_company_search',
                        'popup_url': 'http://43.203.170.37:8080/compare/compSearchPopUp',
                        'suggested_company': analysis_result['mentioned_company']
                    },
                    'db_saved': save_success,
                    'generated_at': datetime.now().isoformat()
                })
            else:
                # 일반적인 재무/투자 상담
                response_message = call_llm_for_general_chat(message, user_info)
                
                # 채팅 기록 저장
                save_success = save_chat_to_db(
                    user_info['user_sno'], 
                    message, 
                    response_message, 
                    'general_chat'
                )
                
                return jsonify({
                    'chat_type': 'general_chat',
                    'user_message': message,
                    'response': response_message,
                    'analysis': analysis_result,
                    'db_saved': save_success,
                    'generated_at': datetime.now().isoformat()
                })
        
        else:
            # 지원하지 않는 chat_type
            return jsonify({'error': f'지원하지 않는 chat_type: {chat_type}'}), 400
    
    except Exception as e:
        logger.error(f"채팅 API 오류: {e}")
        return jsonify({'error': str(e)}), 500

# ========== 추가 유틸리티 API ==========

@app.route('/api/company/search', methods=['GET'])
def search_company():
    """기업명으로 기업 코드 검색"""
    try:
        company_name = request.args.get('name')
        if not company_name:
            return jsonify({'error': '기업명(name) 파라미터가 필요합니다'}), 400
        
        corp_code = get_corp_code(company_name)
        
        return jsonify({
            'status': 'success',
            'data': {
                'company_name': company_name,
                'corp_code': corp_code
            }
        })
        
    except Exception as e:
        logger.error(f"기업 검색 오류: {e}")
        return jsonify({'error': str(e)}), 404

@app.route('/api/news/<company_name>', methods=['GET'])
def get_company_news_detailed(company_name):
    """특정 기업의 뉴스 조회 - 개선된 버전"""
    try:
        period = request.args.get('period', 'month')
        limit = min(int(request.args.get('limit', 5)), 5)  # 기본 5개, 최대 5개로 제한
        
        news_articles = search_news_perplexity(company_name, period)
        
        return jsonify({
            'status': 'success',
            'data': {
                'company_name': company_name,
                'period': period,
                'total_count': len(news_articles),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'articles': [
                    {
                        'id': idx + 1,
                        'title': article['title'],
                        'summary': article['summary'],
                        'full_content': article['content'],
                        'published_date': article['published_date'],
                        'source': article['source'],
                        'url': article.get('url', ''),
                        'word_count': len(article['content'].split())
                    }
                    for idx, article in enumerate(news_articles[:limit])
                ],
                'sentiment_analysis': {
                    'positive': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장'])]),
                    'neutral': len([a for a in news_articles if not any(word in a.get('content', '').lower() for word in ['증가', '상승', '호조', '개선', '성장', '감소', '하락', '부진', '악화'])]),
                    'negative': len([a for a in news_articles if any(word in a.get('content', '').lower() for word in ['감소', '하락', '부진', '악화'])])
                }
            }
        })
        
    except Exception as e:
        logger.error(f"뉴스 조회 오류: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/financial/<corp_code>/<year>', methods=['GET'])
def get_company_financial_data(corp_code, year):
    """특정 기업의 특정 연도 재무 데이터 조회"""
    try:
        financial_data = get_financial_data(corp_code, year)
        
        return jsonify({
            'status': 'success',
            'data': {
                'corp_code': corp_code,
                'year': year,
                'financial_data': financial_data
            }
        })
        
    except Exception as e:
        logger.error(f"재무 데이터 조회 오류: {e}")
        return jsonify({'error': str(e)}), 500

# ========== 에러 핸들러 ==========

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'API 엔드포인트를 찾을 수 없습니다.',
        'available_endpoints': [
            'GET /api/health',
            'POST /api/dashboard',
            'POST /api/chat',
            'GET /api/company/search?name=기업명',
            'GET /api/news/<company_name>?period=month',
            'GET /api/financial/<corp_code>/<year>'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'message': '서버 내부 오류가 발생했습니다.'
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)