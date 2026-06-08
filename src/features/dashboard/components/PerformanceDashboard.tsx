import { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend, Cell
} from 'recharts';
import {
  TrendingUp, TrendingDown, Users, ClipboardCheck,
  AlertTriangle, BarChart3, RefreshCw, ChevronDown
} from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';

interface SectorIndicator {
  sector_id: string;
  sector_label: string;
  total_auditorias: number;
  media_percentual: number;
}

interface SupervisorIndicator {
  supervisor: string;
  total_auditorias: number;
  total_operadores: number;
  media_percentual: number;
}

interface TrendPoint {
  mes: string;
  total_auditorias: number;
  media_percentual: number;
}

interface TopFailure {
  criterio: string;
  total_avaliacoes: number;
  falhas: number;
  taxa_falha_percent: number;
}

interface MatchingQuality {
  total_operadores_distintos: number;
  vinculados_por_fk: number;
  match_exato_por_nome: number;
  sem_correspondencia: number;
  taxa_vinculacao_percent: number;
  total_colaboradores: number;
}

const CHART_COLORS = [
  '#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899',
  '#14b8a6', '#f59e0b', '#6366f1', '#ef4444', '#06b6d4'
];

const MONTHS = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
];

function KPICard({ title, value, subtitle, icon: Icon, trend, color }: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof TrendingUp;
  trend?: 'up' | 'down' | 'neutral';
  color: string;
}) {
  return (
    <div className="perf-kpi-card">
      <div className="flex items-start justify-between mb-3">
        <div className={`perf-kpi-icon ${color}`}>
          <Icon size={20} />
        </div>
        {trend && (
          <div className={`perf-kpi-trend ${trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-slate-400'}`}>
            {trend === 'up' ? <TrendingUp size={16} /> : trend === 'down' ? <TrendingDown size={16} /> : null}
          </div>
        )}
      </div>
      <p className="perf-kpi-value">{value}</p>
      <p className="perf-kpi-title">{title}</p>
      {subtitle && <p className="perf-kpi-subtitle">{subtitle}</p>}
    </div>
  );
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="perf-tooltip">
      <p className="perf-tooltip-label">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="perf-tooltip-value" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
          {entry.name.includes('%') || entry.name.includes('Média') ? '%' : ''}
        </p>
      ))}
    </div>
  );
}

