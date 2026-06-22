/**
 * Helpers puros sobre o catálogo de critérios (AuditCriteriaContext) para a troca
 * de tipo de alerta em auditorias salvas. Em arquivo separado do componente
 * `AlertTypeSelect` para não violar react-refresh/only-export-components.
 */
import type { AuditCriteriaData, Sector } from '../../../contexts/AuditCriteriaContext';
import type { AuditAlert } from '../../../shared/types/audit';

/** Acha o setor no catálogo por id (com fallback case-insensitive). */
export function findSector(data: AuditCriteriaData | null, sectorId?: string): Sector | undefined {
  if (!data || !sectorId) return undefined;
  const norm = sectorId.trim().toLowerCase();
  return data.sectors.find((s) => s.id === sectorId) || data.sectors.find((s) => s.id.toLowerCase() === norm);
}

/**
 * Monta um AuditAlert (id + label + critérios oficiais) a partir do catálogo. O
 * backend re-resolve os critérios pelo id, mas mandamos os do catálogo também.
 * Retorna null se o alerta não existir no setor.
 */
export function buildAuditAlertFromCriteria(
  data: AuditCriteriaData | null,
  sectorId: string | undefined,
  alertId: string,
): AuditAlert | null {
  const sector = findSector(data, sectorId);
  const alert = sector?.alerts.find((a) => a.id === alertId);
  if (!alert) return null;
  return {
    id: alert.id,
    label: alert.label,
    context: alert.context || 'Geral',
    criteria: (alert.criteria || []).map((c) => ({
      id: c.id,
      label: c.label,
      weight: c.weight,
      description: c.description,
    })),
  };
}

/**
 * Resolve o id do alerta a partir do rótulo salvo (arquivos_salvos guarda só o
 * alert_label, não o id). Pré-seleciona o alerta atual no dropdown e permite
 * reavaliar mantendo o mesmo alerta (ex.: troca só de interlocutor). Retorna ''
 * se o rótulo não casar com nenhum alerta do setor.
 */
export function findAlertIdByLabel(
  data: AuditCriteriaData | null,
  sectorId: string | undefined,
  alertLabel: string,
): string {
  const sector = findSector(data, sectorId);
  if (!sector || !alertLabel) return '';
  const norm = alertLabel.trim().toLowerCase();
  const match = sector.alerts.find((a) => (a.label || '').trim().toLowerCase() === norm);
  return match?.id ?? '';
}
