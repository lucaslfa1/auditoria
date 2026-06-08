import { Activity, CalendarClock, Loader2, Play, Power } from 'lucide-react';

import type { EngineStatus, PipelineSummary } from '../schemas';
import {
  formatDateTimeBR,
  formatRelativeTime,
  getAuditView,
  getCurrentStage,
  getStageInfo,
  stepLabel,
} from '../automationViewModel';

interface AutomationControlHeroProps {
  summary: PipelineSummary;
  engineStatus: EngineStatus;
  isEnabled: boolean;
  pending: {
    toggling: boolean;
    runningNow: boolean;
  };
  onToggle: (enabled: boolean) => void;
  onRunNow: () => void;
}

const toneClass = {
  neutral: 'border-slate-500/25 bg-slate-500/10 text-slate-300 theme-light:text-slate-800',
  info: 'border-sky-500/25 bg-sky-500/10 text-sky-300 theme-light:text-sky-800',
  success: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300 theme-light:text-emerald-800',
  warning: 'border-amber-500/25 bg-amber-500/10 text-amber-300 theme-light:text-amber-800',
  danger: 'border-rose-500/25 bg-rose-500/10 text-rose-300 theme-light:text-rose-800',
} as const;

export function AutomationControlHero({
  summary,
  engineStatus,
  isEnabled,
  pending,
  onToggle,
  onRunNow,
}: AutomationControlHeroProps) {
  const isRunning = (engineStatus.is_running || engineStatus.is_cycle_running) && !engineStatus.latest_run_is_stale;
  const manualDisabled = isRunning || pending.runningNow;
  const stage = isRunning ? getCurrentStage(engineStatus, isEnabled) : isEnabled ? 'idle' : 'disabled';
  const stageInfo = getStageInfo(stage, isEnabled);
  const auditView = getAuditView(engineStatus);
  const runningStep = auditView?.current_step ?? engineStatus.current_stage;
  const proxima = isEnabled && summary.proxima_execucao_sp ? summary.proxima_execucao_sp : null;

  return (
    <section className="panel-box-lg space-y-6">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-xl font-bold text-slate-50 theme-light:text-slate-950">
          <Activity className="h-5 w-5 text-primary-400" />
          Controles de execução
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400 theme-light:text-slate-700">
          Ligue ou desligue o agendamento automático, ou inicie o processamento agora mesmo.
        </p>
      </div>

      <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-stretch">
          <button
            type="button"
            onClick={() => onToggle(!isEnabled)}
            disabled={pending.toggling}
            aria-pressed={isEnabled}
            aria-label={isEnabled ? 'Desligar rotina automática' : 'Ligar rotina automática'}
            className={`group flex w-full items-center gap-4 rounded-2xl border px-5 py-4 transition sm:w-auto ${
              isEnabled
                ? 'border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/15'
                : 'border-white/10 bg-white/5 hover:bg-white/10 theme-light:border-slate-300 theme-light:bg-white'
            }`}
          >
            <span
              className={`inline-flex h-12 w-12 items-center justify-center rounded-xl ${
                isEnabled
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : 'bg-slate-500/15 text-slate-400 theme-light:bg-slate-200 theme-light:text-slate-600'
              }`}
            >
              {pending.toggling ? <Loader2 className="h-6 w-6 animate-spin" /> : <Power className="h-6 w-6" />}
            </span>
            <span className="text-left pr-2">
              <span className="metric-label">Automação</span>
              <span
                className={`mt-0.5 block text-xl font-bold ${
                  isEnabled ? 'text-emerald-300 theme-light:text-emerald-700' : 'text-slate-100 theme-light:text-slate-950'
                }`}
              >
                {isEnabled ? 'Operacional' : 'Interrompida'}
              </span>
            </span>
          </button>

          <button
            type="button"
            onClick={onRunNow}
            disabled={manualDisabled}
            className="group flex w-full items-center gap-4 rounded-2xl border border-transparent bg-primary-600 px-5 py-4 text-white transition hover:bg-primary-500 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-primary-600 sm:w-auto shadow-sm"
          >
            <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-white/20 text-white transition group-hover:bg-white/30">
              {pending.runningNow ? <Loader2 className="h-6 w-6 animate-spin" /> : <Play className="h-6 w-6" fill="currentColor" />}
            </span>
            <span className="text-left pr-2">
              <span className="metric-label text-primary-200 theme-light:text-primary-200">Forçar</span>
              <span className="mt-0.5 block text-xl font-bold">Automação</span>
            </span>          </button>
        </div>

        <div className="flex flex-1 flex-col gap-2 sm:items-start lg:items-end lg:border-l lg:border-white/10 lg:pl-6 theme-light:lg:border-slate-300">
          {isEnabled && (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-wide ${toneClass[stageInfo.tone]}`}
            >
              {stageInfo.label}
            </span>
          )}
          {stageInfo.description && (
            <p className="text-sm text-slate-300 theme-light:text-slate-800">{stageInfo.description}</p>
          )}
          {isEnabled && (
            <div className="flex items-center gap-1.5 text-xs text-slate-400 theme-light:text-slate-700">
              <CalendarClock className="h-3.5 w-3.5" />
              {proxima ? (
                <span>
                  Próxima: <strong className="text-slate-200 theme-light:text-slate-900">{formatRelativeTime(proxima)}</strong>
                  <span className="ml-1 text-slate-500">· {formatDateTimeBR(proxima)}</span>
                </span>
              ) : (
                <span>Aguardando agenda</span>
              )}
            </div>
          )}

          {(isRunning || pending.runningNow) && (
            <div className="w-full max-w-sm">
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-800 theme-light:bg-slate-200">
                <div className="h-full w-full animate-pulse rounded-full bg-primary-500 opacity-75" />
              </div>
              <p className="mt-2 text-xs text-slate-400 theme-light:text-slate-700">
                {pending.runningNow ? 'Iniciando ciclo manual' : stepLabel(runningStep)}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
