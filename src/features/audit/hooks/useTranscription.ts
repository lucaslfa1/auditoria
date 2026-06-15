import { useRef, useState } from 'react';
import type { AuditAlert, AuditResult, AuditResultDetail, TranscriptionSegment } from '../../../shared/types/audit';
import { apiFetchBlob, apiFetchJson, ApiError } from '../../../shared/lib/apiClient';

export type ReviewQueueState = 'idle' | 'awaiting_pair' | 'pending_approval' | 'discarded';

export interface SaveToSupervisorResult {
    success: boolean;
    message: string;
    review_status: Exclude<ReviewQueueState, 'idle'>;
    audit_id?: number;
}

export interface AuditCorrectionPayload {
    setor?: string;
    alert_label?: string;
    operator_name?: string;
    exemplo_transcricao?: string;
    corrections: {
        criterion_id: string;
        label: string;
        previous_status?: string;
        previous_comment?: string;
        corrected_status: string;
        corrected_comment?: string;
    }[];
}

export const useTranscription = () => {
    const [isProcessing, setIsProcessing] = useState(false);
    const [transcription, setTranscription] = useState<string>('');
    const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [quotaExceeded, setQuotaExceeded] = useState<string | null>(null);
    const [isRegeneratingSummary, setIsRegeneratingSummary] = useState(false);

    // Stores the params needed to retry with force_override after quota is confirmed
    const pendingOverrideRef = useRef<{
        file: File;
        alert: AuditAlert;
        operatorName?: string;
        operatorId?: string;
        sectorId?: string;
        audioDate?: string;
    } | null>(null);

    const _submitAudit = async (
        file: File,
        selectedAlert: AuditAlert,
        operatorName?: string,
        operatorId?: string,
        sectorId?: string,
        audioDate?: string,
        forceOverride = false
    ) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('alert_json', JSON.stringify(selectedAlert));
        if (operatorName) formData.append('operator_name', operatorName);
        if (operatorId) formData.append('operator_id', operatorId);
        if (sectorId) formData.append('sector_id', sectorId);
        if (audioDate) formData.append('audio_date', audioDate);
        if (forceOverride) formData.append('force_override', 'true');

        return apiFetchJson<AuditResult>('/api/audit', {
            method: 'POST',
            body: formData,
        });
    };

    const processAudio = async (
        file: File,
        selectedAlert: AuditAlert,
        operatorName?: string,
        operatorId?: string,
        sectorId?: string,
        audioDate?: string
    ) => {
        setIsProcessing(true);
        setError(null);
        setActionError(null);
        setQuotaExceeded(null);
        setTranscription('');
        setAuditResult(null);
        setSaveState('idle');
        setSavedAuditId(null);
        pendingOverrideRef.current = null;

        try {
            const data = await _submitAudit(file, selectedAlert, operatorName, operatorId, sectorId, audioDate, false);
            setAuditResult(data);
            setTranscription('Processamento realizado remotamente pelo serviço de auditoria.\nVeja os detalhes ao lado.');
            return true;

        } catch (err: unknown) {
            console.error('Erro no processamento:', err);
            if (err instanceof ApiError && err.status === 429) {
                // Quota exceeded — store params for optional override
                pendingOverrideRef.current = { file, alert: selectedAlert, operatorName, operatorId, sectorId, audioDate };
                setQuotaExceeded(err.message);
            } else if (err instanceof ApiError) {
                setError(err.message);
            } else {
                setError(err instanceof Error ? err.message : 'Falha ao processar áudio.');
            }
            return false;
        } finally {
            setIsProcessing(false);
        }
    };

    const forceProcessAudio = async () => {
        const pending = pendingOverrideRef.current;
        if (!pending) return false;

        setIsProcessing(true);
        setError(null);
        setActionError(null);
        setQuotaExceeded(null);
        setTranscription('');
        setAuditResult(null);
        setSaveState('idle');
        setSavedAuditId(null);
        pendingOverrideRef.current = null;

        try {
            const data = await _submitAudit(
                pending.file, pending.alert,
                pending.operatorName, pending.operatorId, pending.sectorId, pending.audioDate,
                true
            );
            setAuditResult(data);
            setTranscription('Processamento realizado remotamente pelo serviço de auditoria.\nVeja os detalhes ao lado.');
            return true;
        } catch (err: unknown) {
            console.error('Erro no override:', err);
            setError(err instanceof ApiError ? err.message : 'Falha ao processar áudio.');
            return false;
        } finally {
            setIsProcessing(false);
        }
    };

    const triggerDownload = (blob: Blob, filename: string) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    };

    const downloadExcel = async (result: AuditResult) => {
        try {
            setActionError(null);
            const blob = await apiFetchBlob('/api/export/excel', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `auditoria_${new Date().toISOString().slice(0, 10)}.xlsx`);

        } catch (err) {
            console.error('Erro no download:', err);
            setActionError('Não foi possível baixar o Excel.');
        }
    };

    const downloadReportDocx = async (result: AuditResult) => {
        try {
            setActionError(null);
            const blob = await apiFetchBlob('/api/export/report/docx', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `auditoria_${new Date().toISOString().slice(0, 10)}.docx`);
        } catch (err) {
            console.error('Erro no download DOCX:', err);
            setActionError('Não foi possível baixar o DOCX.');
        }
    };

    const downloadReportPdf = async (result: AuditResult) => {
        try {
            setActionError(null);
            const blob = await apiFetchBlob('/api/export/report/pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `auditoria_${new Date().toISOString().slice(0, 10)}.pdf`);
        } catch (err) {
            console.error('Erro no download PDF:', err);
            setActionError('Não foi possível baixar o PDF.');
        }
    };

    const downloadTranscriptionDocx = async (result: AuditResult) => {
        try {
            setActionError(null);
            const blob = await apiFetchBlob('/api/export/transcription/docx', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `transcricao_${new Date().toISOString().slice(0, 10)}.docx`);
        } catch (err) {
            console.error('Erro no download DOCX:', err);
            setActionError('Não foi possível baixar o DOCX.');
        }
    };

    const downloadTranscriptionPdf = async (result: AuditResult) => {
        try {
            setActionError(null);
            const blob = await apiFetchBlob('/api/export/transcription/pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `transcricao_${new Date().toISOString().slice(0, 10)}.pdf`);
        } catch (err) {
            console.error('Erro no download PDF:', err);
            setActionError('Não foi possível baixar o PDF.');
        }
    };

    const downloadGestores = async (
        result: AuditResult,
        alertId?: string,
        alertLabel?: string,
        sectorId?: string
    ) => {
        try {
            setActionError(null);
            const params = new URLSearchParams();
            if (alertId) params.append('alert_id', alertId);
            if (alertLabel) params.append('alert_label', alertLabel);
            if (sectorId) params.append('sector_id', sectorId);
            const qs = params.toString() ? `?${params.toString()}` : '';
            const blob = await apiFetchBlob(`/api/export/gestores${qs}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `consulta_gestores_${new Date().toISOString().slice(0, 10)}.xlsx`);
        } catch (err) {
            console.error('Erro no download Gestores:', err);
            setActionError('Não foi possível exportar no formato Gestores.');
        }
    };

    const downloadGestoresPdf = async (
        result: AuditResult,
        alertId?: string,
        alertLabel?: string,
        sectorId?: string
    ) => {
        try {
            setActionError(null);
            const params = new URLSearchParams();
            if (alertId) params.append('alert_id', alertId);
            if (alertLabel) params.append('alert_label', alertLabel);
            if (sectorId) params.append('sector_id', sectorId);
            const qs = params.toString() ? `?${params.toString()}` : '';
            const blob = await apiFetchBlob(`/api/export/gestores/pdf${qs}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result),
            });
            triggerDownload(blob, `relatorio_gestores_${new Date().toISOString().slice(0, 10)}.pdf`);
        } catch (err) {
            console.error('Erro no download Gestores PDF:', err);
            setActionError('Não foi possível exportar o PDF Gestores.');
        }
    };

    const [saveState, setSaveState] = useState<ReviewQueueState>('idle');
    const [savedAuditId, setSavedAuditId] = useState<number | null>(null);

    const saveToDashboard = async (
        result: AuditResult,
        alertId?: string,
        alertLabel?: string,
        operatorId?: string,
        sectorId?: string,
        audioDate?: string
    ): Promise<SaveToSupervisorResult | null> => {
        try {
            setActionError(null);
            const params = new URLSearchParams();
            if (alertId) params.append('alert_id', alertId);
            if (alertLabel) params.append('alert_label', alertLabel);
            if (operatorId) params.append('operator_id', operatorId);
            if (sectorId) params.append('sector_id', sectorId);
            if (audioDate) params.append('audio_date', audioDate);

            const response = await apiFetchJson<SaveToSupervisorResult>(`/api/dashboard/save?${params.toString()}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result),
            });

            setSaveState(response.review_status);
            if (response.audit_id) {
                setSavedAuditId(response.audit_id);
            }
            return response;
        } catch (err) {
            console.error('Erro ao salvar no dashboard:', err);
            setActionError('Não foi possível salvar no dashboard.');
            return null;
        }
    };

    const forceSendToSupervisor = async (force: boolean = false): Promise<boolean> => {
        if (!savedAuditId) {
            setActionError('Auditoria salva sem identificador. Salve novamente para liberar ao supervisor.');
            return false;
        }
        try {
            setActionError(null);
            const url = `/api/dashboard/force-send?audit_id=${savedAuditId}${force ? '&force=true' : ''}`;
            const response = await apiFetchJson<SaveToSupervisorResult>(url, {
                method: 'POST',
            });
            setSaveState(response.review_status);
            if (response.review_status !== 'pending_approval') {
                setActionError(response.message || 'Auditoria permanece arquivada.');
                return false;
            }
            return response.success;
        } catch (err: any) {
            if (err.status === 429) {
                if (window.confirm(err.message || 'Limite de 2 auditorias atingido. Deseja enviar mesmo assim?')) {
                    return forceSendToSupervisor(true);
                }
            }
            console.error('Erro ao forçar envio:', err);
            setActionError(err.message || 'Não foi possível forçar o envio.');
            return false;
        }
    };

    const updateSavedAudit = async (result: AuditResult): Promise<boolean> => {
        if (!savedAuditId) return true;
        try {
            setActionError(null);
            await apiFetchJson(`/api/dashboard/audits/${savedAuditId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result),
            });
            return true;
        } catch (err) {
            console.error('Erro ao atualizar auditoria salva:', err);
            setActionError('As correções foram aplicadas na tela, mas não foi possível atualizar a auditoria salva.');
            return false;
        }
    };

    const discardSavedAudit = async (): Promise<boolean> => {
        if (!savedAuditId) {
            setActionError('Auditoria salva sem identificador. Salve novamente antes de descartar.');
            return false;
        }
        try {
            setActionError(null);
            await apiFetchJson(`/api/audit/${savedAuditId}/discard`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'Descartada pela auditoria antes do envio ao supervisor.' }),
            });
            setSaveState('idle');
            setSavedAuditId(null);
            return true;
        } catch (err) {
            console.error('Erro ao descartar auditoria arquivada:', err);
            setActionError('Não foi possível descartar a auditoria arquivada.');
            return false;
        }
    };

    const recordAuditCorrections = async (payload: AuditCorrectionPayload): Promise<boolean> => {
        if (!payload.corrections.length) return true;
        try {
            setActionError(null);
            await apiFetchJson('/api/ai-feedback/audit-corrections', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            return true;
        } catch (err) {
            console.error('Erro ao registrar correções para IA:', err);
            setActionError('As correções foram aplicadas, mas não foi possível registrar a referência da IA.');
            return false;
        }
    };

    const resetSavedState = () => {
        setSaveState('idle');
        setSavedAuditId(null);
    };

    const clearActionError = () => {
        setActionError(null);
    };

    const reevaluateTranscription = async (
        editedTranscription: { start: string; end: string; text: string }[],
        selectedAlert: AuditAlert,
        currentResult?: AuditResult | null,
        operatorName?: string,
        operatorId?: string,
        sectorId?: string
    ) => {
        setIsProcessing(true);
        setError(null);
        setActionError(null);
        // Nao limpar auditResult aqui; manter resultado anterior visivel durante o loading

        try {
            const inputHash = currentResult?.input_hash?.trim() || undefined;
            const data = await apiFetchJson<AuditResult>('/api/audit/reevaluate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    transcription: editedTranscription,
                    alert: selectedAlert,
                    operator_name: operatorName,
                    operator_id: operatorId,
                    sector_id: sectorId,
                    input_hash: inputHash,
                    source_type: currentResult?.source_type ?? 'audio',
                    audio_quality: currentResult?.audio_quality ?? null
                }),
            });

            // Validar resposta mínima antes de setar — evita tela em branco
            if (!data || typeof data.score !== 'number' || !Array.isArray(data.details)) {
                setActionError('Resposta inválida da IA. Resultado anterior mantido.');
                return false;
            }

            const nextResult: AuditResult = {
                ...data,
                input_hash: data.input_hash || inputHash,
            };

            if (savedAuditId) {
                await apiFetchJson(`/api/dashboard/audits/${savedAuditId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(nextResult),
                });
            } else {
                setSaveState('idle'); // Reset para permitir arquivar a auditoria reavaliada
            }
            setAuditResult(nextResult);
            return true;
        } catch (err: unknown) {
            console.error('Erro na re-auditoria:', err);
            if (err instanceof ApiError) {
                setActionError(err.message);
            } else {
                setActionError('Falha ao re-avaliar transcrição. Resultado anterior mantido.');
            }
            // auditResult permanece inalterado — resultado anterior continua visível
            return false;
        } finally {
            setIsProcessing(false);
        }
    };

    const regenerateSummaryText = async (
        transcription: TranscriptionSegment[],
        alert: AuditAlert,
        details: AuditResultDetail[],
        operatorName?: string
    ) => {
        setIsRegeneratingSummary(true);
        setActionError(null);
        try {
            const data = await apiFetchJson<{ summary: string; ai_feedback: string }>('/api/audit/regenerate-summary', {
                method: 'POST',
                timeoutMs: 90000,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    transcription,
                    alert,
                    details,
                    operator_name: operatorName,
                }),
            });
            return data;
        } catch (err: any) {
            console.error('Re-generate summary api fetch error:', err);
            setActionError(err.message || 'Erro ao gerar novo resumo da auditoria.');
            return null;
        } finally {
            setIsRegeneratingSummary(false);
        }
    };

    return {
        processAudio,
        forceProcessAudio,
        reevaluateTranscription,
        downloadExcel,
        downloadReportDocx,
        downloadReportPdf,
        downloadTranscriptionDocx,
        downloadTranscriptionPdf,
        downloadGestores,
        downloadGestoresPdf,
        saveToDashboard,
        isProcessing,
        transcription,
        auditResult,
        error,
        quotaExceeded,
        actionError,
        isRegeneratingSummary,
        regenerateSummaryText,
        isSaved: saveState !== 'idle',
        saveState,
        setSaveState,
        setTranscription,
        setAuditResult,
        resetSavedState,
        clearActionError,
        savedAuditId,
        forceSendToSupervisor,
        discardSavedAudit,
        updateSavedAudit,
        recordAuditCorrections
    };
};
