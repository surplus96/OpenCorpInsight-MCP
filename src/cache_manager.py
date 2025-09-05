#!/usr/bin/env python3
"""
Cache Manager for DART MCP Server
SQLite 기반 캐싱 시스템
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
import logging
import os

logger = logging.getLogger("dart-mcp-cache")

class CacheManager:
    """SQLite 기반 캐싱 매니저"""
    
    def __init__(self, db_path: str = "cache/dart_cache.db"):
        self.db_path = db_path
        self._ensure_cache_dir()
        self._init_db()
    
    def _ensure_cache_dir(self):
        """캐시 디렉터리 생성"""
        cache_dir = os.path.dirname(self.db_path)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _init_db(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    category TEXT NOT NULL,
                    metadata TEXT
                )
            ''')
            
            # 인덱스 생성
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON cache_entries(category)')
            conn.commit()
    
    def _generate_key(self, category: str, **params) -> str:
        """캐시 키 생성"""
        # 파라미터를 정렬된 문자열로 변환
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        key_data = f"{category}:{param_str}"
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()
    
    def get(self, category: str, **params) -> Optional[Dict[str, Any]]:
        """캐시에서 데이터 조회"""
        key = self._generate_key(category, **params)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT data, expires_at FROM cache_entries 
                WHERE key = ? AND expires_at > ?
            ''', (key, datetime.now()))
            
            result = cursor.fetchone()
            
            if result:
                logger.info(f"Cache hit for {category}: {key[:8]}...")
                return json.loads(result['data'])
            
            logger.info(f"Cache miss for {category}: {key[:8]}...")
            return None
    
    def set(self, category: str, data: Dict[str, Any], ttl_hours: int = 24, **params):
        """캐시에 데이터 저장"""
        key = self._generate_key(category, **params)
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=ttl_hours)
        
        metadata = {
            'params': params,
            'data_size': len(json.dumps(data))
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO cache_entries 
                (key, data, created_at, expires_at, category, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                key,
                json.dumps(data, ensure_ascii=False),
                created_at,
                expires_at,
                category,
                json.dumps(metadata, ensure_ascii=False)
            ))
            conn.commit()
        
        logger.info(f"Cached {category} data: {key[:8]}... (TTL: {ttl_hours}h)")
    
    def delete(self, category: str, **params) -> bool:
        """특정 캐시 항목 삭제"""
        key = self._generate_key(category, **params)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cache_entries WHERE key = ?', (key,))
            deleted = cursor.rowcount > 0
            conn.commit()
        
        if deleted:
            logger.info(f"Deleted cache entry: {key[:8]}...")
        
        return deleted
    
    def clear_category(self, category: str) -> int:
        """특정 카테고리의 모든 캐시 삭제"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cache_entries WHERE category = ?', (category,))
            deleted_count = cursor.rowcount
            conn.commit()
        
        logger.info(f"Cleared {deleted_count} entries from category: {category}")
        return deleted_count
    
    def cleanup_expired(self) -> int:
        """만료된 캐시 항목 정리"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cache_entries WHERE expires_at <= ?', (datetime.now(),))
            deleted_count = cursor.rowcount
            conn.commit()
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired cache entries")
        
        return deleted_count
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 전체 통계
            cursor.execute('SELECT COUNT(*) as total FROM cache_entries')
            total = cursor.fetchone()['total']
            
            # 만료된 항목 수
            cursor.execute('SELECT COUNT(*) as expired FROM cache_entries WHERE expires_at <= ?', (datetime.now(),))
            expired = cursor.fetchone()['expired']
            
            # 카테고리별 통계
            cursor.execute('''
                SELECT category, COUNT(*) as count, 
                       AVG(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) as active_ratio
                FROM cache_entries 
                GROUP BY category
            ''', (datetime.now(),))
            
            categories = {}
            for row in cursor.fetchall():
                categories[row['category']] = {
                    'count': row['count'],
                    'active_ratio': row['active_ratio']
                }
            
            return {
                'total_entries': total,
                'expired_entries': expired,
                'active_entries': total - expired,
                'categories': categories
            }
    
    def get_cache_policy(self, category: str) -> Dict[str, int]:
        """카테고리별 캐시 정책 반환"""
        policies = {
            # Phase 1: DART API 데이터
            'company_info': {'ttl_hours': 24, 'max_entries': 1000},
            'financial_statements': {'ttl_hours': 24, 'max_entries': 5000},
            'financial_ratios': {'ttl_hours': 12, 'max_entries': 2000},
            'disclosure_list': {'ttl_hours': 6, 'max_entries': 3000},
            'corp_codes': {'ttl_hours': 168, 'max_entries': 100},  # 1주일
            
            # Phase 2: 뉴스 및 분석 데이터
            'company_news': {'ttl_hours': 2, 'max_entries': 1000},  # 2시간 (실시간성 중요)
            'news_sentiment': {'ttl_hours': 4, 'max_entries': 800},  # 4시간
            'financial_events': {'ttl_hours': 6, 'max_entries': 500},  # 6시간
            'company_health': {'ttl_hours': 12, 'max_entries': 300},  # 12시간 (종합 분석)
            'perplexity_search': {'ttl_hours': 1, 'max_entries': 2000},  # 1시간 (검색 결과)
            
            # Phase 3: 투자 신호 및 리포트
            'investment_signal': {'ttl_hours': 8, 'max_entries': 200},  # 8시간 (투자 신호)
            'summary_report': {'ttl_hours': 24, 'max_entries': 100},  # 24시간 (종합 리포트)
            'pdf_export': {'ttl_hours': 72, 'max_entries': 50},  # 72시간 (PDF 파일)
            
            # Phase 4: 포트폴리오, 시계열, 벤치마크 분석
            'portfolio_optimization': {'ttl_hours': 12, 'max_entries': 150},  # 12시간 (포트폴리오 최적화)
            'time_series_analysis': {'ttl_hours': 24, 'max_entries': 200},  # 24시간 (시계열 분석)
            'performance_forecast': {'ttl_hours': 48, 'max_entries': 100},  # 48시간 (성과 예측)
            'industry_benchmark': {'ttl_hours': 24, 'max_entries': 300},  # 24시간 (업계 벤치마크)
            'competitive_analysis': {'ttl_hours': 12, 'max_entries': 200},  # 12시간 (경쟁 분석)
            'industry_report': {'ttl_hours': 72, 'max_entries': 50},  # 72시간 (업계 리포트)
            
            # 기본값
            'default': {'ttl_hours': 24, 'max_entries': 1000}
        }
        
        return policies.get(category, policies['default'])

# 전역 캐시 매니저 인스턴스
cache_manager = CacheManager()

def cached_api_call(category: str, api_func, *args, **kwargs):
    """API 호출 결과를 캐싱하는 데코레이터 함수"""
    # 캐시에서 먼저 확인
    cache_key_params = {
        'args': args,
        'kwargs': {k: v for k, v in kwargs.items() if k != 'api_key'}  # API 키는 캐시 키에서 제외
    }
    
    cached_result = cache_manager.get(category, **cache_key_params)
    if cached_result:
        return cached_result
    
    # 캐시 미스 시 API 호출
    try:
        result = api_func(*args, **kwargs)
        
        # 성공한 결과만 캐싱
        if isinstance(result, dict) and result.get('status') == 'success':
            policy = cache_manager.get_cache_policy(category)
            cache_manager.set(category, result, policy['ttl_hours'], **cache_key_params)
        
        return result
    
    except Exception as e:
        logger.error(f"API call failed for {category}: {str(e)}")
        raise 