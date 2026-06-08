import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Info, X, ExternalLink } from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useBodyScrollLock } from '../../../shared/hooks/useBodyScrollLock';
import * as React from 'react';
import { useDialogFocusTrap } from '../../../shared/hooks/useDialogFocusTrap';
import { PageHeader } from '../../../shared/components/PageHeader';
import { formatOperationalLabel } from '../../../shared/lib/operationalLabels';

interface DashboardStats {
    total_audits: number;
    valid_audits?: number;
    invalid_audits?: number;
    telephony_audits?: number;
    average_score: number;
    average_score_percentage?: number;
    pass_rate: number;
    by_alert: Record<string, {
        label: string;
        count: number;
        avg_score: number;
        avg_score_percentage?: number;
        pass_rate: number;
    }>;
    top_failed_criteria: Array<{
        criterionId: string;
        label: string;
        fail: number;
        total: number;
        fail_rate: number;
    }>;
    sector_id?: string;
}

interface AuditHistory {
    id: number;
    timestamp: string;
    operator: string;
    score: number;
    max_score: number;
    summary: string;
    source_type: 'audio' | 'pdf';
    sector_id?: string;
}

const SECTOR_LABELS: Record<string, string> = {
    transferencia: 'Transferência',
    uti: 'UTI',
    bas: 'BAS',
    distribuicao: 'Distribuição',
    cadastro: 'Setor Cadastro',
    logistica_unilever: 'Logística Unilever',
    mondelez: 'Mondelez',
    logistica: 'Logística (Geral)',
    celula_atendimento: 'Célula de Atendimento',
    operacao_taborda: 'Operação Taborda',
    checklist: 'Checklist',
    risk_monitoring: 'Monitoramento de Riscos',
    fenix: 'Fenix',
};
const formatDateTime = (value: string | null | undefined) => {
    if (!value) return '--';
    return new Date(value).toLocaleString('pt-BR', {
        timeZone: 'America/Sao_Paulo',
        dateStyle: 'short',
        timeStyle: 'short'
    });
};
const formatSectorLabel = (sectorId: string | null | undefined) => {
    if (!sectorId) return '-';
    return SECTOR_LABELS[sectorId] ?? formatOperationalLabel(sectorId);
};

const normalizeAuditPercent = (score: number, maxScore: number) => {
    if (!Number.isFinite(score) || !Number.isFinite(maxScore) || maxScore <= 0) {
        return 0;
    }

    return Math.max(0, Math.min(100, Number(((score / maxScore) * 100).toFixed(1))));
};

const formatPercentValue = (value: number) => `${value.toFixed(1)}%`;

const getMetricToneClass = (value: number) => {
    if (value >= 85) return 'text-primary-300 bg-primary-500/10 border border-primary-500/15 theme-light:text-slate-900 theme-light:bg-slate-100 theme-light:border-slate-300';
    if (value >= 70) return 'text-slate-300 bg-slate-700/40 border border-white/10 theme-light:text-slate-800 theme-light:bg-slate-100 theme-light:border-slate-300';
    return 'text-slate-400 bg-slate-800/50 border border-white/10 theme-light:text-slate-700 theme-light:bg-slate-200 theme-light:border-slate-300';
};

const getMetricToneLabel = (value: number) => {
    if (value >= 85) return 'Forte';
    if (value >= 70) return 'Estável';
    return 'Atenção';
};

const getScoreBadgeClass = (scorePercent: number) => {
    if (scorePercent >= 80) return 'border border-primary-500/20 bg-primary-500/10 text-primary-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-900';
    if (scorePercent >= 70) return 'border border-white/10 bg-slate-700/40 text-slate-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800';
    return 'border border-white/10 bg-slate-800/50 text-slate-400 theme-light:border-slate-300 theme-light:bg-slate-200 theme-light:text-slate-700';
};

