import { Activity, AlertTriangle, CheckCircle2, GitBranch } from 'lucide-react';

import type { AutomationHealthReport, HealthStatus } from '../schemas';
import type { AutomationGateStatus } from '../automationViewModel';

interface AutomationHealthPanelProps {
  report: AutomationHealthReport;
  gates: AutomationGateStatus;
  health: HealthStatus;
}

const indicatorClass: Record<string, string> = {
  success: 'text-emerald-300 theme-light:text-emerald-700',
  info: 'text-sky-300 theme-light:text-sky-700',
  warning: 'text-amber-300 theme-light:text-amber-700',
  danger: 'text-rose-300 theme-light:text-rose-700',
  neutral: 'text-slate-100 theme-light:text-slate-950',
};

export function AutomationHealthPanel({ report, gates, health }: AutomationHealthPanelProps) {
  const release = health.release;
  const revision = release.revision || '-';
  const revisionLabel = revision.startsWith('auditoria-') ? revision.replace('auditoria-', '') : revision;
  const commitLabel = release.commit_short ? `commit ${release.commit_short}` : 'commit não informado';

  return (
    <section className="panel-box-lg space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-xl font-bold text-slate-50 theme-light:text-slate-950">
            <Activity className="h-5 w-5 text-primary-400" />
            Saúde da automação
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400 theme-light:text-slate-700">
            Indicadores do ciclo automático.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {gates.items.map((gate) => (
          <div
            key={gate.id}
            className="min-w-0 rounded-xl border border-white/10 bg-slate-950/30 p-4 theme-light:border-slate-300 theme-light:bg-white"
          >
            <p className="metric-label">{gate.label}</p>
            <p className={`mt-1 flex items-center gap-2 truncate text-lg font-bold ${gate.enabled ? indicatorClass.success : indicatorClass.warning}`}>
              {gate.enabled ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertTriangle className="h-4 w-4 shrink-0" />}
              {gate.enabled ? 'Ligado' : 'Desligado'}
            </p>
            <p className="mt-1 truncate text-xs text-slate-500 theme-light:text-slate-700">
              {gate.enabled ? 'Gate liberado' : 'Gate bloqueando execução'}
            </p>
          </div>
        ))}
        <div className="min-w-0 rounded-xl border border-white/10 bg-slate-950/30 p-4 theme-light:border-slate-300 theme-light:bg-white">
          <p className="metric-label">Deploy</p>
          <p className="mt-1 flex items-center gap-2 truncate text-lg font-bold text-slate-100 theme-light:text-slate-950">
            <GitBranch className="h-4 w-4 shrink-0 text-primary-400" />
            {revisionLabel}
          </p>
          <p className="mt-1 truncate text-xs text-slate-500 theme-light:text-slate-700">
            {release.version ? `v${release.version} · ${commitLabel}` : commitLabel}
          </p>
        </div>
        {(report.indicators ?? []).slice(0, 4).map((indicator) => (
          <div
            key={indicator.id || indicator.label}
            className="min-w-0 rounded-xl border border-white/10 bg-slate-950/30 p-4 theme-light:border-slate-300 theme-light:bg-white"
          >
            <p className="metric-label">{indicator.label}</p>
            <p className={`mt-1 truncate text-lg font-bold ${indicatorClass[indicator.tone] ?? indicatorClass.neutral}`}>
              {indicator.value}
            </p>
            {indicator.detail ? (
              <p className="mt-1 truncate text-xs text-slate-500 theme-light:text-slate-700">{indicator.detail}</p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
