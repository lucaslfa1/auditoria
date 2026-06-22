/**
 * Hook de reavaliação de uma auditoria salva (Arquivos Salvos / Auditorias do mês).
 *
 * Reusa o endpoint /api/audit/reevaluate: dado a transcrição (possivelmente com
 * interlocutor corrigido) + o alerta (possivelmente trocado), a IA refaz a
 * avaliação e devolve um AuditResult novo. TEM CUSTO de IA — chamar só sob ação
 * explícita do usuário (botão "Reavaliar"). Não persiste; o caller salva depois
 * via PUT /api/salvos/{id}.
 */
import { useState } from 'react';

import { apiFetchJson, ApiError } from '../../../shared/lib/apiClient';
import type { AuditAlert, AuditResult } from '../../../shared/types/audit';

export interface ReauditParams {
  transcription: { start: string; end: string; text: string }[];
  alert: AuditAlert;
  operatorName?: string;
  operatorId?: string;
  sectorId?: string;
  sourceType?: 'audio' | 'pdf';
  audioQuality?: unknown;
}

export function useReaudit() {
  const [isReauditing, setIsReauditing] = useState(false);
  const [reauditError, setReauditError] = useState<string | null>(null);

  const reaudit = async (params: ReauditParams): Promise<AuditResult | null> => {
    setIsReauditing(true);
    setReauditError(null);
    try {
      const data = await apiFetchJson<AuditResult>('/api/audit/reevaluate', {
        method: 'POST',
        timeoutMs: 120000,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcription: params.transcription,
          alert: params.alert,
          operator_name: params.operatorName,
          operator_id: params.operatorId,
          sector_id: params.sectorId,
          source_type: params.sourceType ?? 'audio',
          audio_quality: params.audioQuality ?? null,
        }),
      });
      if (!data || typeof data.score !== 'number' || !Array.isArray(data.details)) {
        setReauditError('Resposta inválida da IA. Tente novamente.');
        return null;
      }
      return data;
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : 'Falha ao reavaliar. Tente novamente.';
      setReauditError(msg);
      return null;
    } finally {
      setIsReauditing(false);
    }
  };

  return { reaudit, isReauditing, reauditError };
}
