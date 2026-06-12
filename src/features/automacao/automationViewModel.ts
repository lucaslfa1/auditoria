import type { AuditProgress, EngineStatus, PipelineSummary } from './schemas';
import { STAGE_LABELS } from './lib/stageLabels';

export type StageTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export interface StageInfo {
  label: string;
  description: string;
  tone: StageTone;
}

export interface AutomationGateStatus {
  allEnabled: boolean;
  disabledLabels: string[];
  items: Array<{
    // 'telefonia' saiu em 2026-06-12 junto com o gate telefonia_cron_sync_ativa.
    id: 'pipeline' | 'engine';
    label: string;
    enabled: boolean;
  }>;
}

export const RETRY_INTERVAL_OPTIONS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '1 hora' },
];

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '-';

  const diffSec = Math.round((Date.now() - ts) / 1000);
  const abs = Math.abs(diffSec);

  if (abs < 60) return diffSec >= 0 ? `há ${abs}s` : `em ${abs}s`;

  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) {
    return diffMin >= 0 ? `há ${Math.abs(diffMin)} min` : `em ${Math.abs(diffMin)} min`;
  }

  const diffHour = Math.round(diffMin / 60);
  if (Math.abs(diffHour) < 24) {
    return diffHour >= 0 ? `há ${Math.abs(diffHour)}h` : `em ${Math.abs(diffHour)}h`;
  }

  const diffDay = Math.round(diffHour / 24);
  return diffDay >= 0 ? `há ${Math.abs(diffDay)}d` : `em ${Math.abs(diffDay)}d`;
}

export function formatDateBR(yyyymmdd: string | null | undefined): string {
  if (!yyyymmdd || yyyymmdd.length !== 8) return yyyymmdd || '-';
  return `${yyyymmdd.slice(6, 8)}/${yyyymmdd.slice(4, 6)}/${yyyymmdd.slice(0, 4)}`;
}

export function formatDateTimeBR(iso: string | null | undefined): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function secondsSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return null;
  return Math.max(0, Math.round((Date.now() - ts) / 1000));
}

export function sourceLabel(source: string | null | undefined): string {
  const labels: Record<string, string> = {
    manual_ui: 'Manual pela tela',
    cloud_scheduler: 'Agendamento automático',
    resident_loop: 'Rotina interna',
    manual: 'Manual',
  };
  return source ? labels[source] ?? 'Origem não identificada' : '-';
}

export function statusLabel(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    completed: 'Concluído',
    partial: 'Concluído com atenção',
    in_progress: 'Em andamento',
    empty: 'Sem ligações novas',
    error: 'Falhou',
    pending: 'Pendente',
    ok: 'Tudo certo',
    running: 'Em andamento',
    skipped: 'Ignorado',
    disabled: 'Desligado',
  };
  return status ? labels[status] ?? status : '-';
}

export function getAuditView(engineStatus: EngineStatus): AuditProgress | null {
  if (engineStatus.audit_progress?.is_running) return engineStatus.audit_progress;
  if (engineStatus.last_audit?.is_running) return engineStatus.last_audit;
  return engineStatus.audit_progress ?? engineStatus.last_audit ?? null;
}

export function getStageInfo(stage: string, isEnabled: boolean): StageInfo {
  if (!isEnabled || stage === 'disabled') {
    return STAGE_LABELS.disabled;
  }
  return STAGE_LABELS[stage] ?? STAGE_LABELS.idle;
}

export function getCurrentStage(engineStatus: EngineStatus, isEnabled: boolean): string {
  const auditView = getAuditView(engineStatus);
  const itemStalled = getAuditProgressStaleInfo(auditView).isStale;

  if (engineStatus.latest_run_is_stale || itemStalled) return 'stale';
  if (engineStatus.is_paused || auditView?.is_paused) return 'paused';
  if (!isEnabled) return 'disabled';
  return engineStatus.current_stage || 'idle';
}

export function getProgressCounts(progress: AuditProgress | null): {
  total: number;
  completed: number;
  failed: number;
  discarded: number;
  blocked: number;
  done: number;
} {
  const total = Math.max(
    progress?.total ?? 0,
    progress?.requested_audits ?? 0,
    progress?.target_count ?? 0,
  );
  const completed = progress?.completed ?? 0;
  const failed = progress?.failed ?? 0;
  const discarded = progress?.discarded ?? 0;
  const blocked = progress?.blocked ?? 0;
  return {
    total,
    completed,
    failed,
    discarded,
    blocked,
    done: completed + failed + discarded,
  };
}

export function getProgressPercent(progress: AuditProgress | null): number {
  const { total, done } = getProgressCounts(progress);
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((done / total) * 100)));
}

export function getAuditProgressStaleInfo(progress: AuditProgress | null): {
  isStale: boolean;
  heartbeatAgeSeconds: number | null;
  thresholdSeconds: number;
} {
  const configuredItemTimeout = Number(progress?.item_timeout_seconds ?? 0);
  const configuredBudget = Number(progress?.time_budget_seconds ?? 0);
  const configuredThreshold = Number.isFinite(configuredItemTimeout) && configuredItemTimeout > 0
    ? configuredItemTimeout
    : configuredBudget;
  const thresholdSeconds = Number.isFinite(configuredThreshold) && configuredThreshold > 0
    ? Math.max(360, Math.min(1860, Math.round(configuredThreshold) + 60))
    : 660;
  const heartbeatAgeSeconds = secondsSince(progress?.last_heartbeat_at ?? progress?.last_step_at);
  const isStale = Boolean(
    progress?.is_running &&
    !progress.is_paused &&
    heartbeatAgeSeconds !== null &&
    heartbeatAgeSeconds > thresholdSeconds
  );

  return { isStale, heartbeatAgeSeconds, thresholdSeconds };
}

export function getMainMessage(
  engineStatus: EngineStatus,
  summary: PipelineSummary,
  gates?: AutomationGateStatus,
): string {
  const auditView = getAuditView(engineStatus);
  const itemStalled = getAuditProgressStaleInfo(auditView).isStale;

  if (gates && !gates.allEnabled) {
    return `Rotina desligada: ${gates.disabledLabels.join(', ')}.`;
  }
  if (!summary.config.enabled) return 'Rotina desligada. Ligue para iniciar o ciclo.';
  if (engineStatus.latest_run_is_stale || itemStalled) {
    return 'Aguardando atualização do processamento.';
  }
  if (engineStatus.current_message) return humanizeMessage(engineStatus.current_message);
  if (engineStatus.is_running) return 'Ciclo em andamento.';
  return 'Aguardando próximo horário.';
}

export function humanizeMessage(message: string): string {
  return message
    .replace(/running/gi, 'em andamento')
    .replace(/Automacao/g, 'Automação')
    .replace(/automacao/g, 'automação')
    .replace(/instancia/g, 'instância')
    .replace(/pipeline/gi, 'rotina')
    .replace(/backend/gi, 'servidor')
    .replace(/heartbeat/gi, 'sinal de progresso')
    .replace(/OBS/g, 'armazenamento')
    .replace(/D-1/g, 'diário');
}

export function stepLabel(step: string | null | undefined): string {
  if (!step) return 'Em andamento';

  const labels: Record<string, string> = {
    syncing_d1: 'Coletando ligações',
    auditing: 'Auditando',
    transcribing: 'Transcrevendo',
    evaluating: 'Avaliando critérios',
    saving: 'Salvando',
    classifying: 'Classificando',
    downloading: 'Baixando',
  };

  return labels[step] ?? humanizeMessage(step.replace(/_/g, ' '));
}
