import { z } from 'zod';

const text = (fallback = '') =>
  z.any().transform((value): string => (value == null ? fallback : String(value)));

const nullableText = z
  .any()
  .transform((value): string | null => (value == null || value === '' ? null : String(value)));

const numberValue = (fallback = 0) =>
  z.any().transform((value): number => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  });

const booleanValue = (fallback = false) =>
  z.any().transform((value): boolean => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (['true', '1', 'yes', 'sim', 'on'].includes(normalized)) return true;
      if (['false', '0', 'no', 'nao', 'não', 'off'].includes(normalized)) return false;
    }
    return fallback;
  });

export const PipelineConfigSchema = z
  .object({
    enabled: booleanValue(false),
    horario_execucao: text('06:00'),
    max_retries: numberValue(8),
    retry_intervalo_minutos: numberValue(60),
    lookback_dias: numberValue(3),
    cota_max_por_operador_mes: numberValue(5),
    limite_auditorias: numberValue(10),
    download_max_por_operador_ciclo: numberValue(10),
  })
  .catch({
    enabled: false,
    horario_execucao: '06:00',
    max_retries: 8,
    retry_intervalo_minutos: 60,
    lookback_dias: 3,
    cota_max_por_operador_mes: 5,
    limite_auditorias: 10,
    download_max_por_operador_ciclo: 10,
  });

const PipelineLastRunSchema = z
  .object({
    date_str: text(),
    status: text('pending'),
    attempts: numberValue(0),
    last_attempt_at: nullableText,
    completed_at: nullableText,
    downloaded_count: numberValue(0).nullable().catch(null),
    skipped_quota_count: numberValue(0).nullable().catch(null),
    last_error: nullableText,
  })
  .passthrough();

export const PipelineSummarySchema = z
  .object({
    config: PipelineConfigSchema,
    now_sp: nullableText,
    proxima_execucao_sp: nullableText,
    ultima_execucao: PipelineLastRunSchema.nullable().catch(null),
  })
  .passthrough()
  .catch({
    config: PipelineConfigSchema.parse({}),
    now_sp: null,
    proxima_execucao_sp: null,
    ultima_execucao: null,
  });

const AuditProgressSchema = z
  .object({
    total: numberValue(0),
    target_count: numberValue(0),
    requested_audits: numberValue(0),
    batch_size: numberValue(0),
    operational_batch_size: numberValue(0),
    completed: numberValue(0),
    failed: numberValue(0),
    discarded: numberValue(0),
    blocked: numberValue(0),
    current_filename: text(),
    current_step: nullableText,
    is_running: booleanValue(false),
    is_cancelled: booleanValue(false),
    is_paused: booleanValue(false),
    started_at: nullableText,
    finished_at: nullableText,
    current_item_started_at: nullableText,
    last_step_at: nullableText,
    last_heartbeat_at: nullableText,
    time_budget_seconds: numberValue(0),
    item_timeout_seconds: numberValue(0),
    errors: z.array(z.object({ filename: nullableText, error: nullableText }).passthrough()).catch([]),
    message: nullableText,
    status: nullableText,
  })
  .passthrough()
  .catch({
    total: 0,
    target_count: 0,
    requested_audits: 0,
    batch_size: 0,
    operational_batch_size: 0,
    completed: 0,
    failed: 0,
    discarded: 0,
    blocked: 0,
    current_filename: '',
    current_step: null,
    is_running: false,
    is_cancelled: false,
    is_paused: false,
    started_at: null,
    finished_at: null,
    current_item_started_at: null,
    last_step_at: null,
    last_heartbeat_at: null,
    time_budget_seconds: 0,
    item_timeout_seconds: 0,
    errors: [],
    message: null,
    status: null,
  });

const D1CycleResultSchema = z
  .object({
    status: nullableText,
    message: nullableText,
    executados: z
      .array(z.object({ date_str: nullableText, result: z.any().nullable().catch(null) }).passthrough())
      .catch([]),
  })
  .passthrough()
  .nullable()
  .catch(null);

