import { type ReactNode } from 'react';
import { Loader2, Settings2 } from 'lucide-react';

import type { PipelineConfig } from '../schemas';
import { RETRY_INTERVAL_OPTIONS } from '../automationViewModel';

interface AutomationConfigPanelProps {
  draft: PipelineConfig;
  pending: {
    savingConfig: keyof PipelineConfig | null;
  };
  onUpdateField: (field: keyof PipelineConfig, value: string | number | boolean) => void;
  onSaveField: (field: keyof PipelineConfig) => void;
}

export function AutomationConfigPanel({
  draft,
  pending,
  onUpdateField,
  onSaveField,
}: AutomationConfigPanelProps) {
  return (
    <section className="panel-box-lg space-y-6">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-xl font-bold text-slate-50 theme-light:text-slate-950">
          <Settings2 className="h-5 w-5 text-primary-400" />
          Configurações
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400 theme-light:text-slate-700">
          Horários, limites e comportamento da automação em caso de falhas.
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <ConfigField
          label="Horário de início"
          hint="Hora em que a automação inicia"
          saving={pending.savingConfig === 'horario_execucao'}
        >
          <input
            type="time"
            value={draft.horario_execucao}
            onChange={(event) => onUpdateField('horario_execucao', event.target.value)}
            onBlur={() => onSaveField('horario_execucao')}
            className="glass-input w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          />
        </ConfigField>

        <ConfigField
          label="Dias para trás"
          hint="Quantos dias anteriores buscar"
          saving={pending.savingConfig === 'lookback_dias'}
        >
          <NumberInput
            value={draft.lookback_dias}
            min={1}
            max={30}
            onChange={(value) => onUpdateField('lookback_dias', value)}
            onBlur={() => onSaveField('lookback_dias')}
          />
        </ConfigField>

        <ConfigField
          label="Cota mensal por operador"
          hint="Limite de operadores auditados mês"
          saving={pending.savingConfig === 'cota_max_por_operador_mes'}
        >
          <NumberInput
            value={draft.cota_max_por_operador_mes}
            min={1}
            max={50}
            onChange={(value) => onUpdateField('cota_max_por_operador_mes', value)}
            onBlur={() => onSaveField('cota_max_por_operador_mes')}
          />
        </ConfigField>

        <ConfigField
          label="Limite de downloads"
          hint="Ajusta automaticamente até a meta de auditorias"
          saving={pending.savingConfig === 'limite_ligacoes'}
        >
          <NumberInput
            value={draft.limite_ligacoes}
            min={1}
            onChange={(value) => onUpdateField('limite_ligacoes', value)}
            onBlur={() => onSaveField('limite_ligacoes')}
          />
        </ConfigField>

        <ConfigField
          label="Meta de auditorias"
          hint="Total solicitado; o backend divide em lotes"
          saving={pending.savingConfig === 'limite_auditorias'}
        >
          <NumberInput
            value={draft.limite_auditorias}
            min={1}
            onChange={(value) => onUpdateField('limite_auditorias', value)}
            onBlur={() => onSaveField('limite_auditorias')}
          />
        </ConfigField>

        <ConfigField
          label="Número de tentativas"
          hint="Quantas vezes tenta baixar se falhar (1 a 20)"
          saving={pending.savingConfig === 'max_retries'}
        >
          <NumberInput
            value={draft.max_retries}
            min={1}
            max={20}
            onChange={(value) => onUpdateField('max_retries', value)}
            onBlur={() => onSaveField('max_retries')}
          />
        </ConfigField>

        <ConfigField
          label="Espera entre tentativas"
          hint="Tempo mínimo antes de tentar de novo"
          saving={pending.savingConfig === 'retry_intervalo_minutos'}
        >
          <select
            value={String(draft.retry_intervalo_minutos)}
            onChange={(event) => onUpdateField('retry_intervalo_minutos', Number(event.target.value))}
            onBlur={() => onSaveField('retry_intervalo_minutos')}
            className="glass-input w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          >
            {RETRY_INTERVAL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </ConfigField>

        <ConfigField
          label="Cron Telefonia (Fila de Triagem)"
          hint="Busca contínua de áudios em segundo plano"
          saving={pending.savingConfig === 'telefonia_cron_sync_ativa'}
        >
          <select
            value={String(draft.telefonia_cron_sync_ativa)}
            onChange={(event) => onUpdateField('telefonia_cron_sync_ativa', event.target.value === 'true')}
            onBlur={() => onSaveField('telefonia_cron_sync_ativa')}
            className="glass-input w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          >
            <option value="true">Ligado (Baixar áudios continuamente)</option>
            <option value="false">Desligado</option>
          </select>
        </ConfigField>

        <ConfigField
          label="Intervalo Busca Telefonia (seg)"
          hint="Intervalo do Cron (padrão: 600)"
          saving={pending.savingConfig === 'automacao_intervalo_segundos'}
        >
          <NumberInput
            value={draft.automacao_intervalo_segundos}
            min={60}
            max={86400}
            onChange={(value) => onUpdateField('automacao_intervalo_segundos', value)}
            onBlur={() => onSaveField('automacao_intervalo_segundos')}
          />
        </ConfigField>
      </div>
    </section>
  );
}

function NumberInput({
  value,
  min,
  max,
  onChange,
  onBlur,
}: {
  value: number;
  min: number;
  max?: number;
  onChange: (value: number) => void;
  onBlur: () => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      onChange={(event) => onChange(Number(event.target.value))}
      onBlur={onBlur}
      className="glass-input w-full rounded-xl px-3 py-2.5 text-sm outline-none"
    />
  );
}

function ConfigField({
  label,
  hint,
  saving,
  children,
}: {
  label: string;
  hint: string;
  saving: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex h-[3.25rem] items-end justify-between gap-2">
        <label className="metric-label leading-tight">{label}</label>
        {saving ? <Loader2 className="mb-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-primary-400" /> : null}
      </div>
      {children}
      <p className="mt-1.5 text-[11px] leading-4 text-slate-500 theme-light:text-slate-700">{hint}</p>
    </div>
  );
}
