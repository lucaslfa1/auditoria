/**
 * Lógica da Triagem standalone (upload manual de arquivos para classificar).
 *
 * Sustenta a tela Classifier. Envia arquivos (multipart) para
 * `POST /api/classify` (lote; `force_reclassify` reprocessa) e normaliza cada
 * `ClassificationResult` (setor/alerta/operador/confiança), sinalizando
 * duplicados e itens que precisam de revisão. `POST /api/classify/{input_hash}`
 * reclassifica/atualiza um item específico. NÃO audita — só classifica e prepara
 * o item para a fila de triagem.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { apiFetchJson } from '../../../shared/lib/apiClient';

export interface OperatorRhMatch {
    name: string;
    preferredId: string;
    preferredIdSource: string;
    supervisor: string;
    setor: string;
    escala: string;
    matricula: string;
    idHuawei: string;
    idTelefonia: string;
    softphoneNumber: string;
    telefoniaAccount: string;
    organizacaoTelefonia: string;
    tipoAgente: string;
    statusTelefonia: string;
}

export interface ClassificationResult {
    filename: string;
    input_hash?: string | null;
    sector_id: string;
    sector_label: string;
    alert_id: string;
    alert_label: string;
    confidence: number;
    operator_name?: string | null;
    operator_id?: string | null;
    operator_telefonia?: string | null;
    operator_rh?: OperatorRhMatch | null;
    id_huawei?: string | null;
    matricula?: string | null;
    error?: string | null;
    needs_review?: boolean;
    review_reasons?: string[];
    review_priority?: 'high' | 'medium' | 'low';
    duplicate?: boolean;
    duplicate_reason?: 'already_in_queue' | 'already_audited' | 'duplicate_in_batch' | null;
    duplicate_label?: string | null;
}

interface UseClassifierReturn {
    files: File[];
    results: ClassificationResult[];
    isProcessing: boolean;
    error: string | null;
    progress: number;
    addFiles: (newFiles: FileList | File[]) => void;
    removeFile: (index: number) => void;
    classify: () => Promise<void>;
    reset: () => void;
    updateResult: (index: number, updates: Partial<ClassificationResult>) => void;
    saveManualCorrection: (index: number, correction: { 
        sectorId: string; 
        alertId: string; 
        operatorName?: string; 
        operatorId?: string;
        supervisor?: string;
        escala?: string;
    }) => Promise<boolean>;
    forceReclassify: (index: number) => Promise<void>;
}

export const MAX_CLASSIFIER_FILES = 50;
const ALLOWED_TYPES = [
    'audio/wav', 'audio/x-wav', 'audio/wave',
    'audio/mpeg', 'audio/mp3', 'audio/ogg',
    'audio/webm', 'audio/m4a', 'audio/x-m4a'
];
const fileKey = (file: File) => `${file.name.toLowerCase()}-${file.size}-${file.lastModified}`;

export function useClassifier(): UseClassifierReturn {
    const [files, setFiles] = useState<File[]>([]);
    const [results, setResults] = useState<ClassificationResult[]>([]);
    const [isProcessing, setIsProcessing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [progress, setProgress] = useState(0);
    const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    const addFiles = useCallback((newFiles: FileList | File[]) => {
        const fileArray = Array.from(newFiles);

        const validFiles = fileArray.filter(file => {
            const lowerName = file.name.toLowerCase();
            const isValidType = ALLOWED_TYPES.includes(file.type) ||
                lowerName.endsWith('.mp3') ||
                lowerName.endsWith('.wav') ||
                lowerName.endsWith('.ogg') ||
                lowerName.endsWith('.m4a') ||
                lowerName.endsWith('.webm');
            return isValidType;
        });

        if (!validFiles.length) {
            setError('Selecione arquivos de áudio válidos.');
            return;
        }

        setFiles(prev => {
            const existingKeys = new Set(prev.map(fileKey));
            const uniqueNewFiles = validFiles.filter(file => !existingKeys.has(fileKey(file)));

            if (!uniqueNewFiles.length) {
                setError('Esses arquivos já foram adicionados.');
                return prev;
            }

            const nextFiles = [...prev, ...uniqueNewFiles];

            setError(null);
            return nextFiles;
        });
    }, []);

    const removeFile = useCallback((index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
        setResults(prev => prev.filter((_, i) => i !== index));
        setError(null);
    }, []);

    const classify = useCallback(async () => {
        if (files.length === 0) {
            setError('Nenhum arquivo selecionado.');
            return;
        }
        
        const pendingFiles = files.slice(results.length);
        if (pendingFiles.length === 0) {
            return;
        }

        setIsProcessing(true);
        setError(null);
        setProgress(0);

        try {
            const formData = new FormData();
            pendingFiles.forEach(file => {
                formData.append('files', file);
            });

            progressIntervalRef.current = setInterval(() => {
                setProgress(prev => Math.min(prev + 5, 90));
            }, 500);

            const data = await apiFetchJson<{ results: ClassificationResult[] }>('/api/classify', {
                method: 'POST',
                body: formData,
            });

            setResults(prev => [...prev, ...data.results]);
            setProgress(100);

        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao classificar os arquivos.');
        } finally {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
                progressIntervalRef.current = null;
            }
            setIsProcessing(false);
        }
    }, [files, results.length]);

    const updateResult = useCallback((index: number, updates: Partial<ClassificationResult>) => {
        setResults(prev => prev.map((r, i) => i === index ? { ...r, ...updates } : r));
    }, []);

    const saveManualCorrection = useCallback(async (index: number, correction: { 
        sectorId: string; 
        alertId: string; 
        operatorName?: string; 
        operatorId?: string;
        supervisor?: string;
        escala?: string;
    }) => {
        const currentResult = results[index];
        if (!currentResult?.input_hash) {
            setError('Nao foi possivel identificar o item para salvar a correcao.');
            return false;
        }

        try {
            const data = await apiFetchJson<{ result: ClassificationResult & { status?: string } }>(
                `/api/classify/${encodeURIComponent(currentResult.input_hash)}`,
                {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sector_id: correction.sectorId,
                        alert_id: correction.alertId,
                        operator_name: correction.operatorName,
                        operator_id: correction.operatorId,
                        supervisor: correction.supervisor,
                        escala: correction.escala,
                    }),
                },
            );

            setResults(prev =>
                prev.map((result, resultIndex) =>
                    resultIndex === index ? { ...result, ...data.result } : result,
                ),
            );
            setError(null);
            return true;
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao salvar a correcao manual.');
            return false;
        }
    }, [results]);

    const forceReclassify = useCallback(async (index: number) => {
        const file = files[index];
        if (!file) return;

        setIsProcessing(true);
        setError(null);
        setProgress(0);

        try {
            const formData = new FormData();
            formData.append('files', file);
            formData.append('force_reclassify', 'true');

            const data = await apiFetchJson<{ results: ClassificationResult[] }>('/api/classify', {
                method: 'POST',
                body: formData,
            });

            if (data.results && data.results.length > 0) {
                const newResult = data.results[0];
                setResults(prev => prev.map((r, i) => i === index ? newResult : r));
            }
            setProgress(100);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao reclassificar o arquivo.');
        } finally {
            setIsProcessing(false);
        }
    }, [files]);

    const reset = useCallback(() => {
        setFiles([]);
        setResults([]);
        setError(null);
        setProgress(0);
        setIsProcessing(false);
    }, []);

    return {
        files,
        results,
        isProcessing,
        error,
        progress,
        addFiles,
        removeFile,
        classify,
        reset,
        updateResult,
        saveManualCorrection,
        forceReclassify,
    };
}