export function PerformanceDashboard() {
  const now = new Date();
  const [month, setMonth] = useState<number>(now.getMonth() + 1);
  const [year, setYear] = useState<number>(now.getFullYear());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sectors, setSectors] = useState<SectorIndicator[]>([]);
  const [supervisors, setSupervisors] = useState<SupervisorIndicator[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [topFailures, setTopFailures] = useState<TopFailure[]>([]);
  const [matching, setMatching] = useState<MatchingQuality | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [indicatorsRes, trendRes, failuresRes, matchingRes, supRes] = await Promise.all([
        apiFetchJson<{ by_sector: SectorIndicator[]; trend: TrendPoint[]; top_failures: TopFailure[] }>(
          `/api/analytics/indicators?month=${month}&year=${year}`
        ),
        apiFetchJson<TrendPoint[]>('/api/analytics/trend?months=6'),
        apiFetchJson<TopFailure[]>(`/api/analytics/top-failures?month=${month}&year=${year}&limit=10`),
        apiFetchJson<MatchingQuality>(`/api/analytics/matching-quality?month=${month}&year=${year}`),
        apiFetchJson<SupervisorIndicator[]>(
          `/api/analytics/indicators/supervisors?month=${month}&year=${year}`
        ),
      ]);

      setSectors(indicatorsRes.by_sector || []);
      setTrend(trendRes || []);
      setTopFailures(failuresRes || []);
      setMatching(matchingRes);
      setSupervisors(supRes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
    } finally {
      setIsLoading(false);
    }
  }, [month, year]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Compute KPIs
  const totalAuditorias = sectors.reduce((sum, s) => sum + s.total_auditorias, 0);
  const mediaGeral = sectors.length > 0
    ? sectors.reduce((sum, s) => sum + (s.media_percentual || 0) * s.total_auditorias, 0) / Math.max(totalAuditorias, 1)
    : 0;
  const totalOperadores = supervisors.reduce((sum, s) => sum + s.total_operadores, 0);

  // Trend direction
  const trendDirection: 'up' | 'down' | 'neutral' = trend.length >= 2
    ? (trend[trend.length - 1].media_percentual > trend[trend.length - 2].media_percentual ? 'up' : 'down')
    : 'neutral';

  // Supervisor chart data (top 10, sorted)
  const supervisorChartData = [...supervisors]
    .filter(s => s.total_auditorias > 0)
    .sort((a, b) => (b.media_percentual || 0) - (a.media_percentual || 0))
    .slice(0, 10)
    .map(s => ({
      name: s.supervisor.length > 18 ? s.supervisor.substring(0, 18) + '...' : s.supervisor,
      'Média %': s.media_percentual || 0,
      'Auditorias': s.total_auditorias,
    }));

  // Trend chart data — format months
  const trendChartData = trend.map(t => {
    const [y, m] = t.mes.split('-');
    return {
      mes: `${MONTHS[parseInt(m) - 1]?.substring(0, 3)}/${y.substring(2)}`,
      'Média %': t.media_percentual,
      'Total': t.total_auditorias,
    };
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Carregando indicadores...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel rounded-2xl p-8 text-center">
        <AlertTriangle size={32} className="mx-auto text-red-400 mb-3" />
        <p className="text-red-400 mb-4">{error}</p>
        <button onClick={fetchData} className="btn-primary px-6 py-2 rounded-xl text-sm">Tentar novamente</button>
      </div>
    );
  }

  return (
    <div className="perf-dashboard">
      {/* Header */}
      <div className="perf-header">
        <div>
          <p className="page-eyebrow">nstech | Indicadores</p>
          <h1 className="page-title">
            Dashboard de <span className="page-title-accent">Performance</span>
          </h1>
          <p className="page-subtitle">Visão consolidada de qualidade por operador, supervisor e setor.</p>
        </div>

        <div className="perf-filters">
          <div className="perf-select-wrapper">
            <select
              value={month}
              onChange={e => setMonth(parseInt(e.target.value))}
              className="perf-select"
            >
              {MONTHS.map((m, i) => (
                <option key={i} value={i + 1}>{m}</option>
              ))}
            </select>
            <ChevronDown size={14} className="perf-select-icon" />
          </div>
          <div className="perf-select-wrapper">
            <select
              value={year}
              onChange={e => setYear(parseInt(e.target.value))}
              className="perf-select"
            >
              {[2024, 2025, 2026, 2027].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <ChevronDown size={14} className="perf-select-icon" />
          </div>
          <button onClick={fetchData} className="perf-refresh-btn" title="Atualizar dados">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="perf-kpi-grid">
        <KPICard
          title="Nota Média"
          value={`${mediaGeral.toFixed(1)}%`}
          subtitle={`${totalAuditorias} auditorias no período`}
          icon={BarChart3}
          trend={trendDirection}
          color="bg-primary-500/20 text-primary-400"
        />
        <KPICard
          title="Total de Auditorias"
          value={totalAuditorias}
          subtitle={`Em ${sectors.length} setores`}
          icon={ClipboardCheck}
          color="bg-blue-500/20 text-blue-400"
        />
        <KPICard
          title="Operadores Auditados"
          value={totalOperadores}
          subtitle={`${supervisors.length} supervisores`}
          icon={Users}
          color="bg-emerald-500/20 text-emerald-400"
        />
        <KPICard
          title="Vinculação"
          value={matching ? `${matching.taxa_vinculacao_percent}%` : 'N/A'}
          subtitle={matching ? `${matching.sem_correspondencia} sem match` : ''}
          icon={TrendingUp}
          color="bg-violet-500/20 text-violet-400"
        />
      </div>

      {/* Charts Row */}
      <div className="perf-charts-row">
        {/* Supervisor bar chart */}
        <div className="perf-chart-card perf-chart-card--wide">
          <h3 className="perf-chart-title">Score Médio por Supervisor</h3>
          {supervisorChartData.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">Sem dados para o período selecionado</p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={supervisorChartData} layout="vertical" margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={130}
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="Média %" radius={[0, 6, 6, 0]} maxBarSize={24}>
                  {supervisorChartData.map((_, index) => (
                    <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Monthly trend */}
        <div className="perf-chart-card">
          <h3 className="perf-chart-title">Tendência Mensal</h3>
          {trendChartData.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">Sem dados de tendência</p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={trendChartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="mes" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                <Line
                  type="monotone"
                  dataKey="Média %"
                  stroke="#f97316"
                  strokeWidth={3}
                  dot={{ r: 5, fill: '#f97316' }}
                  activeDot={{ r: 7 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Sector & Failures Row */}
      <div className="perf-charts-row">
        {/* Sector performance */}
        <div className="perf-chart-card">
          <h3 className="perf-chart-title">Performance por Setor</h3>
          {sectors.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">Sem dados</p>
          ) : (
            <div className="perf-table-container">
              <table className="perf-table">
                <thead>
                  <tr>
                    <th>Setor</th>
                    <th className="text-right">Auditorias</th>
                    <th className="text-right">Média</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((s, i) => (
                    <tr key={i}>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                          <span className="truncate">{s.sector_label || s.sector_id}</span>
                        </div>
                      </td>
                      <td className="text-right tabular-nums">{s.total_auditorias}</td>
                      <td className="text-right">
                        <span className={`perf-badge ${(s.media_percentual || 0) >= 80 ? 'perf-badge--success' : (s.media_percentual || 0) >= 60 ? 'perf-badge--warning' : 'perf-badge--danger'}`}>
                          {(s.media_percentual || 0).toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Top failures */}
        <div className="perf-chart-card perf-chart-card--wide">
          <h3 className="perf-chart-title">
            <AlertTriangle size={16} className="text-amber-400 inline mr-2" />
            Top Critérios com Maior Taxa de Falha
          </h3>
          {topFailures.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-10">Sem falhas registradas</p>
          ) : (
            <div className="perf-table-container">
              <table className="perf-table">
                <thead>
                  <tr>
                    <th>Critério</th>
                    <th className="text-right">Avaliações</th>
                    <th className="text-right">Falhas</th>
                    <th className="text-right">Taxa</th>
                  </tr>
                </thead>
                <tbody>
                  {topFailures.map((f, i) => (
                    <tr key={i}>
                      <td className="max-w-[200px] truncate">{f.criterio}</td>
                      <td className="text-right tabular-nums">{f.total_avaliacoes}</td>
                      <td className="text-right tabular-nums">{f.falhas}</td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="perf-progress-bar">
                            <div
                              className="perf-progress-fill"
                              style={{ width: `${Math.min(f.taxa_falha_percent, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs tabular-nums text-slate-300 w-12 text-right">{f.taxa_falha_percent.toFixed(2)}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
