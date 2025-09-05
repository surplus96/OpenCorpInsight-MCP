/**
 * MCP 연동 시계열 분석 대시보드 JavaScript
 * 실제 OpenCorpInsight MCP 함수와 연동
 */

class MCPTimeSeriesDashboard {
    constructor() {
        this.currentData = null;
        this.charts = {};
        this.isLoading = false;
        this.init();
    }

    /**
     * 대시보드 초기화
     */
    init() {
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.showWelcomeMessage();
    }

    /**
     * 이벤트 리스너 설정
     */
    setupEventListeners() {
        // 폼 제출 이벤트
        const searchForm = document.getElementById('searchForm');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => this.handleFormSubmit(e));
        }

        // 창 크기 변경 시 차트 리사이즈
        window.addEventListener('resize', () => this.resizeCharts());

        // URL 파라미터에서 자동 검색
        this.handleUrlParams();
    }

    /**
     * 키보드 단축키 설정
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        this.triggerAnalysis();
                        break;
                    case 's':
                        e.preventDefault();
                        this.exportData();
                        break;
                    case 'r':
                        e.preventDefault();
                        this.refreshCurrentAnalysis();
                        break;
                }
            }
        });
    }

    /**
     * URL 파라미터 처리
     */
    handleUrlParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const company = urlParams.get('company');
        const period = urlParams.get('period');
        const forecast = urlParams.get('forecast');

        if (company) {
            const companyInput = document.getElementById('companyName');
            if (companyInput) {
                companyInput.value = company;
            }

            if (period) {
                const periodSelect = document.getElementById('analysisPeriod');
                if (periodSelect && periodSelect.querySelector(`option[value="${period}"]`)) {
                    periodSelect.value = period;
                }
            }

            if (forecast) {
                const forecastSelect = document.getElementById('forecastPeriods');
                if (forecastSelect && forecastSelect.querySelector(`option[value="${forecast}"]`)) {
                    forecastSelect.value = forecast;
                }
            }

            // 자동 분석 실행
            setTimeout(() => this.triggerAnalysis(), 1000);
        }
    }

    /**
     * 폼 제출 처리
     */
    async handleFormSubmit(e) {
        e.preventDefault();
        
        const formData = this.getFormData();
        if (!this.validateFormData(formData)) {
            return;
        }

        await this.performAnalysis(formData);
    }

    /**
     * 폼 데이터 가져오기
     */
    getFormData() {
        return {
            companyName: document.getElementById('companyName')?.value?.trim() || '',
            analysisPeriod: parseInt(document.getElementById('analysisPeriod')?.value || '5'),
            forecastPeriods: parseInt(document.getElementById('forecastPeriods')?.value || '8')
        };
    }

    /**
     * 폼 데이터 유효성 검증
     */
    validateFormData(data) {
        if (!data.companyName) {
            this.showError('기업명을 입력해주세요.');
            this.focusCompanyInput();
            return false;
        }

        if (data.analysisPeriod < 1 || data.analysisPeriod > 10) {
            this.showError('분석 기간은 1년에서 10년 사이여야 합니다.');
            return false;
        }

        if (data.forecastPeriods < 1 || data.forecastPeriods > 20) {
            this.showError('예측 기간은 1분기에서 20분기 사이여야 합니다.');
            return false;
        }

        return true;
    }

    /**
     * 분석 실행
     */
    async performAnalysis({ companyName, analysisPeriod, forecastPeriods }) {
        if (this.isLoading) {
            console.warn('이미 분석이 진행 중입니다.');
            return;
        }

        try {
            this.setLoadingState(true);
            this.hideError();
            this.hideResults();

            console.log(`🔍 MCP 시계열 분석 시작: ${companyName} (${analysisPeriod}년, ${forecastPeriods}분기)`);

            // 실제 MCP 함수 호출
            const mcpResponse = await this.callMCPFunction(companyName, analysisPeriod, forecastPeriods);

            console.log('📊 MCP 응답 수신:', mcpResponse);

            // 응답 데이터 검증
            if (!this.validateMCPResponse(mcpResponse)) {
                throw new Error('MCP 응답 데이터가 올바르지 않습니다.');
            }

            // 데이터 저장 및 표시
            this.currentData = mcpResponse;
            await this.displayResults(mcpResponse);

            // URL 업데이트
            this.updateURL(companyName, analysisPeriod, forecastPeriods);

            this.showNotification(`${companyName} 분석이 완료되었습니다!`, 'success');

        } catch (error) {
            console.error('❌ 분석 실패:', error);
            this.handleAnalysisError(error);
        } finally {
            this.setLoadingState(false);
        }
    }

    /**
     * 실제 MCP 함수 호출
     */
    async callMCPFunction(corpName, analysisPeriod, forecastPeriods) {
        const metrics = ["매출액", "영업이익", "순이익"];

        try {
            // 실제 환경에서는 MCP 서버와 통신
            const response = await fetch('/api/mcp/analyze_time_series', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    corp_name: corpName,
                    analysis_period: analysisPeriod,
                    forecast_periods: forecastPeriods,
                    metrics: metrics
                }),
                timeout: 30000 // 30초 타임아웃
            });

            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('MCP 서버를 찾을 수 없습니다. 개발 모드로 전환합니다.');
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }

            return data;

        } catch (error) {
            console.warn('MCP 서버 연결 실패:', error.message);
            
            // 개발/테스트 환경에서는 Mock 데이터 사용
            if (this.isDevelopmentMode()) {
                console.log('🔧 개발 모드: Mock 데이터 생성');
                return this.generateMockMCPResponse(corpName, analysisPeriod, forecastPeriods, metrics);
            }
            
            throw error;
        }
    }

    /**
     * 개발 모드 확인
     */
    isDevelopmentMode() {
        return window.location.hostname === 'localhost' || 
               window.location.hostname === '127.0.0.1' || 
               window.location.search.includes('dev=true');
    }

    /**
     * Mock MCP 응답 생성 (개발/테스트용)
     */
    generateMockMCPResponse(corpName, analysisPeriod, forecastPeriods, metrics) {
        console.log(`🎭 Mock 데이터 생성: ${corpName}`);
        
        const baseValues = {
            "매출액": 100000 + Math.random() * 100000,
            "영업이익": 80000 + Math.random() * 80000,
            "순이익": 60000 + Math.random() * 60000
        };

        const cagrRange = {
            "매출액": 8 + Math.random() * 8,
            "영업이익": 10 + Math.random() * 10,
            "순이익": 12 + Math.random() * 8
        };

        const metricsData = {};
        const forecastsData = {};

        // 각 지표별 데이터 생성
        metrics.forEach(metric => {
            const baseValue = baseValues[metric];
            const cagr = cagrRange[metric];
            
            // 히스토리컬 데이터
            const historicalData = [];
            for (let i = 0; i < analysisPeriod; i++) {
                const growth = Math.pow(1 + cagr/100, i);
                const volatility = 0.9 + Math.random() * 0.2;
                historicalData.push(Math.round(baseValue * growth * volatility));
            }

            // 예측 데이터
            const forecastData = [];
            const lastValue = historicalData[historicalData.length - 1];
            for (let i = 0; i < forecastPeriods; i++) {
                const quarterlyGrowth = Math.pow(1 + cagr/100/4, i + 1);
                const uncertainty = 0.95 + Math.random() * 0.1;
                forecastData.push(Math.round(lastValue * quarterlyGrowth * uncertainty));
            }

            metricsData[metric] = {
                raw_data: historicalData,
                historical_data: historicalData,
                forecast_data: forecastData,
                analysis: {
                    average: historicalData.reduce((a, b) => a + b) / historicalData.length,
                    cagr: cagr,
                    trend_direction: "상승",
                    trend_strength: 0.8 + Math.random() * 0.15,
                    volatility: 0.1 + Math.random() * 0.1,
                    r_squared: 0.75 + Math.random() * 0.2
                }
            };
        });

        // 분기별 예측 데이터
        const quarterData = {};
        for (let i = 0; i < forecastPeriods; i++) {
            const quarter = `Q${i + 1}`;
            quarterData[quarter] = {};
            
            metrics.forEach(metric => {
                quarterData[quarter][metric] = metricsData[metric].forecast_data[i];
            });
        }
        
        forecastsData[`${forecastPeriods}분기_예측`] = quarterData;

        return {
            company: corpName,
            analysis_period: analysisPeriod,
            forecast_periods: forecastPeriods,
            data_points: analysisPeriod + forecastPeriods,
            time_unit: "연간",
            metrics: metricsData,
            forecasts: forecastsData,
            summary: {
                status: "성공",
                analysis_date: new Date().getFullYear().toString(),
                confidence_level: 0.8 + Math.random() * 0.15,
                overall_trend: "강한 상승세",
                key_insights: [
                    "모든 지표에서 일관된 성장 패턴 확인",
                    `평균 ${Object.values(cagrRange).reduce((a, b) => a + b, 0) / metrics.length}% CAGR 달성`,
                    "높은 예측 신뢰도 확인"
                ]
            }
        };
    }

    /**
     * MCP 응답 데이터 검증
     */
    validateMCPResponse(response) {
        if (!response || typeof response !== 'object') {
            console.error('Invalid response type:', typeof response);
            return false;
        }

        const requiredFields = ['company', 'analysis_period', 'forecast_periods', 'metrics'];
        for (const field of requiredFields) {
            if (!response[field]) {
                console.error(`Missing required field: ${field}`);
                return false;
            }
        }

        if (!response.metrics || typeof response.metrics !== 'object') {
            console.error('Invalid metrics data');
            return false;
        }

        return true;
    }

    /**
     * 결과 표시
     */
    async displayResults(data) {
        try {
            // 헤더 정보 업데이트
            this.updateHeader(data);
            
            // 핵심 지표 업데이트
            this.updateKeyMetrics(data);
            
            // 차트 생성
            await this.createCharts(data);
            
            // 예측 결과 표시
            this.updateForecastResults(data);
            
            // 결과 섹션 표시
            this.showResults();
            
        } catch (error) {
            console.error('결과 표시 중 오류:', error);
            this.showError('결과를 표시하는 중 오류가 발생했습니다.');
        }
    }

    /**
     * 헤더 정보 업데이트
     */
    updateHeader(data) {
        const companyNameEl = document.getElementById('companyNameResult');
        const analysisMetaEl = document.getElementById('analysisMeta');
        
        if (companyNameEl) {
            companyNameEl.textContent = data.company;
        }
        
        if (analysisMetaEl) {
            const confidence = Math.round((data.summary?.confidence_level || 0.8) * 100);
            analysisMetaEl.textContent = 
                `${data.analysis_period}년 분석 | ${data.forecast_periods}분기 예측 | 신뢰도 ${confidence}%`;
        }
    }

    /**
     * 핵심 지표 업데이트
     */
    updateKeyMetrics(data) {
        const container = document.getElementById('keyMetrics');
        if (!container) return;

        const metrics = Object.keys(data.metrics);
        let html = '';
        
        metrics.forEach(metricName => {
            const metric = data.metrics[metricName];
            if (metric.analysis) {
                const cagr = metric.analysis.cagr || 0;
                const status = this.getCAGRStatus(cagr);
                
                html += `
                    <div class="metric-card ${status}">
                        <div class="metric-value">${cagr.toFixed(1)}%</div>
                        <div class="metric-label">${metricName} CAGR</div>
                    </div>
                `;
            }
        });
        
        // 전체 신뢰도 추가
        const confidence = Math.round((data.summary?.confidence_level || 0.8) * 100);
        const confidenceStatus = confidence >= 85 ? 'excellent' : confidence >= 70 ? 'good' : 'average';
        
        html += `
            <div class="metric-card ${confidenceStatus}">
                <div class="metric-value">${confidence}%</div>
                <div class="metric-label">예측 신뢰도</div>
            </div>
        `;
        
        container.innerHTML = html;
    }

    /**
     * CAGR 상태 판단
     */
    getCAGRStatus(cagr) {
        if (cagr >= 15) return 'excellent';
        if (cagr >= 10) return 'good';
        if (cagr >= 5) return 'average';
        return 'poor';
    }

    /**
     * 차트 생성
     */
    async createCharts(data) {
        // 기존 차트 제거
        this.destroyCharts();
        
        try {
            await Promise.all([
                this.createTimeSeriesChart(data),
                this.createGrowthChart(data)
            ]);
        } catch (error) {
            console.error('차트 생성 중 오류:', error);
            this.showNotification('차트 생성 중 일부 오류가 발생했습니다.', 'warning');
        }
    }

    /**
     * 시계열 차트 생성
     */
    async createTimeSeriesChart(data) {
        const ctx = document.getElementById('timeseriesChart');
        if (!ctx) return;

        const periods = this.generatePeriodLabels(data.analysis_period, data.forecast_periods);
        const datasets = this.createTimeSeriesDatasets(data);

        this.charts.timeseries = new Chart(ctx, {
            type: 'line',
            data: { labels: periods, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: '#3b82f6',
                        borderWidth: 1,
                        cornerRadius: 8,
                        callbacks: {
                            label: (context) => `CAGR: ${context.parsed.y.toFixed(1)}%`
                        }
                    }
                },
                scales: {
                    x: { 
                        title: { display: true, text: '지표' },
                        grid: { color: 'rgba(0, 0, 0, 0.1)' }
                    },
                    y: { 
                        title: { display: true, text: 'CAGR (%)' },
                        grid: { color: 'rgba(0, 0, 0, 0.1)' },
                        ticks: { 
                            callback: (value) => value.toFixed(1) + '%' 
                        },
                        beginAtZero: true
                    }
                },
                animation: { 
                    duration: 1500, 
                    easing: 'easeOutBounce' 
                }
            }
        });
    }

    /**
     * 시계열 데이터셋 생성
     */
    createTimeSeriesDatasets(data) {
        const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'];
        const datasets = [];

        Object.keys(data.metrics).forEach((metricName, index) => {
            const metric = data.metrics[metricName];
            const historicalData = metric.historical_data || [];
            const forecastData = metric.forecast_data || [];
            
            const color = colors[index % colors.length];
            
            datasets.push({
                label: metricName,
                data: [...historicalData, ...forecastData],
                borderColor: color,
                backgroundColor: color + '20',
                borderWidth: 3,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 8,
                pointBackgroundColor: color,
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2
            });
        });

        return datasets;
    }

    /**
     * 기간 라벨 생성
     */
    generatePeriodLabels(analysisPeriod, forecastPeriods) {
        const labels = [];
        const currentYear = new Date().getFullYear();
        
        // 히스토리컬 기간 (연도)
        for (let i = analysisPeriod - 1; i >= 0; i--) {
            labels.push((currentYear - i).toString());
        }
        
        // 예측 기간 (분기)
        for (let i = 1; i <= forecastPeriods; i++) {
            labels.push(`예측Q${i}`);
        }
        
        return labels;
    }

    /**
     * 예측 결과 업데이트
     */
    updateForecastResults(data) {
        const container = document.getElementById('forecastGrid');
        if (!container) return;

        const forecastKey = Object.keys(data.forecasts || {})[0];
        if (!forecastKey) {
            container.innerHTML = '<p>예측 데이터가 없습니다.</p>';
            return;
        }

        const forecasts = data.forecasts[forecastKey];
        let html = '';

        Object.keys(forecasts).forEach(quarter => {
            const quarterData = forecasts[quarter];
            html += `
                <div class="forecast-card">
                    <div class="forecast-quarter">${quarter} 예측</div>
                    <div class="forecast-items">
            `;
            
            Object.keys(quarterData).forEach(metric => {
                const value = quarterData[metric];
                html += `
                    <div class="forecast-item">
                        <span>${metric}</span>
                        <span>${Math.round(value).toLocaleString()}억</span>
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }

    /**
     * 차트 제거
     */
    destroyCharts() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
    }

    /**
     * 차트 리사이즈
     */
    resizeCharts() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.resize === 'function') {
                chart.resize();
            }
        });
    }

    /**
     * UI 상태 관리
     */
    setLoadingState(loading) {
        this.isLoading = loading;
        
        const overlay = document.getElementById('loadingOverlay');
        const btn = document.getElementById('analyzeBtn');
        
        if (overlay) {
            overlay.style.display = loading ? 'flex' : 'none';
        }
        
        if (btn) {
            btn.disabled = loading;
            btn.textContent = loading ? '분석 중...' : '분석 시작';
        }
    }

    showError(message) {
        const errorSection = document.getElementById('errorSection');
        const errorMessage = document.getElementById('errorMessage');
        
        if (errorSection && errorMessage) {
            errorMessage.textContent = message;
            errorSection.classList.add('show');
            errorSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    hideError() {
        const errorSection = document.getElementById('errorSection');
        if (errorSection) {
            errorSection.classList.remove('show');
        }
    }

    showResults() {
        const resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.classList.add('show');
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    hideResults() {
        const resultsSection = document.getElementById('resultsSection');
        if (resultsSection) {
            resultsSection.classList.remove('show');
        }
    }

    /**
     * 분석 오류 처리
     */
    handleAnalysisError(error) {
        let errorMessage = '분석 중 오류가 발생했습니다.';
        
        if (error.message.includes('404')) {
            errorMessage = 'MCP 서버를 찾을 수 없습니다. 서버 상태를 확인해주세요.';
        } else if (error.message.includes('timeout')) {
            errorMessage = '분석 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.';
        } else if (error.message.includes('기업')) {
            errorMessage = '해당 기업의 데이터를 찾을 수 없습니다. 기업명을 확인해주세요.';
        } else if (error.message) {
            errorMessage = error.message;
        }
        
        this.showError(errorMessage);
        this.showNotification(errorMessage, 'error');
    }

    /**
     * 알림 표시
     */
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateX(100px);
            opacity: 0;
            transition: all 0.3s ease;
            max-width: 350px;
            cursor: pointer;
        `;

        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6'
        };

        notification.style.backgroundColor = colors[type] || colors.info;
        notification.textContent = message;
        
        // 클릭으로 닫기
        notification.addEventListener('click', () => {
            this.removeNotification(notification);
        });
        
        document.body.appendChild(notification);
        
        // 애니메이션으로 표시
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
            notification.style.opacity = '1';
        }, 100);
        
        // 자동 제거
        setTimeout(() => {
            this.removeNotification(notification);
        }, type === 'error' ? 5000 : 3000);
    }

    /**
     * 알림 제거
     */
    removeNotification(notification) {
        if (notification && document.body.contains(notification)) {
            notification.style.transform = 'translateX(100px)';
            notification.style.opacity = '0';
            setTimeout(() => {
                if (document.body.contains(notification)) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }
    }

    /**
     * 데이터 내보내기
     */
    exportData() {
        if (!this.currentData) {
            this.showNotification('내보낼 데이터가 없습니다.', 'warning');
            return;
        }
        
        try {
            const exportData = {
                export_date: new Date().toISOString(),
                export_version: '1.0',
                dashboard_type: 'mcp_timeseries',
                ...this.currentData
            };
            
            const dataStr = JSON.stringify(exportData, null, 2);
            const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
            
            const fileName = `${this.currentData.company}_시계열분석_${new Date().toISOString().split('T')[0]}.json`;
            
            const linkElement = document.createElement('a');
            linkElement.setAttribute('href', dataUri);
            linkElement.setAttribute('download', fileName);
            linkElement.style.display = 'none';
            
            document.body.appendChild(linkElement);
            linkElement.click();
            document.body.removeChild(linkElement);
            
            this.showNotification('데이터가 성공적으로 내보내졌습니다!', 'success');
            
        } catch (error) {
            console.error('데이터 내보내기 실패:', error);
            this.showNotification('데이터 내보내기 중 오류가 발생했습니다.', 'error');
        }
    }

    /**
     * URL 업데이트
     */
    updateURL(company, period, forecast) {
        const url = new URL(window.location);
        url.searchParams.set('company', company);
        url.searchParams.set('period', period);
        url.searchParams.set('forecast', forecast);
        
        window.history.replaceState({}, '', url);
    }

    /**
     * 현재 분석 새로고침
     */
    refreshCurrentAnalysis() {
        if (!this.currentData) {
            this.showNotification('새로고침할 데이터가 없습니다.', 'warning');
            return;
        }
        
        const { company, analysis_period, forecast_periods } = this.currentData;
        this.performAnalysis({
            companyName: company,
            analysisPeriod: analysis_period,
            forecastPeriods: forecast_periods
        });
    }

    /**
     * 분석 트리거
     */
    triggerAnalysis() {
        const searchForm = document.getElementById('searchForm');
        if (searchForm) {
            searchForm.dispatchEvent(new Event('submit'));
        }
    }

    /**
     * 기업명 입력 필드 포커스
     */
    focusCompanyInput() {
        const companyInput = document.getElementById('companyName');
        if (companyInput) {
            companyInput.focus();
            companyInput.select();
        }
    }

    /**
     * 환영 메시지 표시
     */
    showWelcomeMessage() {
        setTimeout(() => {
            this.showNotification('기업명을 입력하고 분석을 시작하세요! (Ctrl+Enter)', 'info');
        }, 1000);
    }

    /**
     * 현재 데이터 반환
     */
    getCurrentData() {
        return this.currentData;
    }

    /**
     * 상태 정보 반환
     */
    getStatus() {
        return {
            isLoading: this.isLoading,
            hasData: !!this.currentData,
            chartsCount: Object.keys(this.charts).length,
            lastAnalysis: this.currentData ? {
                company: this.currentData.company,
                timestamp: new Date().toISOString()
            } : null
        };
    }
}

/**
 * 유틸리티 함수들
 */
const MCPDashboardUtils = {
    /**
     * 숫자 포맷팅
     */
    formatNumber(num, options = {}) {
        const { 
            decimals = 0, 
            unit = '', 
            locale = 'ko-KR' 
        } = options;
        
        const formatted = new Intl.NumberFormat(locale, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }).format(num);
        
        return unit ? `${formatted}${unit}` : formatted;
    },

    /**
     * 날짜 포맷팅
     */
    formatDate(date, locale = 'ko-KR') {
        return new Date(date).toLocaleDateString(locale, {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    },

    /**
     * 성장률 상태 판단
     */
    getGrowthStatus(value) {
        if (value >= 15) return { status: 'excellent', color: '#10b981', text: '매우 우수' };
        if (value >= 10) return { status: 'good', color: '#3b82f6', text: '우수' };
        if (value >= 5) return { status: 'average', color: '#f59e0b', text: '보통' };
        if (value >= 0) return { status: 'poor', color: '#ef4444', text: '부진' };
        return { status: 'negative', color: '#dc2626', text: '마이너스' };
    },

    /**
     * 디바운스 함수
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * 로컬 스토리지 저장
     */
    saveToStorage(key, data) {
        try {
            localStorage.setItem(key, JSON.stringify(data));
            return true;
        } catch (error) {
            console.error('로컬 스토리지 저장 실패:', error);
            return false;
        }
    },

    /**
     * 로컬 스토리지 로드
     */
    loadFromStorage(key) {
        try {
            const data = localStorage.getItem(key);
            return data ? JSON.parse(data) : null;
        } catch (error) {
            console.error('로컬 스토리지 로드 실패:', error);
            return null;
        }
    }
};

/**
 * 전역 변수 및 초기화
 */
let mcpDashboardInstance = null;

/**
 * 대시보드 초기화
 */
function initializeMCPDashboard() {
    try {
        mcpDashboardInstance = new MCPTimeSeriesDashboard();
        console.log('🚀 MCP 연동 대시보드 초기화 완료');
        return mcpDashboardInstance;
    } catch (error) {
        console.error('대시보드 초기화 실패:', error);
        return null;
    }
}

/**
 * DOM 로드 완료 후 자동 초기화
 */
document.addEventListener('DOMContentLoaded', initializeMCPDashboard);

/**
 * 전역 함수 노출 (개발자 도구 및 외부 접근용)
 */
window.MCPDashboard = {
    getInstance: () => mcpDashboardInstance,
    utils: MCPDashboardUtils,
    testAnalysis: (company = '삼성전자') => {
        if (mcpDashboardInstance) {
            const companyInput = document.getElementById('companyName');
            if (companyInput) {
                companyInput.value = company;
            }
            mcpDashboardInstance.triggerAnalysis();
        }
    },
    exportData: () => {
        if (mcpDashboardInstance) {
            mcpDashboardInstance.exportData();
        }
    },
    getCurrentData: () => {
        return mcpDashboardInstance ? mcpDashboardInstance.getCurrentData() : null;
    },
    getStatus: () => {
        return mcpDashboardInstance ? mcpDashboardInstance.getStatus() : null;
    }
};

/**
 * 에러 핸들링
 */
window.addEventListener('error', (event) => {
    console.error('전역 에러:', event.error);
    if (mcpDashboardInstance) {
        mcpDashboardInstance.showNotification('예상치 못한 오류가 발생했습니다.', 'error');
    }
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('처리되지 않은 Promise 거부:', event.reason);
    if (mcpDashboardInstance) {
        mcpDashboardInstance.showNotification('비동기 작업 중 오류가 발생했습니다.', 'error');
    }
});

/**
 * 개발자 도구용 헬퍼 함수들
 */
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.dev = {
        dashboard: () => mcpDashboardInstance,
        test: (company) => window.MCPDashboard.testAnalysis(company),
        export: () => window.MCPDashboard.exportData(),
        data: () => window.MCPDashboard.getCurrentData(),
        status: () => window.MCPDashboard.getStatus(),
        clear: () => {
            if (mcpDashboardInstance) {
                mcpDashboardInstance.hideResults();
                mcpDashboardInstance.hideError();
                mcpDashboardInstance.currentData = null;
            }
        }
    };
    
    console.log('🔧 개발 모드 활성화. window.dev 객체 사용 가능');
}
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 20
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: '#3b82f6',
                        borderWidth: 1,
                        cornerRadius: 8,
                        callbacks: {
                            label: (context) => {
                                const value = context.parsed.y;
                                return `${context.dataset.label}: ${value.toLocaleString()}억원`;
                            }
                        }
                    }
                },
                scales: {
                    x: { 
                        title: { display: true, text: '기간' },
                        grid: { color: 'rgba(0, 0, 0, 0.1)' }
                    },
                    y: { 
                        title: { display: true, text: '금액 (억원)' },
                        grid: { color: 'rgba(0, 0, 0, 0.1)' },
                        ticks: {
                            callback: (value) => value.toLocaleString() + '억'
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                },
                animation: { 
                    duration: 2000, 
                    easing: 'easeInOutQuart' 
                }
            }
        });
    }

    /**
     * 성장률 차트 생성
     */
    async createGrowthChart(data) {
        const ctx = document.getElementById('growthChart');
        if (!ctx) return;

        const metrics = Object.keys(data.metrics);
        const cagrData = metrics.map(metricName => {
            const metric = data.metrics[metricName];
            return metric.analysis ? metric.analysis.cagr : 0;
        });

        const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'];

        this.charts.growth = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: metrics,
                datasets: [{
                    label: 'CAGR (%)',
                    data: cagrData,
                    backgroundColor: colors.map(color => color + 'CC'),
                    borderColor: colors,
                    borderWidth: 2,
                    borderRadius: 8
                }]
            },