const AutomationCycleRunSchema = z
  .object({
    id: numberValue(0),
    source: text(),
    status: text('unknown'),
    stage: text('idle'),
    message: nullableText,
    started_at: nullableText,
    finished_at: nullableText,
    last_heartbeat_at: nullableText,
    baixadas: numberValue(0),
    auditadas: numberValue(0),
    error_message: nullableText,
    sync_result: D1CycleResultSchema,
    audit_result: AuditProgressSchema.nullable().catch(null),
    result: z.any().nullable().catch(null),
  })
  .passthrough()
  .nullable()
  .catch(null);

const AutomationHealthIndicatorSchema = z
  .object({
    id: text(),
    label: text(),
    value: text(),
    tone: text('neutral'),
    detail: text(),
  })
  .passthrough();

const AutomationHealthAlertSchema = z
  .object({
    id: text(),
    severity: text('info'),
    title: text(),
    detail: text(),
  })
  .passthrough();

const AutomationHealthReportSchema = z
  .object({
    status: text('ok'),
    headline: text(),
    generated_at: nullableText,
    indicators: z.array(AutomationHealthIndicatorSchema).catch([]),
    alerts: z.array(AutomationHealthAlertSchema).catch([]),
    metrics: z.record(z.string(), z.any()).catch({}),
  })
  .passthrough()
  .catch({
    status: 'ok',
    headline: '',
    generated_at: null,
    indicators: [],
    alerts: [],
    metrics: {},
  });

export const EngineStatusSchema = z
  .object({
    is_enabled: booleanValue(false),
    is_running: booleanValue(false),
    is_cycle_running: booleanValue(false),
    is_paused: booleanValue(false),
    is_cancelled: booleanValue(false),
    current_stage: text('idle'),
    current_message: nullableText,
    current_run_source: nullableText,
    started_at: nullableText,
    finished_at: nullableText,
    last_run: nullableText,
    last_run_source: nullableText,
    last_error: nullableText,
    baixadas_total: numberValue(0),
    auditadas_total: numberValue(0),
    last_sync: D1CycleResultSchema,
    last_audit: AuditProgressSchema.nullable().catch(null),
    last_result: z.any().nullable().catch(null),
    latest_run: AutomationCycleRunSchema,
    latest_run_is_stale: booleanValue(false),
    audit_progress: AuditProgressSchema,
    health_report: AutomationHealthReportSchema,
  })
  .passthrough()
  .catch({
    is_enabled: false,
    is_running: false,
    is_cycle_running: false,
    is_paused: false,
    is_cancelled: false,
    current_stage: 'idle',
    current_message: null,
    current_run_source: null,
    started_at: null,
    finished_at: null,
    last_run: null,
    last_run_source: null,
    last_error: null,
    baixadas_total: 0,
    auditadas_total: 0,
    last_sync: null,
    last_audit: null,
    last_result: null,
    latest_run: null,
    latest_run_is_stale: false,
    audit_progress: AuditProgressSchema.parse({}),
    health_report: AutomationHealthReportSchema.parse({}),
  });

const ReleaseInfoSchema = z
  .object({
    version: nullableText,
    revision: nullableText,
    service: nullableText,
    configuration: nullableText,
    commit_sha: nullableText,
    commit_short: nullableText,
    environment: nullableText,
  })
  .passthrough()
  .catch({
    version: null,
    revision: null,
    service: null,
    configuration: null,
    commit_sha: null,
    commit_short: null,
    environment: null,
  });

export const HealthStatusSchema = z
  .object({
    status: text('offline'),
    division: text('NSTECH'),
    release: ReleaseInfoSchema,
  })
  .passthrough()
  .catch({
    status: 'offline',
    division: 'NSTECH',
    release: ReleaseInfoSchema.parse({}),
  });

export type PipelineConfig = z.infer<typeof PipelineConfigSchema>;
export type PipelineSummary = z.infer<typeof PipelineSummarySchema>;
export type EngineStatus = z.infer<typeof EngineStatusSchema>;
export type AuditProgress = z.infer<typeof AuditProgressSchema>;
export type AutomationHealthReport = z.infer<typeof AutomationHealthReportSchema>;
export type HealthStatus = z.infer<typeof HealthStatusSchema>;
