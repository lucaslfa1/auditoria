/**
 * Orquestra a Central de Auditoria manual, acima do `useAuditFlow`.
 *
 * Mantém a fila de jobs pendentes (vários arquivos: arquivo + alerta + operador
 * + data), processa-os em sequência via `processAudio` (POST /api/audit) e
 * controla a navegação entre as telas/abas (audit, classifier, salvos,
 * supervisor, review, ia, admin, colaboradores, settings). É o estado de alto
 * nível que o App usa na aba de auditoria; não chama a IA diretamente — delega.
 */
import { useEffect, useRef, useState } from 'react';
import type { AuditAlert, AuditSector } from '../../../shared/types/audit';
import { useToast } from '../../../shared/components/ToastProvider';
import type { AuditFlowState } from './useAuditFlow';

interface PendingAuditJob {
  file: File;
  alert: AuditAlert;
  operatorName: string;
  operatorId: string;
  sectorId?: string;
  audioDate?: string;
}

type ViewType =
  | 'audit'
  | 'classifier'
  | 'colaboradores'
  | 'settings'
  | 'supervisor'
  | 'review'
  | 'salvos'
  | 'ia'
  | 'admin';

interface UseAuditOrchestratorOptions {
  flow: AuditFlowState;
  sectors: AuditSector[];
  processAudio: (
    file: File,
    selectedAlert: AuditAlert,
    operatorName?: string,
    operatorId?: string,
    sectorId?: string,
    audioDate?: string,
  ) => Promise<boolean>;
  clearActionError: () => void;
}

const normalizeForComparison = (value: string) =>
  value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');

const findAlertAcrossSectors = (
  sectors: AuditSector[],
  alertId: string,
  alertLabel: string,
): { sector: AuditSector | null; alert: AuditAlert | null } => {
  const safeRequestedId = alertId.includes('::') ? alertId.split('::').pop() ?? alertId : alertId;
  const requestedIds = [alertId, safeRequestedId].filter(Boolean);
  const normalizedRequestedLabel = normalizeForComparison(alertLabel);

  for (const sector of sectors) {
    const alertById = sector.alerts.find((item) => requestedIds.includes(item.id));
    if (alertById) {
      return { sector, alert: alertById };
    }
  }

  if (!normalizedRequestedLabel) {
    return { sector: null, alert: null };
  }

  for (const sector of sectors) {
    const alertByLabel = sector.alerts.find((item) => {
      const normalizedAlert = normalizeForComparison(item.label);
      return (
        normalizedAlert.includes(normalizedRequestedLabel) ||
        normalizedRequestedLabel.includes(normalizedAlert)
      );
    });
    if (alertByLabel) {
      return { sector, alert: alertByLabel };
    }
  }

  return { sector: null, alert: null };
};

const resolveSectorAndAlert = (
  sectors: AuditSector[],
  sectorId: string,
  sectorLabel: string,
  alertId: string,
  alertLabel: string,
) => {
  let sector: AuditSector | null = sectors.find((item) => item.id === sectorId) || null;
  if (!sector) {
    sector =
      sectors.find((item) => normalizeForComparison(item.label) === normalizeForComparison(sectorLabel)) || null;
  }

  let alert =
    sector?.alerts.find((item) => {
      const safeRequestedId = alertId.includes('::') ? alertId.split('::').pop() ?? alertId : alertId;
      return item.id === safeRequestedId || item.id === alertId;
    }) || null;

  if (!alert && sector) {
    alert =
      sector.alerts.find((item) => {
        const normalizedAlert = normalizeForComparison(item.label);
        const normalizedRequestedLabel = normalizeForComparison(alertLabel);
        return (
          normalizedAlert.includes(normalizedRequestedLabel) ||
          normalizedRequestedLabel.includes(normalizedAlert)
        );
      }) || null;
  }

  if (!alert) {
    const globalMatch = findAlertAcrossSectors(sectors, alertId, alertLabel);
    if (globalMatch.alert) {
      sector = globalMatch.sector;
      alert = globalMatch.alert;
    }
  }

  return { sector: sector || null, alert };
};

export function useAuditOrchestrator({
  flow,
  sectors,
  processAudio,
  clearActionError,
}: UseAuditOrchestratorOptions) {
  const [pendingJob, setPendingJob] = useState<PendingAuditJob | null>(null);
  const [auditedIndices, setAuditedIndices] = useState<Set<number>>(new Set());
  const { showToast } = useToast();

  const processAudioRef = useRef(processAudio);
  const clearActionErrorRef = useRef(clearActionError);

  useEffect(() => {
    processAudioRef.current = processAudio;
    clearActionErrorRef.current = clearActionError;
  }, [processAudio, clearActionError]);

  useEffect(() => {
    if (!pendingJob) return;

    const job = pendingJob;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPendingJob(null);

    clearActionErrorRef.current();
    processAudioRef
      .current(job.file, job.alert, job.operatorName, job.operatorId, job.sectorId, job.audioDate)
      .catch((err) => {
        console.error('[AuditOrchestrator] processAudio failed:', err);
      });
  }, [pendingJob]);

  const startFromClassifier = (
    audioFile: File,
    sectorId: string,
    sectorLabel: string,
    alertId: string,
    alertLabel: string,
    opName: string,
    opId: string,
    fileIndex: number,
    setView: (view: ViewType) => void,
  ) => {
    const resolved = resolveSectorAndAlert(sectors, sectorId, sectorLabel, alertId, alertLabel);

    if (!resolved.sector || !resolved.alert) {
      console.warn('[AuditOrchestrator] No alert resolved — classifier result could not be mapped to an audit context.', {
        requestedSectorId: sectorId,
        requestedSectorLabel: sectorLabel,
        requestedAlertId: alertId,
        requestedAlertLabel: alertLabel,
        foundSector: resolved.sector?.id,
        availableAlerts: resolved.sector?.alerts.map((a) => `${a.id} (${a.label})`),
      });
      showToast({
        variant: 'warning',
        title: 'Triagem sem contexto válido para auditoria',
        description: 'Revise o setor e o alerta dessa linha antes de abrir a auditoria.',
      });
      return;
    }

    flow.prepareForClassifierAudit(
      audioFile,
      resolved.sector.id,
      resolved.sector.label,
      resolved.alert.id,
      resolved.alert.label,
      opName,
      opId,
    );

    setAuditedIndices((prev) => new Set(prev).add(fileIndex));
    setView('audit');
    setPendingJob({
      file: audioFile,
      alert: resolved.alert,
      operatorName: opName,
      operatorId: opId,
      sectorId: resolved.sector.id,
      audioDate: flow.audioDate,
    });
  };

  return {
    startFromClassifier,
    auditedIndices,
  };
}

export type AuditOrchestratorState = ReturnType<typeof useAuditOrchestrator>;
