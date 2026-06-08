import { useEffect, useState, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { AuditAlert, AuditResult, AuditResultDetail, TranscriptionSegment } from '../../../shared/types/audit';
import type { AuditCorrectionPayload } from './useTranscription';
import { apiFetchJson } from '../../../shared/lib/apiClient';

interface UseAuditResultEditorOptions {
  auditResult: AuditResult | null;
  selectedAlert: AuditAlert | null;
  operatorName: string;
  operatorId: string;
  selectedSectorId?: string;
  reevaluateTranscription: (
    editedTranscription: TranscriptionSegment[],
    selectedAlert: AuditAlert,
    currentResult?: AuditResult | null,
    operatorName?: string,
    operatorId?: string,
    sectorId?: string
  ) => Promise<boolean>;
  setAuditResult: Dispatch<SetStateAction<AuditResult | null>>;
  regenerateSummaryText: (
    transcription: TranscriptionSegment[],
    alert: AuditAlert,
    details: AuditResultDetail[],
    operatorName?: string
  ) => Promise<{ summary: string; ai_feedback: string } | null>;
  isRegeneratingSummary: boolean;
  updateSavedAudit?: (result: AuditResult) => Promise<boolean>;
  recordAuditCorrections?: (payload: AuditCorrectionPayload) => Promise<boolean>;
}

const normalizeDetailStatus = (rawStatus: unknown): AuditResultDetail['status'] => {
  const normalized = String(rawStatus || '').trim().toLowerCase();
  return ['pass', 'na', 'n/a', 'pending_manual'].includes(normalized) ? 'pass' : 'fail';
};

const cloneDetails = (details: AuditResultDetail[]) =>
  details.map((detail) => ({ ...detail, status: normalizeDetailStatus(detail.status) }));

/**
 * Compara dois arrays de detalhes considerando apenas os campos que influenciam
 * o resumo (status + comentário). Usada para detectar "summary stale" — quando
 * o auditor mexeu nos cards mas o resumo ainda reflete a versão antiga.
 */
const detailsDiverge = (a: AuditResultDetail[], b: AuditResultDetail[]): boolean => {
  if (a.length !== b.length) return true;
  for (let i = 0; i < a.length; i++) {
    if (a[i].criterionId !== b[i].criterionId) return true;
    if (a[i].status !== b[i].status) return true;
    if ((a[i].comment || '') !== (b[i].comment || '')) return true;
  }
  return false;
};

const getObtainedScore = (detail: Pick<AuditResultDetail, 'status' | 'weight' | 'deflator'>) => {
  const d = Math.abs(detail.deflator ?? 0);
  if (detail.status === 'pass') {
    return detail.weight;
  }
  // fail
  return -d;
};

const calculateScores = (details: AuditResultDetail[], sectorId?: string) => {
  let score = 0;
  let maxScore = 0;
  let zeroed = false;

  const RASTREAMENTO_SECTORS = ['bas', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
  const sec = (sectorId || '').toLowerCase().trim();

  for (const detail of details) {
    maxScore += detail.weight;
    score += getObtainedScore(detail);

    // Regra de zeragem (Fatal) do backend replicada
    if (
      RASTREAMENTO_SECTORS.includes(sec) &&
      detail.label &&
      detail.label.toLowerCase().includes('senha') &&
      detail.status === 'fail'
    ) {
      zeroed = true;
    }
  }

  // Falha crítica de comportamento / abandono (fallback)
  if (!zeroed) {
    for (const detail of details) {
      if (detail.status === 'fail') {
        const text = `${detail.label} ${detail.comment || ''}`.toLowerCase();
        if (
          ['cadastro', 'mondelez'].includes(sec) &&
          (text.includes('45 segundos') || text.includes('comportamento hostil') || text.includes('incomum') || text.includes('abandono'))
        ) {
          zeroed = true;
        } else if (
          ['logistica', 'logistica_unilever', 'operacao_taborda'].includes(sec) &&
          (text.includes('comportamento hostil') || text.includes('incomum') || text.includes('abandono'))
        ) {
          zeroed = true;
        } else if (
          RASTREAMENTO_SECTORS.includes(sec) &&
          (text.includes('comportamento hostil') ||
            text.includes('incomum') ||
            text.includes('abandono') ||
            text.includes('dica de senha') ||
            text.includes('dica da senha') ||
            text.includes('senha ou cpf'))
        ) {
          zeroed = true;
        }
      }
    }
  }

  if (zeroed) {
    score = 0;
  }

  return { score, maxScore };
};

export function useAuditResultEditor({
  auditResult,
  selectedAlert,
  operatorName,
  operatorId,
  selectedSectorId,
  reevaluateTranscription,
  setAuditResult,
  regenerateSummaryText,
  isRegeneratingSummary,
  updateSavedAudit,
  recordAuditCorrections,
}: UseAuditResultEditorOptions) {
  const [isEditingTranscription, setIsEditingTranscription] = useState(false);
  const [tempTranscription, setTempTranscription] = useState<TranscriptionSegment[]>([]);
  const [isEditingResult, setIsEditingResult] = useState(false);
  const [tempDetails, setTempDetails] = useState<AuditResultDetail[]>([]);
  const [tempScore, setTempScore] = useState(0);
  const [tempMaxScore, setTempMaxScore] = useState(0);
  const [tempSummary, setTempSummary] = useState('');
  const [tempFeedback, setTempFeedback] = useState('');
  // Snapshot dos detalhes que correspondem ao resumo atual. Usado para saber
  // se o usuário editou critérios depois da última geração do resumo.
  const [alignedDetails, setAlignedDetails] = useState<AuditResultDetail[]>([]);
  const [baselineDetails, setBaselineDetails] = useState<AuditResultDetail[]>([]);
  const [summaryEditedManually, setSummaryEditedManually] = useState(false);
  const [feedbackEditedManually, setFeedbackEditedManually] = useState(false);
  const [lastCorrectionLearning, setLastCorrectionLearning] = useState<AuditCorrectionPayload | null>(null);
  // Backup do resumo/feedback anterior à última regeneração, para permitir
  // desfazer a reescrita da I.A. sem perder edições manuais feitas antes dela.
  const [preRegenBackup, setPreRegenBackup] = useState<{ summary: string; feedback: string } | null>(null);

  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Carrega rascunho automaticamente ao abrir
  useEffect(() => {
    if (!auditResult?.input_hash) return;
    
    // Ignore se já está salvo ou finalizado
    // @ts-expect-error: auditResult.status might not be strongly typed here
    if (['approved', 'contestation_pending_review', 'discarded'].includes(auditResult.status || '')) return;
    
    let isMounted = true;
    
    apiFetchJson<{ok: boolean; draft: any}>(`/api/audit/draft/${auditResult.input_hash}`)
      .then((res: any) => {
         if (!isMounted || !res.draft) return;
         
         const hasDraftDetails = res.draft.details_json && res.draft.details_json !== '[]';
         const hasDraftTranscription = res.draft.transcription_json && res.draft.transcription_json !== '[]';
         
         if (hasDraftDetails) {
            try {
               const parsedDetails = cloneDetails(JSON.parse(res.draft.details_json) as AuditResultDetail[]);
               setTempDetails(parsedDetails);
               const { score, maxScore } = calculateScores(parsedDetails, selectedSectorId);
               setTempScore(score);
               setTempMaxScore(maxScore);
               setIsEditingResult(true);
            } catch (e) {
               console.error('Failed to parse draft details', e);
            }
         }
         
         if (hasDraftTranscription) {
            try {
               const parsedTrans = JSON.parse(res.draft.transcription_json);
               setTempTranscription(parsedTrans);
               setIsEditingTranscription(true);
            } catch (e) {
               console.error('Failed to parse draft transcription', e);
            }
         }
      })
      .catch(() => {
         // ignorar 404 (sem rascunho)
      });
      
    return () => { isMounted = false; };
  }, [auditResult?.input_hash]); // apenas roda ao trocar de auditoria

  // Auto-save quando há mudanças locais
  useEffect(() => {
     if (!auditResult?.input_hash) return;
     if (!isEditingResult && !isEditingTranscription) return;
     
     if (autosaveTimerRef.current) {
        clearTimeout(autosaveTimerRef.current);
     }
     
     autosaveTimerRef.current = setTimeout(() => {
        apiFetchJson(`/api/audit/draft/${auditResult.input_hash}`, {
           method: 'PUT',
           body: JSON.stringify({
              details_json: isEditingResult ? JSON.stringify(tempDetails) : '[]',
              transcription_json: isEditingTranscription ? JSON.stringify(tempTranscription) : '[]'
           })
        }).catch((err: any) => console.error('Erro no autosave', err));
     }, 3000);
     
     return () => {
        if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
     };
  }, [tempDetails, tempTranscription, isEditingResult, isEditingTranscription, auditResult?.input_hash]);

  useEffect(() => {
    if (auditResult) {
      return;
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsEditingTranscription(false);
    setTempTranscription([]);
    setIsEditingResult(false);
    setTempDetails([]);
    setTempScore(0);
    setTempMaxScore(0);
    setTempSummary('');
    setTempFeedback('');
    setAlignedDetails([]);
    setBaselineDetails([]);
    setSummaryEditedManually(false);
    setFeedbackEditedManually(false);
    setPreRegenBackup(null);
  }, [auditResult]);

  const handleEditTranscription = () => {
    if (!auditResult) {
      return;
    }

    setTempTranscription(auditResult.transcription.map((segment) => ({ ...segment })));
    setIsEditingTranscription(true);
  };

  const handleSaveTranscription = async () => {
    if (!selectedAlert || !auditResult) {
      return false;
    }

    const success = await reevaluateTranscription(
      tempTranscription,
      selectedAlert,
      auditResult,
      operatorName,
      operatorId,
      selectedSectorId
    );

    if (success) {
      setIsEditingTranscription(false);
    }

    return success;
  };

  const startEditResult = () => {
    if (!auditResult) {
      return;
    }

    const snapshot = cloneDetails(auditResult.details);
    setTempDetails(snapshot);
    setTempScore(auditResult.score);
    setTempMaxScore(auditResult.maxPossibleScore);
    setTempSummary(auditResult.summary || '');
    setTempFeedback(auditResult.ai_feedback || '');
    // Ao abrir o modo de edição, os detalhes ainda refletem o resumo atual.
    setAlignedDetails(snapshot);
    setBaselineDetails(snapshot);
    setSummaryEditedManually(false);
    setFeedbackEditedManually(false);
    setPreRegenBackup(null);
    setIsEditingResult(true);
  };

  const cancelEditResult = () => {
    setIsEditingResult(false);
    setPreRegenBackup(null);
  };

  const applyEditResult = async (): Promise<AuditResult | null> => {
    if (!auditResult) {
      return null;
    }

    let nextSummary = tempSummary;
    let nextFeedback = tempFeedback;

    if (selectedAlert && detailsDiverge(tempDetails, alignedDetails) && (!summaryEditedManually || !feedbackEditedManually)) {
      const regenerated = await regenerateSummaryText(
        auditResult.transcription,
        selectedAlert,
        cloneDetails(tempDetails),
        operatorName
      );
      if (regenerated) {
        if (!summaryEditedManually) {
          nextSummary = regenerated.summary;
          setTempSummary(regenerated.summary);
        }
        if (!feedbackEditedManually) {
          nextFeedback = regenerated.ai_feedback || '';
          setTempFeedback(regenerated.ai_feedback || '');
        }
      }
    }

    const nextResult = {
      ...auditResult,
      details: cloneDetails(tempDetails),
      score: tempScore,
      maxPossibleScore: tempMaxScore,
      summary: nextSummary,
      ai_feedback: nextFeedback,
    };

    const changedCorrections: AuditCorrectionPayload['corrections'] = [];
    for (const detail of tempDetails) {
      const previous = baselineDetails.find((item) => item.criterionId === detail.criterionId);
      if (!previous) continue;
      if (previous.status === detail.status && (previous.comment || '') === (detail.comment || '')) continue;
      changedCorrections.push({
          criterion_id: detail.criterionId,
          label: detail.label,
          previous_status: previous.status,
          previous_comment: previous.comment || '',
          corrected_status: detail.status,
          corrected_comment: detail.comment || '',
      });
    }

    if (changedCorrections.length) {
      const learningPayload: AuditCorrectionPayload = {
        setor: selectedSectorId,
        alert_label: selectedAlert?.label,
        operator_name: operatorName,
        exemplo_transcricao: auditResult.transcription?.map((segment) => segment.text).filter(Boolean).join('\n') || '',
        corrections: changedCorrections,
      };
      if (recordAuditCorrections) {
        await recordAuditCorrections(learningPayload);
      }
      setLastCorrectionLearning(learningPayload);
    }

    if (updateSavedAudit) {
      const persisted = await updateSavedAudit(nextResult);
      if (!persisted) {
        return null;
      }
    }

    setAuditResult(nextResult);
    setIsEditingResult(false);
    setAlignedDetails(cloneDetails(tempDetails));
    setBaselineDetails(cloneDetails(tempDetails));
    setSummaryEditedManually(false);
    setFeedbackEditedManually(false);
    setPreRegenBackup(null);
    return nextResult;
  };

  const generateAITexts = async () => {
    if (!auditResult || !selectedAlert) return;
    // Backup do estado atual antes de sobrescrever, para permitir desfazer.
    const backup = { summary: tempSummary, feedback: tempFeedback };
    // Snapshot dos detalhes enviados — usado depois para marcar como "alinhado".
    const detailsSentSnapshot = cloneDetails(tempDetails);
    const result = await regenerateSummaryText(
      auditResult.transcription,
      selectedAlert,
      detailsSentSnapshot,
      operatorName
    );
    if (result) {
      setPreRegenBackup(backup);
      setTempSummary(result.summary);
      setTempFeedback(result.ai_feedback || '');
      // O novo resumo reflete exatamente estes detalhes.
      setAlignedDetails(detailsSentSnapshot);
      setSummaryEditedManually(false);
      setFeedbackEditedManually(false);
    }
  };

  const undoRegeneration = () => {
    if (!preRegenBackup) return;
    setTempSummary(preRegenBackup.summary);
    setTempFeedback(preRegenBackup.feedback);
    setSummaryEditedManually(true);
    setFeedbackEditedManually(true);
    setPreRegenBackup(null);
  };

  const updateTempSummary = (value: string) => {
    setSummaryEditedManually(true);
    setTempSummary(value);
  };

  const updateTempFeedback = (value: string) => {
    setFeedbackEditedManually(true);
    setTempFeedback(value);
  };

  const updateTempDetail = (index: number, field: keyof AuditResultDetail, value: string) => {
    const nextDetails = tempDetails.map((detail, detailIndex) => {
      if (detailIndex !== index) {
        return detail;
      }

      const updatedDetail = {
        ...detail,
        [field]: field === 'status' ? normalizeDetailStatus(value) : value,
      } as AuditResultDetail;

      return {
        ...updatedDetail,
        obtainedScore: getObtainedScore(updatedDetail),
      };
    });

    const { score, maxScore } = calculateScores(nextDetails, selectedSectorId);
    setTempDetails(nextDetails);
    setTempScore(score);
    setTempMaxScore(maxScore);
  };

  const updateTranscriptionSegment = (index: number, field: keyof TranscriptionSegment, value: string) => {
    setTempTranscription((currentSegments) =>
      currentSegments.map((segment, segmentIndex) =>
        segmentIndex === index ? { ...segment, [field]: value } : segment
      )
    );
  };

  const addTranscriptionSegment = (afterIndex: number) => {
    setTempTranscription((currentSegments) => {
      const prev = currentSegments[afterIndex];
      const newSegment: TranscriptionSegment = {
        start: prev?.end || '00:00.000',
        end: prev?.end || '00:00.000',
        text: '',
      };
      const next = [...currentSegments];
      next.splice(afterIndex + 1, 0, newSegment);
      return next;
    });
  };

  const removeTranscriptionSegment = (index: number) => {
    setTempTranscription((currentSegments) => {
      if (currentSegments.length <= 1) return currentSegments;
      return currentSegments.filter((_, i) => i !== index);
    });
  };

  const forceUpdateTranscription = (newSegments: TranscriptionSegment[]) => {
    if (!auditResult) return;
    setAuditResult({ ...auditResult, transcription: newSegments });
  };

  const visibleDetails = isEditingResult
    ? tempDetails
    : auditResult?.details || [];

  // Resumo fica "desatualizado" quando o auditor mexeu em status/comentário
  // de algum critério depois da última geração do resumo.
  const isSummaryStale = isEditingResult && detailsDiverge(tempDetails, alignedDetails);
  const canUndoRegeneration = isEditingResult && preRegenBackup !== null;

  return {
    handleEditTranscription,
    handleSaveTranscription,
    startEditResult,
    cancelEditResult,
    applyEditResult,
    updateTempDetail,
    updateTranscriptionSegment,
    addTranscriptionSegment,
    removeTranscriptionSegment,
    forceUpdateTranscription,
    isEditingTranscription,
    setIsEditingTranscription,
    tempTranscription,
    isEditingResult,
    tempSummary,
    tempFeedback,
    setTempSummary: updateTempSummary,
    setTempFeedback: updateTempFeedback,
    visibleDetails,
    generateAITexts,
    isRegeneratingSummary,
    isSummaryStale,
    undoRegeneration,
    canUndoRegeneration,
    lastCorrectionLearning,
    clearLastCorrectionLearning: () => setLastCorrectionLearning(null),
  };
}

export type AuditResultEditorState = ReturnType<typeof useAuditResultEditor>;
