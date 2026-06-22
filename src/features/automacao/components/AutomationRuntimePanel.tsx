import { CheckCircle2, Database, Loader2, Pause, Play, XCircle } from 'lucide-react';

import type { EngineStatus, PipelineSummary } from '../schemas';
import {
  formatDateTimeBR,
  formatRelativeTime,
  getAuditView,
  getCurrentStage,
  getMainMessage,
  getProgressCounts,
  getProgressPercent,
  getStageInfo,
  sourceLabel,
  statusLabel,
  stepLabel,
  type AutomationGateStatus,
} from '../automationViewModel';

interface AutomationRuntimePanelProps {
  summary: PipelineSummary;
  engineStatus: EngineStatus;
  gates: AutomationGateStatus;
  controlAction: 'pause' | 'resume' | 'cancel' | null;
  onControl: (action: 'pause' | 'resume' | 'cancel') => void;
}

const stageToneClass = {
  neutral: 'bg-slate-500/10 text-slate-300 border-slate-500/20',
  info: 'bg-sky-500/10 text-sky-300 border-sky-500/20',
  success: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
  danger: 'bg-rose-500/10 text-rose-300 border-rose-500/20',
};

export function AutomationRuntimePanel({
  summary,
  engineStatus,
  gates,
  controlAction,
  onControl,
}: AutomationRuntimePanelProps) {
  const isEnabled = gates.allEnabled;
  const auditView = getAuditView(engineStatus);
  const stage = getCurrentStage(engineStatus, isEnabled);
  const stageInfo = getStageInfo(stage, isEnabled);
  const percent = getProgressPercent(auditView);
  const progressCounts = getProgressCounts(auditView);
  const auditDone = progressCounts.done;
  const auditTotal = progressCounts.total;
  const isIndeterminate = Boolean(engineStatus.is_running && auditTotal === 0);
  const progressWidth = isIndeterminate ? 100 : percent;
  const canControl = Boolean((engineStatus.is_running || auditView?.is_running || engineStatus.latest_run_is_stale) && !engineStatus.is_cancelled && !auditView?.is_cancelled);

  return (
    <section className="panel-box-lg space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-wide ${stageToneClass[stageInfo.tone]}`}>
              {stageInfo.label}
            </span>
            {engineStatus.is_running ? <Loader2 className="h-4 w-4 animate-spin text-sky-400" /> : null}
          </div>
          <h3 className="mt-4 text-xl font-bold text-slate-50 theme-light:text-slate-950">
            Andamento
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400 theme-light:text-slate-700">
            {getMainMessage(engineStatus, summary, gates)}
          </p>
        </div>

        {canControl ? (
          <div className="flex flex-wrap gap-2">
            {auditView?.is_paused ? (
              <button
                type="button"
                onClick={() => onControl('resume')}
                disabled={controlAction !== null}
                className="btn-success px-4 py-2"
              >
                {controlAction === 'resume' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Retomar
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onControl('pause')}
                disabled={controlAction !== null}
                className="btn-secondary px-4 py-2"
              >
                {controlAction === 'pause' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
                Pausar
              </button>
            )}
            <button
              type="button"
              onClick={() => onControl('cancel')}
              disabled={controlAction !== null}
              className="btn-danger px-4 py-2"
            >
              {controlAction === 'cancel' ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
              Cancelar
            </button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-950/30 p-5 theme-light:border-slate-300 theme-light:bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="metric-label">Auditando</p>
              <p className="mt-1 text-base font-semibold text-slate-100 theme-light:text-slate-950">
                {auditView?.is_running
                  ? auditView.current_filename || 'Processando item atual'
                  : auditTotal > 0
                    ? `${auditDone} de ${auditTotal} finalizados`
                    : 'Aguardando próxima execução'}
              </p>
            </div>
            {auditView?.is_running ? (
              auditView.is_paused ? (
                <Pause className="h-5 w-5 text-amber-400" />
              ) : (
                <Loader2 className="h-5 w-5 animate-spin text-amber-400" />
              )
            ) : (
              <CheckCircle2 className="h-5 w-5 text-emerald-400" />
            )}
          </div>

          <div>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-800 theme-light:bg-slate-200">
              <div
                className={`h-full rounded-full transition-all ${isIndeterminate ? 'animate-pulse opacity-70' : ''} ${auditView?.is_paused ? 'bg-amber-500' : 'bg-primary-500'}`}
                style={{ width: `${progressWidth}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 theme-light:text-slate-700">
              <span>
                {auditTotal > 0
                  ? `${auditDone} de ${auditTotal} finalizados`
                  : engineStatus.is_running
                    ? 'Preparando lote'
                    : 'Aguardando itens'}
              </span>
              <span>{isIndeterminate ? 'em andamento' : `${percent}%`}</span>
            </div>
            {auditTotal > 0 ? (
              <p className="mt-2 text-xs text-slate-500 theme-light:text-slate-700">
                {`${progressCounts.completed} auditados · ${progressCounts.discarded} descartados · ${progressCounts.failed} não processados`}
              </p>
            ) : null}
          </div>

          {auditView?.current_step || auditView?.last_step_at ? (
            <p className="text-xs leading-5 text-slate-500 theme-light:text-slate-700">
              {`Etapa: ${stepLabel(auditView.current_step)}`}
              {auditView.last_step_at ? ` · ${formatRelativeTime(auditView.last_step_at)}` : ''}
            </p>
          ) : null}
        </div>

        <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-950/30 p-5 theme-light:border-slate-300 theme-light:bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="metric-label">Coleta</p>
              <p className="mt-1 text-base font-semibold text-slate-100 theme-light:text-slate-950">
                {statusLabel(engineStatus.last_sync?.status)}
              </p>
            </div>
            <Database className="h-5 w-5 text-sky-400" />
          </div>

          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Metric label={engineStatus.is_running ? 'Iniciado' : 'Última coleta'} value={formatDateTimeBR(engineStatus.started_at)} />
            <Metric label={engineStatus.is_running ? 'Origem' : 'Última origem'} value={sourceLabel(engineStatus.current_run_source ?? engineStatus.last_run_source)} />
            <Metric label="Baixadas (Hoje)" value={String(engineStatus.baixadas_total ?? 0)} />
            <Metric label="Auditadas (Hoje)" value={String(engineStatus.auditadas_total ?? 0)} />
          </dl>
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/[0.03] p-3 theme-light:bg-slate-100">
      <dt className="metric-label">{label}</dt>
      <dd className="mt-1 truncate font-semibold text-slate-100 theme-light:text-slate-950">{value}</dd>
    </div>
  );
}