export function Dashboard({ onNavigateToFiles }: { onNavigateToFiles?: () => void }) {
    const [stats, setStats] = useState<DashboardStats | null>(null);
    const [history, setHistory] = useState<AuditHistory[]>([]);
    const [selectedSector, setSelectedSector] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'audio' | 'pdf'>('audio');
    const [fetchError, setFetchError] = useState<string | null>(null);
    const [refreshKey, setRefreshKey] = useState(0);
    const [showInfoModal, setShowInfoModal] = useState(false);
    const [animatedPassRate, setAnimatedPassRate] = useState(0);
    const infoModalRef = React.useRef<HTMLDivElement | null>(null);

    useBodyScrollLock(showInfoModal);
    const closeInfoModal = React.useCallback(() => setShowInfoModal(false), []);
    useDialogFocusTrap(infoModalRef, showInfoModal, {
        onDismiss: closeInfoModal,
        initialFocusSelector: '[data-autofocus="true"]',
    });

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setFetchError(null);
            try {
                const sectorParams = new URLSearchParams();
                if (selectedSector) {
                    sectorParams.set('sector_id', selectedSector);
                }
                const sectorParam = sectorParams.toString() ? `?${sectorParams.toString()}` : '';
                const [statsRes, historyRes] = await Promise.all([
                    apiFetchJson<DashboardStats>(`/api/analytics${sectorParam}`, { timeoutMs: 10000 }),
                    apiFetchJson<AuditHistory[]>('/api/dashboard/history', { timeoutMs: 10000 })
                ]);

                setStats(statsRes ?? null);

                const normalizedHistory: AuditHistory[] = Array.isArray(historyRes)
                    ? historyRes.map((item): AuditHistory => ({
                        ...item,
                        source_type: item.source_type === 'pdf' ? 'pdf' : 'audio'
                    }))
                    : [];

                setHistory(
                    selectedSector
                        ? normalizedHistory.filter((item) => item.sector_id === selectedSector)
                        : normalizedHistory
                );
            } catch (error) {
                console.error('Failed to fetch dashboard data', error);
                setStats(null);
                setHistory([]);
                setFetchError('Conexão lenta ou indisponível. Verifique se o servidor está rodando.');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [selectedSector, refreshKey]);

    useEffect(() => {
        if (!loading && stats) {
            const timer = setTimeout(() => {
                setAnimatedPassRate(stats.pass_rate ?? 0);
            }, 100);
            return () => clearTimeout(timer);
        } else {
            setAnimatedPassRate(0);
        }
    }, [stats, loading]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center p-20 space-y-6">
                <div className="relative">
                    <div className="w-16 h-16 border-4 border-primary-500/10 border-t-primary-500 rounded-full animate-spin"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-2 h-2 bg-primary-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(201,63,15,0.8)]"></div>
                    </div>
                </div>
                <div className="text-center">
                    <p className="text-white font-medium text-lg">Atualizando painel</p>
                    <p className="text-slate-500 text-xs mt-1 uppercase tracking-widest">Consolidando indicadores operacionais</p>
                </div>
            </div>
        );
    }

    const hasDashboardData =
        (stats?.total_audits ?? 0) > 0 ||
        history.length > 0;
    const dashboardSubtitle = 'Visão consolidada das auditorias e dos principais indicadores da operação.';

    if (fetchError && !hasDashboardData) {
        return (
            <div className="space-y-6">
                <PageHeader
                    eyebrow="nstech | Auditoria"
                    titleFirstWord="Painel"
                    titleRest="de Auditoria"
                    subtitle={dashboardSubtitle}
                />

                <div className="glass-panel rounded-2xl border border-slate-600/30 bg-slate-800/40 p-8 theme-light:border-slate-300 theme-light:bg-slate-100">
                    <h3 className="section-title-lg">Não foi possível carregar o dashboard</h3>
                    <p className="mt-2 max-w-2xl text-sm text-slate-300">{fetchError}</p>
                    <div className="mt-5">
                        <button
                            onClick={() => setRefreshKey((prev) => prev + 1)}
                            className="btn-primary px-5 py-2.5 text-sm font-semibold"
                        >
                            Tentar novamente
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    if (!hasDashboardData) {
        return (
            <div className="space-y-6">
                <PageHeader
                    eyebrow="nstech | Auditoria"
                    titleFirstWord="Painel"
                    titleRest="de Auditoria"
                    subtitle={dashboardSubtitle}
                />

                <div className="glass-panel rounded-2xl p-12 text-center border border-white/5 bg-slate-900/20">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/50 mb-4 border border-white/10">
                        <svg className="w-8 h-8 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                    </div>
                    <h3 className="section-title-lg mb-2">Sem dados para exibir</h3>
                    <p className="text-slate-400 max-w-sm mx-auto mb-6">
                        Ainda não há auditorias salvas. Assim que os primeiros registros forem enviados, os indicadores aparecerão aqui.
                    </p>
                    <button
                        onClick={() => setRefreshKey(prev => prev + 1)}
                        className="btn-primary px-6 py-2 text-sm font-semibold"
                    >
                        Atualizar painel
                    </button>
                </div>
            </div>
        );
    }

    const allSectors = Object.keys(SECTOR_LABELS);
    const filteredHistory = history.filter((h) => (h.source_type || 'audio') === activeTab);
    const averageScorePercentage = stats?.average_score_percentage ?? 0;
    const passRate = stats?.pass_rate ?? 0;
    const historyChartData = filteredHistory.slice().reverse().map((item) => ({
        ...item,
        score_percent: normalizeAuditPercent(item.score, item.max_score),
    }));
    const topAlerts = Object.entries(stats?.by_alert ?? {})
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 6);
    return (
        <div className="space-y-6 pb-10">
            {/* Header Section */}
            <PageHeader
                eyebrow="nstech | Auditoria"
                titleFirstWord="Painel"
                titleRest="de Auditoria"
                subtitle={dashboardSubtitle}
            />

            {fetchError ? (
                <div className="glass-panel rounded-2xl border border-slate-600/30 bg-slate-800/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-100">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                            <p className="section-title-sm">Atualização parcial</p>
                            <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-700">{fetchError}</p>
                        </div>
                        <button
                            onClick={() => setRefreshKey((prev) => prev + 1)}
                            className="btn-ghost px-4 py-2 text-sm font-semibold"
                        >
                            Recarregar
                        </button>
                    </div>
                </div>
            ) : null}

            {/* Filter Section */}
            <div className="surface-toolbar">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h3 className="metric-label flex items-center gap-2 theme-light:text-slate-900">
                            <span className="w-2 h-2 rounded-full bg-primary-500 animate-pulse"></span>
                            Filtrar por setor
                        </h3>
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="overflow-x-auto md:pb-0 custom-scrollbar-windows px-2">
                            <div className="flex gap-2 min-w-max pb-4 pt-1">
                                <button
                                    onClick={() => setSelectedSector(null)}
                                    className={`btn-filter px-4 py-2 ${selectedSector === null ? 'btn-filter-active' : ''}`}
                                >
                                    Visão geral
                                </button>
                                {allSectors.map((sector) => (
                                    <button
                                        key={sector}
                                        onClick={() => setSelectedSector(sector)}
                                        className={`btn-filter px-4 py-2 ${selectedSector === sector ? 'btn-filter-active' : ''}`}
                                    >
                                        {formatSectorLabel(sector)}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Metrics Cards */}
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
                <div className="group metric-card animate-slide-up" style={{ animationDelay: '0.1s', animationFillMode: 'both' }}>
                    <p className="metric-label mb-4">Auditorias salvas</p>
                    <div className="flex items-end justify-between">
                        <h3 className="metric-value">{stats?.total_audits ?? 0}</h3>
                        <div className="metric-icon group-hover:scale-110 transition-transform">
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                        </div>
                    </div>
                    <div className="metric-note flex items-center gap-2">
                        <span className="rounded-full bg-primary-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-primary-300">Base validada</span>
                        <span>{stats?.valid_audits ?? stats?.total_audits ?? 0} registros consolidados</span>
                    </div>
                </div>

                <div className="group metric-card animate-slide-up" style={{ animationDelay: '0.2s', animationFillMode: 'both' }}>
                    <p className="metric-label mb-4">Nota média</p>
                    <div className="flex items-end justify-between">
                        <h3 className="metric-value">{formatPercentValue(averageScorePercentage)}</h3>
                        <div className="metric-icon group-hover:scale-110 transition-transform">
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
                        </div>
                    </div>
                    <div className="metric-note flex items-center gap-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${getMetricToneClass(averageScorePercentage)}`}>{getMetricToneLabel(averageScorePercentage)}</span>
                        <span>Normalizada pela nota máxima de cada auditoria</span>
                    </div>
                </div>

                <div className="group metric-card animate-slide-up" style={{ animationDelay: '0.3s', animationFillMode: 'both' }}>
                    <div className="flex items-center justify-between mb-4">
                        <p className="metric-label">Taxa de aprovação</p>
                        <button
                            onClick={() => setShowInfoModal(true)}
                            className="btn-icon !h-8 !w-8"
                            title="Saiba mais sobre esta métrica"
                            aria-label="Explicar taxa de aprovação"
                            aria-haspopup="dialog"
                            aria-expanded={showInfoModal}
                        >
                            <Info size={14} />
                        </button>
                    </div>
                    <div className="flex items-end justify-between">
                        <h3 className="metric-value">{passRate}<span className="ml-1 text-lg text-slate-500 theme-light:text-slate-700">%</span></h3>
                        <div className="metric-icon group-hover:scale-110 transition-transform">
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        </div>
                    </div>
                    <div className="metric-note flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-slate-800 theme-light:bg-slate-200 rounded-full overflow-hidden">
                            <div className="h-full bg-primary-500 shadow-[0_0_8px_rgba(201,63,15,0.18)] theme-light:bg-slate-600 transition-all duration-1000 ease-out" style={{ width: `${animatedPassRate}%` }}></div>
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${getMetricToneClass(passRate)}`}>{getMetricToneLabel(passRate)}</span>
                    </div>
                </div>
            </div>

            {/* Info Modal */}
            {showInfoModal && (
                <div
                    className="safe-area-overlay fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in"
                    onClick={closeInfoModal}
                >
                    <div
                        ref={infoModalRef}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="dashboard-info-title"
                        aria-describedby="dashboard-info-description"
                        tabIndex={-1}
                        className="touch-scroll w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain glass-panel p-8 rounded-3xl border border-white/10 shadow-2xl theme-light:bg-white theme-light:border-slate-300"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-primary-500/10 flex items-center justify-center text-primary-300 border border-primary-500/15 theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-700">
                                    <Info size={20} />
                                </div>
                                <h3 id="dashboard-info-title" className="section-title-lg">Taxa de aprovação</h3>
                            </div>
                            <button
                                onClick={closeInfoModal}
                                data-autofocus="true"
                                aria-label="Fechar explicação do índice de aprovação"
                                className="btn-icon"
                            >
                                <X size={20} />
                            </button>
                        </div>
                        <div className="space-y-4">
                            <p id="dashboard-info-description" className="text-slate-300 leading-relaxed theme-light:text-slate-600">
                                Esta taxa mostra o percentual de auditorias aprovadas sobre o total exibido no painel.
                            </p>
                            <div className="p-4 rounded-2xl bg-primary-500/5 border border-primary-500/10 theme-light:bg-slate-100 theme-light:border-slate-300">
                                <p className="text-sm text-primary-300 font-medium theme-light:text-slate-800">
                                    O corte atual considera aprovada a auditoria que atinge pelo menos 80% da nota máxima possível.
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={closeInfoModal}
                            className="btn-primary w-full mt-8 py-3.5 rounded-xl font-bold text-sm"
                        >
                            Fechar
                        </button>
                    </div>
                </div>
            )}

            <div className="grid gap-8 xl:grid-cols-3">
                <div className="glass-panel hover-lift p-5 rounded-xl xl:col-span-2 animate-slide-up" style={{ animationDelay: '0.4s', animationFillMode: 'both' }}>
                    <h3 className="section-title mb-5">Evolução da nota</h3>
                    <div className="h-[300px] w-full min-w-0">
                        <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={300} debounce={50}>
                            <LineChart data={historyChartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-slate-600, #475569)" vertical={false} />
                                <XAxis dataKey="timestamp" tickFormatter={(t) => new Date(t).toLocaleDateString()} stroke="var(--color-slate-400, #94a3b8)" fontSize={12} tickLine={false} axisLine={false} />
                                <YAxis
                                    stroke="var(--color-slate-400, #94a3b8)"
                                    fontSize={12}
                                    tickLine={false}
                                    axisLine={false}
                                    domain={[0, 100]}
                                    tickFormatter={(value) => `${value}%`}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'var(--color-slate-800, #1e293b)', borderColor: 'var(--color-slate-700, #334155)', borderRadius: '8px', color: 'var(--theme-light-text-strong, #f8fafc)' }}
                                    itemStyle={{ color: '#38bdf8' }}
                                    formatter={(value) => [`${Number(value).toFixed(2)}%`, 'Nota']}
                                    labelFormatter={(label) => formatDateTime(String(label))}
                                />
                                <Line type="monotone" dataKey="score_percent" stroke="var(--color-primary-500, #38bdf8)" strokeWidth={3} dot={{ fill: 'var(--color-primary-500, #38bdf8)', strokeWidth: 2 }} activeDot={{ r: 6 }} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="glass-panel hover-lift p-5 rounded-xl theme-light:bg-white theme-light:border-slate-300 animate-slide-up" style={{ animationDelay: '0.45s', animationFillMode: 'both' }}>
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="section-title">Últimas auditorias</h3>
                        <div className="flex bg-slate-800/50 rounded-lg p-1 border border-white/5 theme-light:bg-slate-100 theme-light:border-slate-300">
                            <button
                                onClick={() => setActiveTab('audio')}
                                className={`btn-filter px-3 py-1.5 text-xs font-medium ${activeTab === 'audio' ? 'btn-filter-active theme-light:bg-white theme-light:text-slate-900 theme-light:border-slate-300' : '!border-transparent !bg-transparent'}`}
                            >
                                Áudio
                            </button>
                            <button
                                onClick={() => setActiveTab('pdf')}
                                className={`btn-filter px-3 py-1.5 text-xs font-medium ${activeTab === 'pdf' ? 'btn-filter-active theme-light:bg-white theme-light:text-slate-900 theme-light:border-slate-300' : '!border-transparent !bg-transparent'}`}
                            >
                                Documentos
                            </button>
                        </div>
                    </div>
                    {filteredHistory.length > 0 ? (
                        <>
                            <div className="space-y-3 md:hidden">
                                {filteredHistory.map((item, index) => (
                                    <article key={item.id} className="rounded-xl border border-white/10 bg-slate-900/45 p-4 theme-light:bg-slate-50 theme-light:border-slate-300 animate-reveal-soft" style={{ animationDelay: `${0.5 + index * 0.05}s`, animationFillMode: 'both' }}>
                                        <div className="mb-2 flex items-center justify-between gap-3">
                                            <span className="text-xs font-medium text-slate-500 theme-light:text-slate-600">
                                                {new Date(item.timestamp).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })}
                                            </span>
                                            <span className={`rounded-full px-2 py-1 text-xs font-bold ${getScoreBadgeClass(normalizeAuditPercent(item.score, item.max_score))}`}>
                                                {formatPercentValue(normalizeAuditPercent(item.score, item.max_score))}
                                            </span>
                                        </div>
                                        <p className="text-xs uppercase tracking-wider text-slate-500 theme-light:text-slate-600">
                                            {item.source_type === 'pdf' ? 'Documento' : 'Áudio'} • {item.operator || '-'}
                                        </p>
                                        <p className="mt-2 text-xs text-slate-500 theme-light:text-slate-600">
                                            Score bruto: {item.score}/{item.max_score}
                                        </p>
                                        <p className="mt-2 text-sm text-slate-300 line-clamp-3 theme-light:text-slate-800">{item.summary}</p>
                                        {onNavigateToFiles && (
                                            <button
                                                onClick={onNavigateToFiles}
                                                className="mt-3 btn-ghost px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 w-full justify-center"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5" />
                                                Editar em Arquivos
                                            </button>
                                        )}
                                    </article>
                                ))}
                            </div>
                            <div className="hidden md:block overflow-x-auto">
                                <table className="min-w-full text-xs">
                                    <thead>
                                        <tr className="text-slate-500 theme-light:text-slate-600">
                                            <th className="py-2 pr-3 text-left">Data</th>
                                            <th className="py-2 pr-3 text-left">Operador</th>
                                            <th className="py-2 pr-3 text-left">Origem</th>
                                            <th className="py-2 pr-3 text-left">Nota</th>
                                            <th className="py-2 text-left">Resumo</th>
                                            {onNavigateToFiles && <th className="py-2 text-center">Editar</th>}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredHistory.map((item, index) => (
                                            <tr key={item.id} className="border-t border-white/10 theme-light:border-slate-300 animate-reveal-soft" style={{ animationDelay: `${0.5 + index * 0.05}s`, animationFillMode: 'both' }}>
                                                <td className="py-2 pr-3 text-slate-300 theme-light:text-slate-800">{new Date(item.timestamp).toLocaleDateString()}</td>
                                                <td className="py-2 pr-3 text-slate-300 theme-light:text-slate-800">{item.operator || '-'}</td>
                                                <td className="py-2 pr-3 text-slate-300 theme-light:text-slate-800">{item.source_type === 'pdf' ? 'Documento' : 'Áudio'}</td>
                                                <td className="py-2 pr-3">
                                                    <span className={`inline-flex rounded px-2 py-1 font-semibold ${getScoreBadgeClass(normalizeAuditPercent(item.score, item.max_score))}`}>
                                                        {formatPercentValue(normalizeAuditPercent(item.score, item.max_score))}
                                                    </span>
                                                    <span className="ml-2 text-[11px] text-slate-500 theme-light:text-slate-600">{item.score}/{item.max_score}</span>
                                                </td>
                                                <td className="py-2 text-slate-300 theme-light:text-slate-800">{item.summary}</td>
                                                {onNavigateToFiles && (
                                                    <td className="py-2 text-center">
                                                        <button
                                                            onClick={onNavigateToFiles}
                                                            className="btn-ghost px-2.5 py-1.5 text-xs font-medium inline-flex items-center gap-1"
                                                            title="Editar esta auditoria em Arquivos"
                                                        >
                                                            <ExternalLink className="w-3 h-3" />
                                                            Editar
                                                        </button>
                                                    </td>
                                                )}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    ) : (
                        <p className="text-slate-500 text-center py-4">Nenhuma auditoria de {activeTab === 'audio' ? 'áudio' : 'documento'} encontrada.</p>
                    )}
                </div>
            </div>

            <div className="grid gap-8 xl:grid-cols-2">
                <div className="glass-panel hover-lift p-5 rounded-xl theme-light:bg-white theme-light:border-slate-300 animate-slide-up" style={{ animationDelay: '0.55s', animationFillMode: 'both' }}>
                    <h3 className="section-title mb-5">Alertas com mais auditorias</h3>
                    <div className="space-y-3">
                        {topAlerts.length > 0 ? (
                            topAlerts.map(([alertId, item], index) => (
                                <div key={alertId} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-white/5 theme-light:bg-slate-50 theme-light:border-slate-300 animate-reveal-soft" style={{ animationDelay: `${0.65 + index * 0.05}s`, animationFillMode: 'both' }}>
                                    <div>
                                        <p className="text-sm text-slate-300 font-medium">{item.label}</p>
                                        <p className="text-xs text-slate-500">Nota média: {formatPercentValue(item.avg_score_percentage ?? 0)} | Aprovação: {item.pass_rate}%</p>
                                    </div>
                                    <span className="text-sm font-bold text-slate-200 theme-light:text-slate-900">{item.count}</span>
                                </div>
                            ))
                        ) : (
                            <p className="text-slate-500 text-center py-4">Sem dados para exibir.</p>
                        )}
                    </div>
                </div>

                <div className="glass-panel hover-lift p-5 rounded-xl theme-light:bg-white theme-light:border-slate-300 animate-slide-up" style={{ animationDelay: '0.6s', animationFillMode: 'both' }}>
                    <h3 className="section-title mb-5">Critérios com mais reprovações</h3>
                    <div className="space-y-3">
                        {stats && stats.top_failed_criteria?.length ? (
                            stats.top_failed_criteria.slice(0, 6).map((item, index) => (
                                <div key={item.criterionId} className="p-3 rounded-lg bg-slate-800/50 border border-white/5 theme-light:bg-slate-50 theme-light:border-slate-300 animate-reveal-soft" style={{ animationDelay: `${0.7 + index * 0.05}s`, animationFillMode: 'both' }}>
                                    <div className="flex items-center justify-between mb-1">
                                        <p className="text-sm text-slate-300 font-medium">{item.label}</p>
                                        <span className="text-xs font-bold text-slate-300 theme-light:text-slate-800">{item.fail} falhas</span>
                                    </div>
                                    <p className="text-xs text-slate-500">Taxa de falha: {item.fail_rate}%</p>
                                </div>
                            ))
                        ) : (
                            <p className="text-slate-500 text-center py-4">Sem dados para exibir.</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}


