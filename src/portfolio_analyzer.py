#!/usr/bin/env python3
"""
Portfolio Analyzer for OpenCorpInsight
포트폴리오 최적화 및 분석
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 수치 계산 및 최적화
try:
    import numpy as np
    import pandas as pd
    from scipy import optimize
    from scipy.stats import norm
    import cvxpy as cp
    OPTIMIZATION_AVAILABLE = True
except ImportError:
    OPTIMIZATION_AVAILABLE = False
    logger = logging.getLogger("portfolio-analyzer")
    logger.warning("최적화 라이브러리가 설치되지 않음. 포트폴리오 기능이 제한됩니다.")

# 시각화
try:
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False

# 주가 데이터
try:
    import yfinance as yf
    MARKET_DATA_AVAILABLE = True
except ImportError:
    MARKET_DATA_AVAILABLE = False

from cache_manager import cache_manager

logger = logging.getLogger("portfolio-analyzer")

class PortfolioAnalyzer:
    """포트폴리오 최적화 및 분석 클래스"""
    
    def __init__(self):
        self.risk_free_rate = 0.025  # 무위험 수익률 (연 2.5%)
        self.trading_days = 252  # 연간 거래일수
        
    async def optimize_portfolio(self, companies: List[str], investment_amount: float, 
                               risk_tolerance: str, optimization_method: str = "sharpe") -> Dict[str, Any]:
        """포트폴리오 최적화"""
        try:
            # 캐시에서 먼저 조회
            cache_key = f"{'-'.join(sorted(companies))}_{investment_amount}_{risk_tolerance}_{optimization_method}"
            cached_result = cache_manager.get('portfolio_optimization', cache_key=cache_key)
            if cached_result:
                logger.info(f"포트폴리오 최적화 캐시 히트: {companies}")
                return cached_result
            
            # 기업별 수익률 데이터 수집
            returns_data = await self._get_returns_data(companies)
            
            if returns_data.empty:
                return self._get_mock_portfolio_result(companies, investment_amount, risk_tolerance)
            
            # 최적화 실행
            if optimization_method == "sharpe":
                weights = self._optimize_sharpe_ratio(returns_data)
            elif optimization_method == "risk_parity":
                weights = self._optimize_risk_parity(returns_data)
            elif optimization_method == "min_variance":
                weights = self._optimize_min_variance(returns_data)
            else:
                weights = self._optimize_sharpe_ratio(returns_data)  # 기본값
            
            # 포트폴리오 성과 계산
            portfolio_return, portfolio_volatility, sharpe_ratio = self._calculate_portfolio_metrics(
                returns_data, weights
            )
            
            # 리스크 허용도에 따른 조정
            adjusted_weights = self._adjust_for_risk_tolerance(weights, risk_tolerance)
            
            # 투자 금액 배분
            allocations = {company: weight * investment_amount 
                          for company, weight in zip(companies, adjusted_weights)}
            
            # 결과 구성
            result = {
                'companies': companies,
                'optimization_method': optimization_method,
                'risk_tolerance': risk_tolerance,
                'total_investment': investment_amount,
                'optimal_weights': dict(zip(companies, adjusted_weights)),
                'allocations': allocations,
                'expected_annual_return': portfolio_return * 100,
                'annual_volatility': portfolio_volatility * 100,
                'sharpe_ratio': sharpe_ratio,
                'risk_metrics': self._calculate_risk_metrics(returns_data, adjusted_weights),
                'diversification_ratio': self._calculate_diversification_ratio(returns_data, adjusted_weights),
                'rebalancing_frequency': self._suggest_rebalancing_frequency(portfolio_volatility),
                'optimization_timestamp': datetime.now().isoformat(),
                'data_period': '1년',
                'confidence_level': self._calculate_confidence_level(returns_data)
            }
            
            # 캐시에 저장
            cache_manager.set('portfolio_optimization', result, cache_key=cache_key)
            
            return result
            
        except Exception as e:
            logger.error(f"포트폴리오 최적화 중 오류: {e}")
            return self._get_mock_portfolio_result(companies, investment_amount, risk_tolerance)
    
    async def analyze_portfolio_performance(self, companies: List[str], weights: List[float], 
                                          analysis_period: int = 252) -> Dict[str, Any]:
        """포트폴리오 성과 분석"""
        try:
            # 수익률 데이터 수집
            returns_data = await self._get_returns_data(companies, analysis_period)
            
            if returns_data.empty:
                return self._get_mock_performance_result(companies, weights)
            
            # 포트폴리오 수익률 계산
            portfolio_returns = (returns_data * weights).sum(axis=1)
            
            # 성과 지표 계산
            performance_metrics = {
                'total_return': (portfolio_returns + 1).prod() - 1,
                'annual_return': portfolio_returns.mean() * self.trading_days,
                'annual_volatility': portfolio_returns.std() * np.sqrt(self.trading_days),
                'sharpe_ratio': self._calculate_sharpe_ratio(portfolio_returns),
                'max_drawdown': self._calculate_max_drawdown(portfolio_returns),
                'var_95': np.percentile(portfolio_returns, 5),
                'cvar_95': portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, 5)].mean(),
                'sortino_ratio': self._calculate_sortino_ratio(portfolio_returns),
                'calmar_ratio': self._calculate_calmar_ratio(portfolio_returns),
                'information_ratio': self._calculate_information_ratio(portfolio_returns)
            }
            
            # 기간별 성과
            period_performance = self._calculate_period_performance(portfolio_returns)
            
            # 리스크 기여도
            risk_contribution = self._calculate_risk_contribution(returns_data, weights)
            
            result = {
                'companies': companies,
                'weights': dict(zip(companies, weights)),
                'analysis_period_days': analysis_period,
                'performance_metrics': performance_metrics,
                'period_performance': period_performance,
                'risk_contribution': risk_contribution,
                'correlation_matrix': returns_data.corr().to_dict(),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"포트폴리오 성과 분석 중 오류: {e}")
            return self._get_mock_performance_result(companies, weights)
    
    async def generate_efficient_frontier(self, companies: List[str], num_portfolios: int = 100) -> Dict[str, Any]:
        """효율적 프론티어 생성"""
        try:
            # 수익률 데이터 수집
            returns_data = await self._get_returns_data(companies)
            
            if returns_data.empty:
                return self._get_mock_frontier_result(companies)
            
            # 효율적 프론티어 계산
            frontier_data = self._calculate_efficient_frontier(returns_data, num_portfolios)
            
            # 최적 포트폴리오들 식별
            optimal_portfolios = self._identify_optimal_portfolios(frontier_data, returns_data)
            
            result = {
                'companies': companies,
                'num_portfolios': num_portfolios,
                'frontier_data': frontier_data,
                'optimal_portfolios': optimal_portfolios,
                'risk_free_rate': self.risk_free_rate,
                'generation_timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"효율적 프론티어 생성 중 오류: {e}")
            return self._get_mock_frontier_result(companies)
    
    async def _get_returns_data(self, companies: List[str], period_days: int = 252) -> pd.DataFrame:
        """기업별 수익률 데이터 수집"""
        try:
            if not MARKET_DATA_AVAILABLE:
                logger.warning("주가 데이터 라이브러리 없음, Mock 데이터 사용")
                return pd.DataFrame()
            
            # 한국 주식 심볼 변환 (예: 삼성전자 -> 005930.KS)
            symbols = []
            for company in companies:
                symbol = self._get_stock_symbol(company)
                if symbol:
                    symbols.append(symbol)
            
            if not symbols:
                return pd.DataFrame()
            
            # 주가 데이터 다운로드
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days + 50)  # 여유분 추가
            
            stock_data = yf.download(symbols, start=start_date, end=end_date)['Adj Close']
            
            if stock_data.empty:
                return pd.DataFrame()
            
            # 수익률 계산
            returns = stock_data.pct_change().dropna()
            
            # 컬럼명을 회사명으로 변경
            if len(companies) == len(returns.columns):
                returns.columns = companies
            
            return returns.tail(period_days)  # 최근 period_days만 사용
            
        except Exception as e:
            logger.error(f"수익률 데이터 수집 중 오류: {e}")
            return pd.DataFrame()
    
    def _get_stock_symbol(self, company_name: str) -> Optional[str]:
        """회사명을 주식 심볼로 변환"""
        symbol_map = {
            '삼성전자': '005930.KS',
            'LG전자': '066570.KS',
            'SK하이닉스': '000660.KS',
            'NAVER': '035420.KS',
            '카카오': '035720.KS',
            'LG화학': '051910.KS',
            '현대차': '005380.KS',
            'KB금융': '105560.KS',
            '신한지주': '055550.KS',
            'POSCO홀딩스': '005490.KS'
        }
        return symbol_map.get(company_name)
    
    def _optimize_sharpe_ratio(self, returns_data: pd.DataFrame) -> np.ndarray:
        """샤프 비율 최대화 최적화"""
        try:
            n_assets = len(returns_data.columns)
            
            # 목적함수: 음의 샤프 비율 (최소화를 위해)
            def negative_sharpe(weights):
                portfolio_return = np.sum(returns_data.mean() * weights) * self.trading_days
                portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(returns_data.cov() * self.trading_days, weights)))
                return -(portfolio_return - self.risk_free_rate) / portfolio_volatility
            
            # 제약조건
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})  # 가중치 합 = 1
            bounds = tuple((0, 1) for _ in range(n_assets))  # 0 <= weight <= 1
            
            # 초기값
            initial_guess = np.array([1/n_assets] * n_assets)
            
            # 최적화 실행
            result = optimize.minimize(negative_sharpe, initial_guess, method='SLSQP',
                                     bounds=bounds, constraints=constraints)
            
            return result.x if result.success else initial_guess
            
        except Exception as e:
            logger.error(f"샤프 비율 최적화 중 오류: {e}")
            n_assets = len(returns_data.columns)
            return np.array([1/n_assets] * n_assets)
    
    def _optimize_risk_parity(self, returns_data: pd.DataFrame) -> np.ndarray:
        """리스크 패리티 최적화"""
        try:
            n_assets = len(returns_data.columns)
            cov_matrix = returns_data.cov().values
            
            # CVXPY를 사용한 리스크 패리티 최적화
            if OPTIMIZATION_AVAILABLE:
                w = cp.Variable(n_assets)
                risk_contrib = cp.multiply(w, cov_matrix @ w)
                
                # 목적함수: 리스크 기여도의 분산 최소화
                objective = cp.Minimize(cp.sum_squares(risk_contrib - cp.sum(risk_contrib)/n_assets))
                
                # 제약조건
                constraints = [cp.sum(w) == 1, w >= 0]
                
                # 문제 정의 및 해결
                problem = cp.Problem(objective, constraints)
                problem.solve()
                
                if w.value is not None:
                    return w.value
            
            # 대안: 동일 가중치
            return np.array([1/n_assets] * n_assets)
            
        except Exception as e:
            logger.error(f"리스크 패리티 최적화 중 오류: {e}")
            n_assets = len(returns_data.columns)
            return np.array([1/n_assets] * n_assets)
    
    def _optimize_min_variance(self, returns_data: pd.DataFrame) -> np.ndarray:
        """최소분산 최적화"""
        try:
            n_assets = len(returns_data.columns)
            cov_matrix = returns_data.cov().values
            
            # 목적함수: 포트폴리오 분산 최소화
            def portfolio_variance(weights):
                return np.dot(weights.T, np.dot(cov_matrix, weights))
            
            # 제약조건
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            bounds = tuple((0, 1) for _ in range(n_assets))
            
            # 초기값
            initial_guess = np.array([1/n_assets] * n_assets)
            
            # 최적화 실행
            result = optimize.minimize(portfolio_variance, initial_guess, method='SLSQP',
                                     bounds=bounds, constraints=constraints)
            
            return result.x if result.success else initial_guess
            
        except Exception as e:
            logger.error(f"최소분산 최적화 중 오류: {e}")
            n_assets = len(returns_data.columns)
            return np.array([1/n_assets] * n_assets)
    
    def _calculate_portfolio_metrics(self, returns_data: pd.DataFrame, weights: np.ndarray) -> Tuple[float, float, float]:
        """포트폴리오 성과 지표 계산"""
        try:
            # 연간 수익률
            portfolio_return = np.sum(returns_data.mean() * weights) * self.trading_days
            
            # 연간 변동성
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(returns_data.cov() * self.trading_days, weights)))
            
            # 샤프 비율
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility
            
            return portfolio_return, portfolio_volatility, sharpe_ratio
            
        except Exception as e:
            logger.error(f"포트폴리오 지표 계산 중 오류: {e}")
            return 0.08, 0.15, 0.5  # 기본값
    
    def _adjust_for_risk_tolerance(self, weights: np.ndarray, risk_tolerance: str) -> np.ndarray:
        """리스크 허용도에 따른 가중치 조정"""
        try:
            if risk_tolerance == "conservative":
                # 보수적: 가중치를 더 균등하게 조정
                adjusted_weights = weights * 0.7 + np.ones(len(weights)) / len(weights) * 0.3
            elif risk_tolerance == "aggressive":
                # 공격적: 상위 가중치를 더 집중
                top_indices = np.argsort(weights)[-3:]  # 상위 3개
                adjusted_weights = weights.copy()
                adjusted_weights[top_indices] *= 1.2
            else:  # moderate
                adjusted_weights = weights.copy()
            
            # 정규화
            adjusted_weights = adjusted_weights / np.sum(adjusted_weights)
            
            return adjusted_weights
            
        except Exception as e:
            logger.error(f"리스크 허용도 조정 중 오류: {e}")
            return weights
    
    def _calculate_risk_metrics(self, returns_data: pd.DataFrame, weights: np.ndarray) -> Dict[str, float]:
        """리스크 지표 계산"""
        try:
            portfolio_returns = (returns_data * weights).sum(axis=1)
            
            return {
                'value_at_risk_95': float(np.percentile(portfolio_returns, 5)),
                'conditional_var_95': float(portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, 5)].mean()),
                'max_drawdown': float(self._calculate_max_drawdown(portfolio_returns)),
                'downside_deviation': float(portfolio_returns[portfolio_returns < 0].std() * np.sqrt(self.trading_days)),
                'beta': 1.0  # 시장 베타 (추후 구현)
            }
            
        except Exception as e:
            logger.error(f"리스크 지표 계산 중 오류: {e}")
            return {'value_at_risk_95': -0.02, 'conditional_var_95': -0.03, 'max_drawdown': -0.15, 'downside_deviation': 0.12, 'beta': 1.0}
    
    def _calculate_diversification_ratio(self, returns_data: pd.DataFrame, weights: np.ndarray) -> float:
        """분산화 비율 계산"""
        try:
            # 개별 자산 가중평균 변동성
            individual_volatilities = returns_data.std() * np.sqrt(self.trading_days)
            weighted_avg_volatility = np.sum(weights * individual_volatilities)
            
            # 포트폴리오 변동성
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(returns_data.cov() * self.trading_days, weights)))
            
            # 분산화 비율
            diversification_ratio = weighted_avg_volatility / portfolio_volatility
            
            return float(diversification_ratio)
            
        except Exception as e:
            logger.error(f"분산화 비율 계산 중 오류: {e}")
            return 1.2
    
    def _suggest_rebalancing_frequency(self, portfolio_volatility: float) -> str:
        """리밸런싱 주기 제안"""
        if portfolio_volatility > 0.25:
            return "월간"
        elif portfolio_volatility > 0.15:
            return "분기별"
        else:
            return "반기별"
    
    def _calculate_confidence_level(self, returns_data: pd.DataFrame) -> float:
        """분석 신뢰도 계산"""
        try:
            # 데이터 품질 기반 신뢰도
            data_points = len(returns_data)
            missing_ratio = returns_data.isnull().sum().sum() / (len(returns_data) * len(returns_data.columns))
            
            base_confidence = min(90, data_points / 252 * 100)  # 1년 데이터 기준 90%
            quality_penalty = missing_ratio * 20  # 결측치에 따른 페널티
            
            confidence = max(50, base_confidence - quality_penalty)
            
            return float(confidence)
            
        except Exception as e:
            logger.error(f"신뢰도 계산 중 오류: {e}")
            return 75.0
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """최대 낙폭 계산"""
        try:
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            return drawdown.min()
        except:
            return -0.15
    
    def _calculate_sharpe_ratio(self, returns: pd.Series) -> float:
        """샤프 비율 계산"""
        try:
            excess_return = returns.mean() * self.trading_days - self.risk_free_rate
            volatility = returns.std() * np.sqrt(self.trading_days)
            return excess_return / volatility if volatility > 0 else 0
        except:
            return 0.5
    
    def _calculate_sortino_ratio(self, returns: pd.Series) -> float:
        """소르티노 비율 계산"""
        try:
            excess_return = returns.mean() * self.trading_days - self.risk_free_rate
            downside_std = returns[returns < 0].std() * np.sqrt(self.trading_days)
            return excess_return / downside_std if downside_std > 0 else 0
        except:
            return 0.7
    
    def _calculate_calmar_ratio(self, returns: pd.Series) -> float:
        """칼마 비율 계산"""
        try:
            annual_return = returns.mean() * self.trading_days
            max_drawdown = abs(self._calculate_max_drawdown(returns))
            return annual_return / max_drawdown if max_drawdown > 0 else 0
        except:
            return 0.6
    
    def _calculate_information_ratio(self, returns: pd.Series) -> float:
        """정보 비율 계산 (벤치마크 대비)"""
        try:
            # 간단히 초과수익률의 샤프비율로 근사
            excess_return = returns.mean() * self.trading_days - self.risk_free_rate
            tracking_error = returns.std() * np.sqrt(self.trading_days)
            return excess_return / tracking_error if tracking_error > 0 else 0
        except:
            return 0.4
    
    def _calculate_period_performance(self, returns: pd.Series) -> Dict[str, float]:
        """기간별 성과 계산"""
        try:
            cumulative = (1 + returns).cumprod()
            
            return {
                '1개월': float((cumulative.tail(21).iloc[-1] / cumulative.tail(21).iloc[0] - 1) if len(cumulative) >= 21 else 0),
                '3개월': float((cumulative.tail(63).iloc[-1] / cumulative.tail(63).iloc[0] - 1) if len(cumulative) >= 63 else 0),
                '6개월': float((cumulative.tail(126).iloc[-1] / cumulative.tail(126).iloc[0] - 1) if len(cumulative) >= 126 else 0),
                '1년': float((cumulative.iloc[-1] / cumulative.iloc[0] - 1) if len(cumulative) > 0 else 0)
            }
        except:
            return {'1개월': 0.02, '3개월': 0.05, '6개월': 0.08, '1년': 0.12}
    
    def _calculate_risk_contribution(self, returns_data: pd.DataFrame, weights: np.ndarray) -> Dict[str, float]:
        """리스크 기여도 계산"""
        try:
            cov_matrix = returns_data.cov() * self.trading_days
            portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
            
            risk_contributions = {}
            for i, company in enumerate(returns_data.columns):
                marginal_contrib = np.dot(cov_matrix.iloc[i], weights)
                risk_contrib = weights[i] * marginal_contrib / portfolio_variance
                risk_contributions[company] = float(risk_contrib)
            
            return risk_contributions
            
        except Exception as e:
            logger.error(f"리스크 기여도 계산 중 오류: {e}")
            return {company: 1.0/len(returns_data.columns) for company in returns_data.columns}
    
    def _calculate_efficient_frontier(self, returns_data: pd.DataFrame, num_portfolios: int) -> Dict[str, List]:
        """효율적 프론티어 계산"""
        try:
            n_assets = len(returns_data.columns)
            results = {'returns': [], 'volatility': [], 'sharpe': [], 'weights': []}
            
            # 목표 수익률 범위 설정
            min_ret = returns_data.mean().min() * self.trading_days
            max_ret = returns_data.mean().max() * self.trading_days
            target_returns = np.linspace(min_ret, max_ret, num_portfolios)
            
            for target_return in target_returns:
                try:
                    # 목표 수익률에서 최소분산 포트폴리오 찾기
                    def portfolio_variance(weights):
                        return np.dot(weights.T, np.dot(returns_data.cov() * self.trading_days, weights))
                    
                    constraints = [
                        {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # 가중치 합 = 1
                        {'type': 'eq', 'fun': lambda x: np.sum(returns_data.mean() * x) * self.trading_days - target_return}  # 목표 수익률
                    ]
                    bounds = tuple((0, 1) for _ in range(n_assets))
                    initial_guess = np.array([1/n_assets] * n_assets)
                    
                    result = optimize.minimize(portfolio_variance, initial_guess, method='SLSQP',
                                             bounds=bounds, constraints=constraints)
                    
                    if result.success:
                        weights = result.x
                        port_return = np.sum(returns_data.mean() * weights) * self.trading_days
                        port_volatility = np.sqrt(portfolio_variance(weights))
                        sharpe = (port_return - self.risk_free_rate) / port_volatility
                        
                        results['returns'].append(float(port_return))
                        results['volatility'].append(float(port_volatility))
                        results['sharpe'].append(float(sharpe))
                        results['weights'].append(weights.tolist())
                        
                except:
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"효율적 프론티어 계산 중 오류: {e}")
            return {'returns': [0.08, 0.12, 0.16], 'volatility': [0.15, 0.18, 0.22], 
                   'sharpe': [0.4, 0.5, 0.6], 'weights': [[0.33, 0.33, 0.34], [0.4, 0.3, 0.3], [0.5, 0.25, 0.25]]}
    
    def _identify_optimal_portfolios(self, frontier_data: Dict, returns_data: pd.DataFrame) -> Dict[str, Any]:
        """최적 포트폴리오들 식별"""
        try:
            if not frontier_data['sharpe']:
                return {}
            
            # 최대 샤프 비율 포트폴리오
            max_sharpe_idx = np.argmax(frontier_data['sharpe'])
            
            # 최소 변동성 포트폴리오
            min_vol_idx = np.argmin(frontier_data['volatility'])
            
            return {
                'max_sharpe': {
                    'weights': dict(zip(returns_data.columns, frontier_data['weights'][max_sharpe_idx])),
                    'return': frontier_data['returns'][max_sharpe_idx],
                    'volatility': frontier_data['volatility'][max_sharpe_idx],
                    'sharpe': frontier_data['sharpe'][max_sharpe_idx]
                },
                'min_volatility': {
                    'weights': dict(zip(returns_data.columns, frontier_data['weights'][min_vol_idx])),
                    'return': frontier_data['returns'][min_vol_idx],
                    'volatility': frontier_data['volatility'][min_vol_idx],
                    'sharpe': frontier_data['sharpe'][min_vol_idx]
                }
            }
            
        except Exception as e:
            logger.error(f"최적 포트폴리오 식별 중 오류: {e}")
            return {}
    
    # Mock 데이터 생성 함수들
    def _get_mock_portfolio_result(self, companies: List[str], investment_amount: float, risk_tolerance: str) -> Dict[str, Any]:
        """Mock 포트폴리오 최적화 결과"""
        n_companies = len(companies)
        
        # 리스크 허용도에 따른 가중치 조정
        if risk_tolerance == "conservative":
            base_weights = [1/n_companies] * n_companies
        elif risk_tolerance == "aggressive":
            base_weights = [0.5] + [0.5/(n_companies-1)] * (n_companies-1)
        else:  # moderate
            base_weights = [0.4] + [0.6/(n_companies-1)] * (n_companies-1)
        
        # 정규화
        total = sum(base_weights)
        weights = [w/total for w in base_weights]
        
        allocations = {company: weight * investment_amount 
                      for company, weight in zip(companies, weights)}
        
        return {
            'companies': companies,
            'optimization_method': 'mock_sharpe',
            'risk_tolerance': risk_tolerance,
            'total_investment': investment_amount,
            'optimal_weights': dict(zip(companies, weights)),
            'allocations': allocations,
            'expected_annual_return': 12.5,
            'annual_volatility': 18.2,
            'sharpe_ratio': 0.68,
            'risk_metrics': {
                'value_at_risk_95': -0.025,
                'conditional_var_95': -0.035,
                'max_drawdown': -0.15,
                'downside_deviation': 0.12,
                'beta': 1.0
            },
            'diversification_ratio': 1.25,
            'rebalancing_frequency': '분기별',
            'optimization_timestamp': datetime.now().isoformat(),
            'data_period': '1년 (Mock)',
            'confidence_level': 75.0
        }
    
    def _get_mock_performance_result(self, companies: List[str], weights: List[float]) -> Dict[str, Any]:
        """Mock 성과 분석 결과"""
        return {
            'companies': companies,
            'weights': dict(zip(companies, weights)),
            'analysis_period_days': 252,
            'performance_metrics': {
                'total_return': 0.125,
                'annual_return': 0.125,
                'annual_volatility': 0.182,
                'sharpe_ratio': 0.68,
                'max_drawdown': -0.15,
                'var_95': -0.025,
                'cvar_95': -0.035,
                'sortino_ratio': 0.85,
                'calmar_ratio': 0.83,
                'information_ratio': 0.45
            },
            'period_performance': {
                '1개월': 0.015,
                '3개월': 0.035,
                '6개월': 0.068,
                '1년': 0.125
            },
            'risk_contribution': dict(zip(companies, [w/sum(weights) for w in weights])),
            'correlation_matrix': {company: {comp: 0.3 if company != comp else 1.0 for comp in companies} for company in companies},
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _get_mock_frontier_result(self, companies: List[str]) -> Dict[str, Any]:
        """Mock 효율적 프론티어 결과"""
        return {
            'companies': companies,
            'num_portfolios': 50,
            'frontier_data': {
                'returns': [0.08, 0.10, 0.12, 0.14, 0.16],
                'volatility': [0.15, 0.16, 0.18, 0.20, 0.22],
                'sharpe': [0.35, 0.45, 0.55, 0.60, 0.65],
                'weights': [[1/len(companies)] * len(companies) for _ in range(5)]
            },
            'optimal_portfolios': {
                'max_sharpe': {
                    'weights': dict(zip(companies, [0.4, 0.35, 0.25][:len(companies)])),
                    'return': 0.14,
                    'volatility': 0.20,
                    'sharpe': 0.60
                },
                'min_volatility': {
                    'weights': dict(zip(companies, [1/len(companies)] * len(companies))),
                    'return': 0.08,
                    'volatility': 0.15,
                    'sharpe': 0.35
                }
            },
            'risk_free_rate': self.risk_free_rate,
            'generation_timestamp': datetime.now().isoformat()
        }

# 전역 포트폴리오 분석기 인스턴스
portfolio_analyzer = PortfolioAnalyzer() 