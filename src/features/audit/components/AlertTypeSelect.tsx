/**
 * Seletor do TIPO de alerta de uma auditoria, populado pelos alertas oficiais do
 * setor (via AuditCriteriaContext / GET /api/criteria/export). Usado no modo
 * edição de Arquivos Salvos e Auditorias do mês para corrigir a classificação
 * antes de "Reavaliar". Helpers puros vivem em ../lib/alertCatalog.
 */
import { useAuditCriteria } from '../../../contexts/AuditCriteriaContext';
import { findSector } from '../lib/alertCatalog';

interface AlertTypeSelectProps {
  sectorId?: string;
  /** id do alerta atualmente selecionado. */
  value: string;
  onChange: (alertId: string, alertLabel: string) => void;
  disabled?: boolean;
  className?: string;
}

export function AlertTypeSelect({ sectorId, value, onChange, disabled, className }: AlertTypeSelectProps) {
  const { data } = useAuditCriteria();
  const sector = findSector(data, sectorId);
  const alerts = sector?.alerts ?? [];
  const knownValue = alerts.some((a) => a.id === value);

  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => {
        const next = alerts.find((a) => a.id === e.target.value);
        onChange(e.target.value, next?.label ?? '');
      }}
      className={
        className ??
        'text-xs rounded-lg border px-2.5 py-1.5 min-w-[220px] bg-slate-800 border-white/15 text-slate-200 focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900'
      }
    >
      {/* Mantém o valor atual visível mesmo se não estiver no catálogo do setor
          (ex.: alerta legado/"desconhecido") para não perder a seleção. */}
      {!knownValue && value ? <option value={value}>{value}</option> : null}
      {!value ? <option value="">Selecione um alerta…</option> : null}
      {alerts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.label}
        </option>
      ))}
    </select>
  );
}
