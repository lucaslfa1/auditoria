import { useCallback, useEffect, useRef, useState } from 'react';
import { Trash2, Play, Pause, Loader2, AlertCircle, Download, Mic, AudioLines, Pencil, Check, X } from 'lucide-react';
import { useClassifier, type ClassificationResult } from '../hooks/useClassifier';
import { OperatorAutocompleteFields } from '../../../shared/components/OperatorAutocompleteFields';
import { useBodyScrollLock } from '../../../shared/hooks/useBodyScrollLock';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { RemoteTriageQueue } from './RemoteTriageQueue';

import { useAuditCriteria } from '../../../contexts/AuditCriteriaContext';

interface ClassifierProps {
    theme: 'dark' | 'light';
    auditedIndices?: Set<number>;
    onStartAudit?: (file: File, sectorId: string, sectorLabel: string, alertId: string, alertLabel: string, operatorName: string, operatorId: string, fileIndex: number) => void;
}
// Pending audit data for modal
interface PendingAuditData {
    file: File;
    fileIndex: number;
    sectorId: string;
    sectorLabel: string;
    alertId: string;
    alertLabel: string;
    suggestedOperator: string | null;
    suggestedOperatorId: string | null;
}

export function Classifier({ theme, auditedIndices, onStartAudit }: ClassifierProps) {
    const {
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
    } = useClassifier();

    // Edit mode state: index of row being edited, null = none
    const [editingIndex, setEditingIndex] = useState<number | null>(null);
    const [editSectorId, setEditSectorId] = useState('');
    const [editAlertId, setEditAlertId] = useState('');
    const [editOperatorName, setEditOperatorName] = useState('');
    const [editOperatorId, setEditOperatorId] = useState('');
    const [editSupervisor, setEditSupervisor] = useState('');
    const [editEscala, setEditEscala] = useState('');
    const [isSavingEdit, setIsSavingEdit] = useState(false);

    const { data: auditCriteriaData } = useAuditCriteria();
    const sectors = auditCriteriaData?.sectors || [];

    const sectorOptions = sectors.map(s => ({ id: s.id, label: s.label }));
    const getAlertsForSector = (sectorId: string) => {
        const sector = sectors.find(s => s.id === sectorId);
        return sector?.alerts.map(a => ({ id: a.id, label: a.label })) || [];
    };

    const handleStartEdit = (index: number) => {
        const result = results[index];
        if (!result) return;

        let initialSectorId = result.sector_id;
        let initialAlertId = result.alert_id;

        if (initialSectorId === 'erro' || initialSectorId === 'desconhecido' || !sectors.some(s => s.id === initialSectorId)) {
            initialSectorId = sectors[0]?.id || '';
        }

        const validAlerts = getAlertsForSector(initialSectorId);
        if (initialAlertId === 'erro' || initialAlertId === 'desconhecido' || !validAlerts.some(a => a.id === initialAlertId)) {
            initialAlertId = validAlerts[0]?.id || '';
        }

        setEditingIndex(index);
        setEditSectorId(initialSectorId);
        setEditAlertId(initialAlertId);
        setEditOperatorName(result.operator_rh?.name || result.operator_name || '');
        setEditOperatorId(result.operator_rh?.matricula || result.operator_id || result.matricula || '');
        setEditSupervisor(result.operator_rh?.supervisor || '');
        setEditEscala(result.operator_rh?.escala || '');
    };

    const handleCancelEdit = () => {
        setEditingIndex(null);
        setEditSectorId('');
        setEditAlertId('');
        setEditOperatorName('');
        setEditOperatorId('');
        setEditSupervisor('');
        setEditEscala('');
    };

    const handleConfirmEdit = async () => {
        if (editingIndex === null) return;
        const sector = sectors.find(s => s.id === editSectorId);
        const alert = sector?.alerts.find(a => a.id === editAlertId);
        if (!sector || !alert) return;

        setIsSavingEdit(true);
        const saved = await saveManualCorrection(editingIndex, {
            sectorId: sector.id,
            alertId: alert.id,
            operatorName: editOperatorName,
            operatorId: editOperatorId,
            supervisor: editSupervisor,
            escala: editEscala,
        });
        if (saved) {
            updateResult(editingIndex, {
                sector_id: sector.id,
                sector_label: sector.label,
                alert_id: alert.id,
                alert_label: alert.label,
                needs_review: false,
                review_reasons: [],
                review_priority: 'low',
            });
            setEditingIndex(null);
        }
        setIsSavingEdit(false);
    };

    const handleEditSectorChange = (sectorId: string) => {
        setEditSectorId(sectorId);
        const alerts = getAlertsForSector(sectorId);
        if (alerts.length > 0) {
            // Se o alerta atual existe no novo setor, mantém ele
            const stillExists = alerts.some(a => a.id === editAlertId);
            if (!stillExists) {
                setEditAlertId(alerts[0].id);
            }
        }
    };

    const fileInputRef = useRef<HTMLInputElement>(null);

    // Modal state for operator info
    const [showOperatorModal, setShowOperatorModal] = useState(false);
    const [pendingAudit, setPendingAudit] = useState<PendingAuditData | null>(null);
    const [operatorName, setOperatorName] = useState('');
    const [operatorId, setOperatorId] = useState('');
    const [modalError, setModalError] = useState<string | null>(null);

    const modalRef = useRef<HTMLDivElement | null>(null);

    // Audio playback state
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const audioUrlRef = useRef<string | null>(null);
    const [playingIndex, setPlayingIndex] = useState<number | null>(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [isDragActive, setIsDragActive] = useState(false);
    const reviewCount = results.filter((result) => result.needs_review).length;

    useBodyScrollLock(showOperatorModal);

    const formatTime = (seconds: number) => {
        if (!seconds || isNaN(seconds)) return "0:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(false);

        if (e.dataTransfer.files) {
            addFiles(e.dataTransfer.files);
        }
    }, [addFiles]);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(false);
    }, []);

    const openFilePicker = useCallback(() => {
        fileInputRef.current?.click();
    }, []);

    const handleUploadAreaKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            openFilePicker();
        }
    }, [openFilePicker]);

    const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            addFiles(e.target.files);
        }
        e.target.value = '';
    }, [addFiles]);



    const safeText = (value?: string | null) => value?.trim() || '';

    const getOperatorDisplayName = (result: ClassificationResult) =>
        safeText(result.operator_rh?.name) || safeText(result.operator_name) || 'Nao identificado';

    const getSupervisorDisplayName = (result: ClassificationResult) =>
        safeText(result.operator_rh?.supervisor) || 'Nao identificado';

    const getOperatorIdentifierLabel = (result: ClassificationResult) => {
        const idHuawei = safeText(result.id_huawei) || safeText(result.operator_rh?.idHuawei);
        const matricula = safeText(result.matricula) || safeText(result.operator_rh?.matricula);
        const preferredId = safeText(result.operator_id) || safeText(result.operator_rh?.preferredId);
        const telefoniaId = safeText(result.operator_telefonia) || safeText(result.operator_rh?.idTelefonia);

        if (idHuawei) return `ID Huawei: ${idHuawei}`;
        if (matricula) return `Matricula: ${matricula}`;
        if (preferredId) return `ID: ${preferredId}`;
        if (telefoniaId) return `Telefonia: ${telefoniaId}`;
        return 'Sem vinculo no RH';
    };

    // Normalize string for filename (remove accents, spaces, special chars)
    const normalizeForFilename = (str: string) => {
        return str
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-zA-Z0-9]/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_|_$/g, '')
            .toUpperCase();
    };

    // Generate classified filename for download
    const getClassifiedFilename = (index: number) => {
        const result = results[index];
        const file = files[index];
        if (!file || !result || result.error) return result?.filename || 'Unknown';

        const extension = file.name.split('.').pop() || 'wav';
        const sector = normalizeForFilename(result.sector_label);
        const alert = normalizeForFilename(result.alert_label);
        const originalName = file.name.replace(/\.[^/.]+$/, '');
        return `${sector}_${alert}_${originalName}.${extension}`;
    };

    // Download file with renamed name
    const handleDownload = (index: number) => {
        const result = results[index];
        const file = files[index];
        if (!file || !result) return;

        const newName = getClassifiedFilename(index);

        const url = URL.createObjectURL(file);
        const a = document.createElement('a');
        a.href = url;
        a.download = newName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const stopPlayback = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.ontimeupdate = null;
            audioRef.current.onloadedmetadata = null;
            audioRef.current.onended = null;
            audioRef.current = null;
        }
        if (audioUrlRef.current) {
            URL.revokeObjectURL(audioUrlRef.current);
            audioUrlRef.current = null;
        }
        setPlayingIndex(null);
        setCurrentTime(0);
        setDuration(0);
    }, []);

    const togglePlayback = useCallback((index: number) => {
        const file = files[index];
        if (!file) return;

        if (playingIndex === index) {
            stopPlayback();
            return;
        }

        stopPlayback();

        const url = URL.createObjectURL(file);
        const audio = new Audio(url);
        audioUrlRef.current = url;

        audio.onloadedmetadata = () => {
            if (isFinite(audio.duration)) setDuration(audio.duration);
        };

        audio.ontimeupdate = () => {
            setCurrentTime(audio.currentTime);
        };

        audio.onended = () => {
            stopPlayback();
        };

        audio.play().catch(console.error);
        audioRef.current = audio;
        setPlayingIndex(index);
    }, [files, playingIndex, stopPlayback]);

    useEffect(() => {
        return () => stopPlayback();
    }, [stopPlayback]);

    // Open modal to collect operator info before starting audit
    const handleStartAudit = (index: number) => {
        const result = results[index];
        const file = files[index];
        if (!file || !result || !onStartAudit) return;

        // Store pending audit data and open modal
        setPendingAudit({
            file,
            fileIndex: index,
            sectorId: result.sector_id,
            sectorLabel: result.sector_label,
            alertId: result.alert_id,
            alertLabel: result.alert_label,
            suggestedOperator: result.operator_rh?.name || result.operator_name || null,
            suggestedOperatorId: result.operator_id || result.operator_telefonia || null
        });
        setOperatorName(result.operator_rh?.name || result.operator_name || '');
        setOperatorId(result.operator_id || result.operator_telefonia || '');
        setModalError(null);
        setShowOperatorModal(true);
    };

    // Confirm and start audit with operator info
    const handleConfirmAudit = () => {
        if (!pendingAudit || !onStartAudit) return;
        if (!operatorId.trim()) {
            setModalError('Informe o ID do operador para continuar.');
            return;
        }

        stopPlayback();
        setModalError(null);

        onStartAudit(
            pendingAudit.file,
            pendingAudit.sectorId,
            pendingAudit.sectorLabel,
            pendingAudit.alertId,
            pendingAudit.alertLabel,
            operatorName.trim() || 'Não informado',
            operatorId.trim(),
            pendingAudit.fileIndex
        );

        setShowOperatorModal(false);
        setPendingAudit(null);
    };

    // eslint-disable-next-line react-hooks/preserve-manual-memoization
    const handleCancelModal = useCallback(() => {
        setShowOperatorModal(false);
        setPendingAudit(null);
        setOperatorName('');
        setOperatorId('');
        setModalError(null);
    }, []);



    useEffect(() => {
        if (!showOperatorModal) return;

        const modalElement = modalRef.current;
        if (!modalElement) return;

        modalElement.querySelector<HTMLInputElement>('input')?.focus();

        const handleModalKeydown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                handleCancelModal();
                return;
            }

            if (event.key !== 'Tab') return;

            const focusableElements = modalElement.querySelectorAll<HTMLElement>(
                'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
            );

            if (!focusableElements.length) return;

            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];
            const activeElement = document.activeElement as HTMLElement | null;

            if (event.shiftKey) {
                if (!activeElement || activeElement === firstElement) {
                    event.preventDefault();
                    lastElement.focus();
                }
                return;
            }

            if (activeElement === lastElement) {
                event.preventDefault();
                firstElement.focus();
            }
        };

        const handleFocusIn = (event: FocusEvent) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }

            if (!['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
                return;
            }

            window.requestAnimationFrame(() => {
                target.scrollIntoView({ block: 'center' });
            });
        };

        document.addEventListener('keydown', handleModalKeydown);
        modalElement.addEventListener('focusin', handleFocusIn);
        return () => {
            document.removeEventListener('keydown', handleModalKeydown);
            modalElement.removeEventListener('focusin', handleFocusIn);
        };
    }, [handleCancelModal, showOperatorModal]);

    const isDark = theme === 'dark';
    const mutedTextClass = isDark ? 'text-slate-400' : 'text-gray-600';
    const softTextClass = isDark ? 'text-slate-500' : 'text-gray-500';
    const tableHeadCellClass = `px-4 py-3 text-left text-xs font-medium uppercase tracking-wider sticky top-0 z-10 backdrop-blur-sm ${isDark ? 'text-slate-400 bg-slate-900/92' : 'text-gray-500 bg-white/95'}`;
    const tableHeadActionClass = `px-4 py-3 text-center text-xs font-medium uppercase tracking-wider sticky top-0 z-10 backdrop-blur-sm ${isDark ? 'text-slate-400 bg-slate-900/92' : 'text-gray-500 bg-white/95'}`;

    return (
        <div>
            <div className="space-y-6 pb-10">
                {/* Header */}
                <PageHeader
                    eyebrow="nstech | Classificação"
                    titleFirstWord="Classificação"
                    titleRest="de Arquivos"
                    subtitle="Envie os áudios para identificar setor e alerta antes de iniciar a auditoria."
                />

                {/* Instruções de uso do módulo (recolhível) */}
                <ModuleInstructions
                    storageKey="instructions:classifier"
                    steps={[
                        'Solte ou selecione os áudios na área de upload abaixo.',
                        'Confira o setor, o alerta e o operador identificados em cada ligação e ajuste se precisar.',
                        'Clique em "Enviar para auditar" para enviar a ligação à auditoria da IA.',
                    ]}
                />

                {/* Remote Triage Queue */}
                <RemoteTriageQueue />

                {/* Upload Area */}
                {!isProcessing && (
                    <div
                        onDrop={handleDrop}
                        onDragEnter={handleDragOver}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onClick={openFilePicker}
                        onKeyDown={handleUploadAreaKeyDown}
                        tabIndex={0}
                        role="button"
                        aria-label="Selecionar ou arrastar arquivos de áudio para triagem"
                        className={`
              group glass-panel hover-lift relative overflow-hidden rounded-3xl p-16 text-center cursor-pointer
              border-2 border-dashed transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-primary-500/40
              ${isDragActive
                                ? 'border-primary-400 bg-primary-500/10 scale-[1.005]'
                                : isDark
                                    ? 'border-slate-700 hover:border-primary-400/70 hover:bg-slate-900/65'
                                    : 'border-slate-300 hover:border-primary-500 bg-slate-50 theme-light:bg-slate-100/50'
                            }
            `}
                    >
                        <div className="relative flex flex-col items-center gap-5">
                            <div className="w-16 h-16 rounded-2xl bg-primary-500/10 flex items-center justify-center text-primary-500 border border-primary-500/20 group-hover:scale-110 transition-transform">
                                <AudioLines size={32} />
                            </div>
                            <div>
                                <p className="text-xl font-bold mb-2 theme-light:text-slate-800">
                                    Envie os áudios para triagem
                                </p>
                                <p className={`text-sm ${softTextClass}`}>
                                    Clique para selecionar ou arraste os arquivos ({files.length} adicionados)
                                </p>
                            </div>
                            <button
                                type="button"
                                className="btn-primary px-8 py-3 rounded-xl text-xs font-bold transition-all duration-300"
                            >
                                Selecionar áudios
                            </button>
                        </div>
                    </div>
                )}

                {/* Error Message */}
                {error && (
                    <div className="glass-panel mb-6 p-4 rounded-xl border border-red-500/25 flex items-center gap-3">
                        <AlertCircle className="w-5 h-5 text-red-400" />
                        <span className="text-red-400">{error}</span>
                    </div>
                )}

                {/* File List */}
                {files.length > results.length && (
                    <div className="glass-panel rounded-2xl overflow-hidden border border-white/10 mt-6">
                        <div className={`p-4 border-b ${isDark ? 'border-white/10' : 'border-slate-200/80'}`}>
                            <div className="flex items-center justify-between">
                                <span className="font-medium">{files.length - results.length} arquivo(s) pendentes</span>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="btn-secondary px-3 py-1.5 text-sm"
                                    >
                                        + Adicionar
                                    </button>
                                    <button
                                        onClick={reset}
                                        className="btn-danger px-3 py-1.5 text-sm"
                                    >
                                        Limpar Tudo
                                    </button>
                                </div>
                            </div>
                        </div>

                        <div className="p-4 space-y-2 max-h-64 overflow-y-auto stagger-group">
                            {files.slice(results.length).map((file, i) => {
                                const index = i + results.length;
                                return (
                                    <div key={index} className={`stagger-item flex items-center justify-between p-3 rounded-lg border transition-all duration-300 hover:-translate-y-px ${isDark ? 'bg-slate-800/50 border-white/5 hover:bg-slate-800' : 'bg-white border-slate-200 hover:bg-slate-50'}`}>
                                        <div className="flex items-center gap-3">
                                            <Play className={`w-4 h-4 ${isDark ? 'text-slate-400' : 'text-gray-500'}`} />
                                            <span className="text-sm truncate max-w-xs">{file.name}</span>
                                            <span className={`text-xs ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>
                                                {(file.size / 1024 / 1024).toFixed(2)} MB
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => removeFile(index)}
                                            className="btn-icon-danger focus:outline-none focus:ring-2 focus:ring-red-500/50"
                                            aria-label={`Remover arquivo ${file.name}`}
                                            title="Remover arquivo"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                )
                            })}
                        </div>

                        <div className={`p-4 border-t ${isDark ? 'border-white/10' : 'border-slate-200/80'}`}>
                            <button
                                onClick={classify}
                                disabled={isProcessing}
                                className="btn-primary w-full py-3 font-medium"
                            >
                                {isProcessing ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        Analisando... {progress}%
                                    </>
                                ) : (
                                    'Iniciar triagem'
                                )}
                            </button>
                        </div>
                    </div>
                )}

                {/* Processing State */}
                {isProcessing && (
                    <div className="glass-panel mt-6 rounded-2xl p-6 text-center border border-white/10">
                        <Loader2 className="w-12 h-12 animate-spin text-primary-500 mx-auto mb-4" />
                        <p className="text-lg font-medium mb-2">Analisando {files.length} arquivo(s)...</p>
                        <p className={`text-sm ${mutedTextClass}`}>
                            Transcrevendo e identificando setor e alerta.
                        </p>
                        <div className="mt-4 w-full max-w-xs mx-auto">
                            <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-slate-800/80' : 'bg-slate-200'}`}>
                                <div
                                    className="h-full bg-gradient-to-r from-primary-500 to-primary-600 transition-all duration-300"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>
                        </div>
                    </div>
                )}

                {/* Results Table */}
                {results.length > 0 && (
                    <div className="glass-panel rounded-2xl overflow-hidden border border-white/10">
                        {reviewCount > 0 && (
                            <div className={`mx-4 mt-4 rounded-xl border px-4 py-3 text-sm ${isDark ? 'border-amber-500/20 bg-amber-500/10 text-amber-300' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                                <div className="flex items-start gap-2">
                                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                                    <span>
                                        {reviewCount} arquivo(s) entraram na fila de revisão por identificação incompleta ou arquivo inválido.
                                    </span>
                                </div>
                            </div>
                        )}

                        <div className={`p-4 border-b flex items-center justify-between ${isDark ? 'border-white/10' : 'border-slate-200/80'}`}>
                            <div className="flex items-center gap-2">
                                <span className="font-medium">Triagem concluída</span>
                                <span className={`text-sm ${softTextClass}`}>
                                    ({results.length} arquivo(s))
                                </span>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={reset}
                                    className="btn-danger px-4 py-1.5 text-sm"
                                >
                                    Esvaziar resultados (Reset)
                                </button>
                            </div>
                        </div>

                        <div className="md:hidden p-4 space-y-3 stagger-group">
                            {results.map((result, index) => (
                                <div
                                    key={`mobile-${index}`}
                                    className={`stagger-item p-4 rounded-lg border transition-all duration-300 hover:-translate-y-px ${isDark ? 'bg-slate-800/50 border-white/10 hover:bg-slate-800' : 'bg-white border-slate-200 hover:bg-slate-50'} ${result.needs_review ? 'ring-2 ring-amber-500/60' : ''}`}
                                >
                                    <div className="flex items-start gap-3">
                                        <button
                                            onClick={() => togglePlayback(index)}
                                            className={`mt-0.5 p-1.5 rounded-lg transition-colors hover:bg-primary-500/20 ${playingIndex === index ? 'text-primary-400' : isDark ? 'text-slate-400' : 'text-gray-500'}`}
                                            title={playingIndex === index ? 'Pausar' : 'Reproduzir'}
                                            aria-label={`${playingIndex === index ? 'Pausar' : 'Reproduzir'} arquivo ${result.filename}`}
                                        >
                                            {playingIndex === index ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                                        </button>

                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium truncate" title={result.filename}>
                                                {result.filename}
                                            </p>
                                            {result.duplicate && (
                                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                                        {result.duplicate_label || (result.duplicate_reason === 'already_audited' ? 'Já auditado' : 'Já na triagem')}
                                                    </span>
                                                    <button
                                                        onClick={() => void forceReclassify(index)}
                                                        disabled={isProcessing}
                                                        className="text-[10px] font-bold text-primary-400 hover:text-primary-300 underline underline-offset-2 disabled:opacity-50"
                                                    >
                                                        {isProcessing ? 'Processando...' : 'Reprocessar IA'}
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {playingIndex === index && (
                                        <div className="flex items-center gap-2 mt-3">
                                            <span className={`text-[10px] font-mono ${softTextClass}`}>
                                                {formatTime(currentTime)}
                                            </span>
                                            <input
                                                type="range"
                                                min={0}
                                                max={duration || 100}
                                                value={currentTime}
                                                step={0.1}
                                                onChange={(e) => setCurrentTime(Number(e.target.value))}
                                                onMouseUp={(e) => { if (audioRef.current) audioRef.current.currentTime = Number((e.target as HTMLInputElement).value); }}
                                                onTouchEnd={(e) => { if (audioRef.current) audioRef.current.currentTime = Number((e.target as HTMLInputElement).value); }}
                                                className={`flex-1 h-1 rounded-lg appearance-none cursor-pointer ${isDark ? 'bg-slate-700 accent-primary-500' : 'bg-slate-200 accent-primary-600'}`}
                                            />
                                            <span className={`text-[10px] font-mono ${softTextClass}`}>
                                                {formatTime(duration)}
                                            </span>
                                        </div>
                                    )}

                                    {editingIndex === index ? (
                                        <div className="mt-3 space-y-2">
                                            <div>
                                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1 ${softTextClass}`}>Setor</label>
                                                <select
                                                    value={editSectorId}
                                                    onChange={(e) => handleEditSectorChange(e.target.value)}
                                                    className={`w-full text-xs rounded-lg border px-3 py-2 ${isDark ? 'bg-slate-800 border-white/15 text-slate-200' : 'bg-white border-slate-300 text-gray-800'}`}
                                                >
                                                    {sectorOptions.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1 ${softTextClass}`}>Alerta</label>
                                                <select
                                                    value={editAlertId}
                                                    onChange={(e) => setEditAlertId(e.target.value)}
                                                    className={`w-full text-xs rounded-lg border px-3 py-2 ${isDark ? 'bg-slate-800 border-white/15 text-slate-200' : 'bg-white border-slate-300 text-gray-800'}`}
                                                >
                                                    {getAlertsForSector(editSectorId).map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                                                </select>
                                            </div>
                                            <div className="pt-2">
                                                <OperatorAutocompleteFields
                                                    sectorId={editSectorId}
                                                    operatorName={editOperatorName}
                                                    operatorId={editOperatorId}
                                                    onOperatorNameChange={(value) => setEditOperatorName(value)}
                                                    onOperatorIdChange={(value) => setEditOperatorId(value)}
                                                    theme={theme}
                                                />
                                            </div>
                                            <div className="grid grid-cols-2 gap-2">
                                                <div>
                                                    <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1 ${softTextClass}`}>Supervisor</label>
                                                    <input
                                                        type="text"
                                                        value={editSupervisor}
                                                        onChange={(e) => setEditSupervisor(e.target.value)}
                                                        placeholder="Supervisor"
                                                        className={`w-full text-xs rounded-lg border px-3 py-2 ${isDark ? 'bg-slate-800 border-white/15 text-slate-200' : 'bg-white border-slate-300 text-gray-800'}`}
                                                    />
                                                </div>
                                                <div>
                                                    <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1 ${softTextClass}`}>Escala</label>
                                                    <input
                                                        type="text"
                                                        value={editEscala}
                                                        onChange={(e) => setEditEscala(e.target.value)}
                                                        placeholder="Escala"
                                                        className={`w-full text-xs rounded-lg border px-3 py-2 ${isDark ? 'bg-slate-800 border-white/15 text-slate-200' : 'bg-white border-slate-300 text-gray-800'}`}
                                                    />
                                                </div>
                                            </div>
                                            <div className="flex gap-2 mt-2">
                                                <button onClick={() => void handleConfirmEdit()} disabled={isSavingEdit} className="btn-primary flex-1 px-3 py-1.5 text-xs font-medium flex items-center justify-center gap-1 disabled:opacity-60">
                                                    {isSavingEdit ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} {isSavingEdit ? 'Salvando' : 'Salvar'}
                                                </button>
                                                <button onClick={handleCancelEdit} disabled={isSavingEdit} className="btn-ghost flex-1 px-3 py-1.5 text-xs font-medium flex items-center justify-center gap-1 disabled:opacity-60">
                                                    <X className="w-3.5 h-3.5" /> Cancelar
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="mt-3">
                                                <div className={`p-2 rounded-lg text-xs border ${isDark ? 'bg-slate-900/60 border-white/10 text-slate-300' : 'bg-white border-slate-200 text-gray-700'}`}>
                                                    <span className="block opacity-70">Setor</span>
                                                    <span className="font-medium">{result.sector_label}</span>
                                                </div>
                                            </div>

                                            <div className={`mt-2 text-xs ${mutedTextClass}`}>
                                                Alerta: <span className="font-medium">{result.alert_label}</span>
                                            </div>
                                        </>
                                    )}

                                    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                                        <div className={`rounded-lg border p-2 text-xs ${isDark ? 'bg-slate-900/60 border-white/10 text-slate-300' : 'bg-white border-slate-200 text-gray-700'}`}>
                                            <span className="block opacity-70">Operador</span>
                                            <span className="block font-medium truncate">{getOperatorDisplayName(result)}</span>
                                            <span className={`block truncate ${softTextClass}`}>{getOperatorIdentifierLabel(result)}</span>
                                        </div>
                                        <div className={`rounded-lg border p-2 text-xs ${isDark ? 'bg-slate-900/60 border-white/10 text-slate-300' : 'bg-white border-slate-200 text-gray-700'}`}>
                                            <span className="block opacity-70">Supervisor</span>
                                            <span className="block font-medium truncate">{getSupervisorDisplayName(result)}</span>
                                        </div>
                                    </div>

                                    <div className="mt-3 flex items-center gap-2">
                                        {editingIndex !== index && (
                                            <>
                                                <button
                                                    onClick={() => handleStartEdit(index)}
                                                    className="btn-ghost px-3 py-2 text-xs font-medium flex items-center gap-1"
                                                    title="Editar classificação"
                                                >
                                                    <Pencil className="w-3.5 h-3.5" /> Editar
                                                </button>
                                                <button
                                                    onClick={() => handleDownload(index)}
                                                    className="btn-ghost flex-1 px-3 py-2 text-xs font-medium"
                                                >
                                                    Baixar
                                                </button>
                                                {onStartAudit && (
                                                    auditedIndices?.has(index) ? (
                                                        <span className="inline-flex items-center gap-1 flex-1 px-3 py-2 text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg justify-center">
                                                            <Check className="w-3.5 h-3.5" /> Auditado
                                                        </span>
                                                    ) : (
                                                        <button
                                                            onClick={() => handleStartAudit(index)}
                                                            className="btn-primary flex-1 px-3 py-2 text-xs font-medium"
                                                        >
                                                            Auditar
                                                        </button>
                                                    )
                                                )}
                                            </>
                                        )}
                                        {result.error && editingIndex !== index && (
                                            <span className="inline-flex items-center gap-1 text-xs text-amber-500 font-semibold px-2">
                                                <AlertCircle className="w-3 h-3" />
                                                Falha Omitida
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="hidden md:block max-h-[560px] overflow-auto">
                            <table className="w-full">
                                <thead>
                                    <tr>
                                        <th className={tableHeadCellClass}>
                                            Arquivo
                                        </th>
                                        <th className={tableHeadCellClass}>
                                            Operador
                                        </th>
                                        <th className={tableHeadCellClass}>
                                            Supervisor
                                        </th>
                                        <th className={tableHeadCellClass}>
                                            Setor
                                        </th>
                                        <th className={tableHeadCellClass}>
                                            Alerta
                                        </th>
                                        <th className={tableHeadActionClass}>
                                            Ações
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className={`stagger-group divide-y ${isDark ? 'divide-white/10' : 'divide-slate-200'}`}>
                                    {results.map((result, index) => (
                                        <tr key={index} className={`stagger-item ${isDark ? 'hover:bg-slate-800/30 transition-colors' : 'hover:bg-slate-50 transition-colors'} ${result.needs_review ? 'shadow-[inset_0_0_0_2px_rgb(245_158_11_/_0.6)]' : ''}`}>
                                            <td className="px-4 py-4">
                                                <div className="flex flex-col gap-1">
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            onClick={() => togglePlayback(index)}
                                                            className={`p-1 rounded-lg transition-colors hover:bg-primary-500/20 ${playingIndex === index ? 'text-primary-400' : isDark ? 'text-slate-400' : 'text-gray-500'}`}
                                                            title={playingIndex === index ? 'Pausar' : 'Reproduzir'}
                                                            aria-label={`${playingIndex === index ? 'Pausar' : 'Reproduzir'} arquivo ${result.filename}`}
                                                        >
                                                            {playingIndex === index ? (
                                                                <Pause className="w-4 h-4" />
                                                            ) : (
                                                                <Play className="w-4 h-4" />
                                                            )}
                                                        </button>
                                                        <span className="text-sm font-medium truncate max-w-[240px]" title={result.filename}>
                                                            {result.filename}
                                                        </span>
                                                        {result.duplicate && (
                                                            <div className="flex items-center gap-2">
                                                                <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 whitespace-nowrap">
                                                                    {result.duplicate_label || (result.duplicate_reason === 'already_audited' ? 'Já auditado' : 'Já na triagem')}
                                                                </span>
                                                                <button
                                                                    onClick={() => void forceReclassify(index)}
                                                                    disabled={isProcessing}
                                                                    className="text-[10px] font-bold text-primary-400 hover:text-primary-300 underline underline-offset-2 disabled:opacity-50"
                                                                >
                                                                    {isProcessing ? 'Processando...' : 'Reprocessar IA'}
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                    {playingIndex === index && (
                                                        <div className="flex items-center gap-2 w-full max-w-[280px] mt-1 pl-7">
                                                            <span className={`text-[10px] font-mono ${softTextClass}`}>
                                                                {formatTime(currentTime)}
                                                            </span>
                                                            <input
                                                                type="range"
                                                                min={0}
                                                                max={duration || 100}
                                                                value={currentTime}
                                                                step={0.1}
                                                                onChange={(e) => setCurrentTime(Number(e.target.value))}
                                                                onMouseUp={(e) => { if (audioRef.current) audioRef.current.currentTime = Number((e.target as HTMLInputElement).value); }}
                                                                onTouchEnd={(e) => { if (audioRef.current) audioRef.current.currentTime = Number((e.target as HTMLInputElement).value); }}
                                                                className={`flex-1 h-1 rounded-lg appearance-none cursor-pointer ${isDark ? 'bg-slate-700 accent-primary-500' : 'bg-slate-200 accent-primary-600'
                                                                    }`}
                                                            />
                                                            <span className={`text-[10px] font-mono ${softTextClass}`}>
                                                                {formatTime(duration)}
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-4 py-4">
                                                {editingIndex === index ? (
                                                    <div className="flex flex-col gap-2">
                                                        <OperatorAutocompleteFields
                                                            sectorId={editSectorId}
                                                            operatorName={editOperatorName}
                                                            operatorId={editOperatorId}
                                                            onOperatorNameChange={(value) => setEditOperatorName(value)}
                                                            onOperatorIdChange={(value) => setEditOperatorId(value)}
                                                            theme={theme}
                                                            compact
                                                        />
                                                        <div className="grid grid-cols-1 gap-1.5">
                                                            <input
                                                                type="text"
                                                                value={editSupervisor}
                                                                onChange={(e) => setEditSupervisor(e.target.value)}
                                                                placeholder="Supervisor"
                                                                className={`text-[11px] rounded border px-2 py-1 ${isDark ? 'bg-slate-800 border-white/10 text-slate-300' : 'bg-white border-slate-300 text-gray-700'}`}
                                                            />
                                                            <input
                                                                type="text"
                                                                value={editEscala}
                                                                onChange={(e) => setEditEscala(e.target.value)}
                                                                placeholder="Escala"
                                                                className={`text-[11px] rounded border px-2 py-1 ${isDark ? 'bg-slate-800 border-white/10 text-slate-300' : 'bg-white border-slate-300 text-gray-700'}`}
                                                            />
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="flex min-w-[150px] flex-col gap-0.5">
                                                        <span className="text-sm font-medium truncate" title={getOperatorDisplayName(result)}>
                                                            {getOperatorDisplayName(result)}
                                                        </span>
                                                        <span className={`text-xs truncate ${softTextClass}`} title={getOperatorIdentifierLabel(result)}>
                                                            {getOperatorIdentifierLabel(result)}
                                                        </span>
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-4 py-4">
                                                <span className={`inline-flex max-w-[160px] truncate rounded-lg border px-2.5 py-1 text-xs font-medium ${isDark ? 'bg-slate-800 border-white/10 text-slate-300' : 'bg-white border-slate-200 text-gray-700'}`} title={getSupervisorDisplayName(result)}>
                                                    {getSupervisorDisplayName(result)}
                                                </span>
                                            </td>
                                            <td className="px-4 py-4">
                                                {editingIndex === index ? (
                                                    <select
                                                        value={editSectorId}
                                                        onChange={(e) => handleEditSectorChange(e.target.value)}
                                                        className={`text-xs rounded-lg border px-2.5 py-1.5 min-w-[140px] ${isDark ? 'bg-slate-800 border-primary-500/30 text-slate-200 ring-1 ring-primary-500/20' : 'bg-white border-primary-500/40 text-gray-800 ring-1 ring-primary-500/20'}`}
                                                    >
                                                        {sectorOptions.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                                                    </select>
                                                ) : (
                                                    <span className={`inline-flex px-2.5 py-1 rounded-lg text-xs font-medium border ${isDark ? 'bg-slate-800 border-white/10 text-slate-300' : 'bg-white border-slate-200 text-gray-700'}`}>
                                                        {result.sector_label}
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-4">
                                                {editingIndex === index ? (
                                                    <select
                                                        value={editAlertId}
                                                        onChange={(e) => setEditAlertId(e.target.value)}
                                                        className={`text-xs rounded-lg border px-2.5 py-1.5 min-w-[180px] ${isDark ? 'bg-slate-800 border-primary-500/30 text-slate-200 ring-1 ring-primary-500/20' : 'bg-white border-primary-500/40 text-gray-800 ring-1 ring-primary-500/20'}`}
                                                    >
                                                        {getAlertsForSector(editSectorId).map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                                                    </select>
                                                ) : (
                                                    <span className="text-sm">{result.alert_label}</span>
                                                )}
                                            </td>

                                            <td className="px-4 py-4">
                                                <div className="flex items-center justify-center gap-1.5">
                                                    {editingIndex === index && (
                                                        <>
                                                            <button
                                                                onClick={() => void handleConfirmEdit()}
                                                                disabled={isSavingEdit}
                                                                className="btn-primary !h-8 !w-8 !rounded-lg !p-0 disabled:opacity-60"
                                                                title="Confirmar edição"
                                                            >
                                                                {isSavingEdit ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                                                            </button>

                                                            <button
                                                                onClick={handleCancelEdit}
                                                                disabled={isSavingEdit}
                                                                className="btn-ghost !h-8 !w-8 !rounded-lg !p-0 disabled:opacity-60"
                                                                title="Cancelar edição"
                                                            >
                                                                <X className="w-4 h-4" />
                                                            </button>
                                                        </>
                                                    )}
                                                    {editingIndex !== index && (
                                                        <>
                                                            <button
                                                                onClick={() => handleStartEdit(index)}
                                                                className="btn-icon"
                                                                title="Editar classificação"
                                                                aria-label={`Editar classificação de ${result.filename}`}
                                                            >
                                                                <Pencil className="w-4 h-4" />
                                                            </button>
                                                            <button
                                                                onClick={() => handleDownload(index)}
                                                                className="btn-icon"
                                                                title="Baixar com nome classificado"
                                                                aria-label={`Baixar arquivo classificado ${result.filename}`}
                                                            >
                                                                <Download className="w-4 h-4" />
                                                            </button>
                                                            {onStartAudit && (
                                                                auditedIndices?.has(index) ? (
                                                                    <span
                                                                        className="inline-flex items-center justify-center h-9 w-9 rounded-lg text-emerald-400 bg-emerald-500/10 border border-emerald-500/20"
                                                                        title="Já auditado nesta sessão"
                                                                        aria-label={`Arquivo ${result.filename} já auditado`}
                                                                    >
                                                                        <Check className="w-4 h-4" />
                                                                    </span>
                                                                ) : (
                                                                    <button
                                                                        onClick={() => handleStartAudit(index)}
                                                                        className="btn-primary !h-9 !w-9 !rounded-lg !p-0"
                                                                        title="Ir para Auditoria"
                                                                        aria-label={`Iniciar auditoria para ${result.filename}`}
                                                                    >
                                                                        <Mic className="w-4 h-4" />
                                                                    </button>
                                                                )
                                                            )}
                                                        </>
                                                    )}
                                                    {result.error && editingIndex !== index && (
                                                        <span className="inline-flex flex-col items-center gap-1 text-[10px] text-amber-500 mx-1 font-semibold leading-tight">
                                                            <AlertCircle className="w-3 h-3" />
                                                            Falha AI
                                                        </span>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Hidden file input for adding more files */}
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="audio/*"
                    onChange={handleFileInput}
                    className="hidden"
                />
            </div>

            {/* Operator Info Modal */}
            {showOperatorModal && pendingAudit && (
                <div
                    className="safe-area-overlay fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/55 backdrop-blur-sm"
                    onClick={handleCancelModal}
                >
                    <div
                        ref={modalRef}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="operator-modal-title"
                        onClick={(event) => event.stopPropagation()}
                        className={`touch-scroll w-full max-w-md rounded-2xl p-5 shadow-sm max-h-[calc(100dvh-1.5rem)] overflow-y-auto overscroll-contain border ${isDark ? 'bg-slate-900/95 border-white/10' : 'bg-white border-slate-200'}`}
                    >
                        <div className="mb-6">
                            <h3 id="operator-modal-title" className="text-lg font-semibold">Dados do operador</h3>
                            <p className={softTextClass}>
                                Preencha os dados antes de iniciar a auditoria.
                            </p>
                        </div>

                        {pendingAudit.suggestedOperator && (
                            <div className={`mb-4 p-3 rounded-lg border ${isDark ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-emerald-50 border-emerald-200'}`}>
                                <p className={`text-sm ${isDark ? 'text-emerald-400' : 'text-emerald-700'}`}>
                                    Operador sugerido: <strong>{pendingAudit.suggestedOperator}</strong>
                                    {pendingAudit.suggestedOperatorId && (
                                        <span className="ml-2 opacity-80">
                                            (ID Huawei: <strong>{pendingAudit.suggestedOperatorId}</strong>)
                                        </span>
                                    )}
                                </p>
                            </div>
                        )}

                        <OperatorAutocompleteFields
                            sectorId={pendingAudit.sectorId}
                            operatorName={operatorName}
                            operatorId={operatorId}
                            onOperatorNameChange={(value) => {
                                setOperatorName(value);
                                if (modalError) setModalError(null);
                            }}
                            onOperatorIdChange={(value) => {
                                setOperatorId(value);
                                if (modalError) setModalError(null);
                            }}
                            theme={theme}
                            requiredId
                        />
                        {modalError && (
                            <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                                {modalError}
                            </div>
                        )}

                        <div className={`mt-4 p-3 rounded-lg border ${isDark ? 'bg-slate-800/70 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                            <p className={`text-xs ${softTextClass}`}>
                                <strong>Setor:</strong> {pendingAudit.sectorLabel} <br />
                                <strong>Alerta:</strong> {pendingAudit.alertLabel}
                            </p>
                        </div>

                        <div className="flex flex-col sm:flex-row gap-3 mt-6">
                            <button
                                onClick={handleCancelModal}
                                className="btn-ghost flex-1 py-3 font-medium"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleConfirmAudit}
                                disabled={!operatorId.trim()}
                                className="btn-primary flex-1 py-3 font-medium"
                            >
                                Iniciar Auditoria
                            </button>
                        </div>
                    </div>
                </div>
            )}


        </div>
    );
}
