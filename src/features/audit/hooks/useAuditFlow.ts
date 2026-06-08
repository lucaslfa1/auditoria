import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, Dispatch, DragEvent, SetStateAction } from 'react';
import type { AuditAlert, AuditResult, AuditSector, OperatorLookupItem } from '../../../shared/types/audit';
import { apiFetchJson } from '../../../shared/lib/apiClient';

interface UseAuditFlowOptions {
  sectors: AuditSector[];
  processAudio: (
    file: File,
    selectedAlert: AuditAlert,
    operatorName?: string,
    operatorId?: string,
    sectorId?: string,
    audioDate?: string
  ) => Promise<boolean>;
  clearActionError: () => void;
  resetSavedState: () => void;
  setTranscription: Dispatch<SetStateAction<string>>;
  setAuditResult: Dispatch<SetStateAction<AuditResult | null>>;
}

const KNOWN_SECTOR_SUFFIXES = new Set([
  'BAS', 'G2L', 'LP', 'UTI', 'FENIX', 'CADASTRO', 'LOGISTICA',
  'MONDELEZ', 'UNILEVER', 'CHECKLIST', 'TABORDA', 'TRANSLOVATO', 'DIALOGO',
]);

const normalizeForComparison = (value: string) =>
  value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');

const resolveOperatorIdentifiers = (operator: OperatorLookupItem) =>
  [
    operator.matricula,
    operator.preferredId,
    operator.idHuawei,
    operator.idTelefonia,
    operator.softphoneNumber,
    operator.telefoniaAccount,
  ]
    .filter(Boolean)
    .map((value) => normalizeForComparison(String(value)));

const findExactOperator = (
  operators: OperatorLookupItem[],
  operatorName: string,
  operatorId: string,
) => {
  const normalizedName = normalizeForComparison(operatorName);
  const normalizedId = normalizeForComparison(operatorId);

  return operators.find((operator) => {
    if (operator.auditavel === false) {
      return false;
    }
    if (normalizedName && normalizeForComparison(operator.name) === normalizedName) {
      return true;
    }
    return normalizedId ? resolveOperatorIdentifiers(operator).includes(normalizedId) : false;
  }) ?? null;
};

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

const extractOperatorFromFilename = (filename: string): string | null => {
  const base = filename.replace(/\.[^/.]+$/, '');
  const cleaned = base.replace(/_(Voz|voz|VOZ)$/, '');
  const parts = cleaned.split('_');

  if (parts.length < 3) {
    return null;
  }

  let nameStart = -1;
  let nameEnd = parts.length;

  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    if (/^\d{5,}$/.test(part) || /^[A-Z]+(-[A-Z0-9]+)+$/i.test(part)) {
      continue;
    }
    if (KNOWN_SECTOR_SUFFIXES.has(part.toUpperCase())) {
      if (nameStart >= 0) {
        nameEnd = index;
      }
      break;
    }
    if (nameStart < 0) {
      nameStart = index;
    }
  }

  if (nameStart < 0 || nameEnd <= nameStart) {
    return null;
  }

  const name = parts
    .slice(nameStart, nameEnd)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');

  return name.length >= 2 ? name : null;
};

const resolveSectorAndAlert = (
  sectors: AuditSector[],
  sectorId: string,
  sectorLabel: string,
  alertId: string,
  alertLabel: string
) => {
  let sector: AuditSector | null = sectors.find((item) => item.id === sectorId) || null;
  if (!sector) {
    sector =
      sectors.find((item) => normalizeForComparison(item.label) === normalizeForComparison(sectorLabel)) || null;
  }

  let alert = sector?.alerts.find((item) => {
    const safeRequestedId = alertId.includes('::') ? alertId.split('::').pop() : alertId;
    return item.id === safeRequestedId || item.id === alertId;
  }) || null;
  if (!alert && sector) {
    alert = sector.alerts.find((item) => {
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

export function useAuditFlow({
  sectors,
  processAudio,
  clearActionError,
  resetSavedState,
  setTranscription,
  setAuditResult,
}: UseAuditFlowOptions) {
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [selectedSector, setSelectedSector] = useState<AuditSector | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<AuditAlert | null>(null);
  const [operatorName, setOperatorName] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [auditType, setAuditType] = useState<'audio' | 'pdf'>('audio');
  const [isDragging, setIsDragging] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [audioDate, setAudioDate] = useState('');

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  const clearSelectedFile = () => {
    setFile(null);
    setAudioUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }
      return null;
    });
    setInputError(null);
    clearActionError();
  };

  const selectedSectorRef = useRef(selectedSector);
  const operatorNameRef = useRef(operatorName);

  useEffect(() => {
    selectedSectorRef.current = selectedSector;
    operatorNameRef.current = operatorName;
  }, [selectedSector, operatorName]);

  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const setSelectedFile = useCallback((selectedFile: File, skipOperatorExtraction = false) => {
    setFile(selectedFile);
    setAudioUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }
      return URL.createObjectURL(selectedFile);
    });
    setInputError(null);
    clearActionError();

    if (skipOperatorExtraction || operatorNameRef.current.trim()) {
      return;
    }

    const extracted = extractOperatorFromFilename(selectedFile.name);
    if (!extracted) {
      return;
    }

    setOperatorName(extracted);

    const currentSector = selectedSectorRef.current;
    if (!currentSector?.id) {
      return;
    }

    // Cancel any previous in-flight lookup before starting a new one
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const params = new URLSearchParams({ sector_id: currentSector.id, search: extracted, limit: '5', _t: Date.now().toString() });
    apiFetchJson<OperatorLookupItem[]>(`/api/rh/operadores/lookup?${params.toString()}`, { timeoutMs: 5000, signal: controller.signal })
      .then((results) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(results) || results.length === 0) {
          return;
        }

        const normalizedExtracted = normalizeForComparison(extracted);
        const match = results.find((item) => normalizeForComparison(item.name) === normalizedExtracted);

        if (!match) {
          return;
        }

        const resolvedId = match.preferredId || match.idTelefonia || match.softphoneNumber || '';
        if (!resolvedId) {
          return;
        }

        setOperatorId(resolvedId);
        apiFetchJson('/api/rh/operadores/vincular', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nome: extracted, operator_id: resolvedId, sector_id: currentSector.id }),
        }).catch(() => { });
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
      });
  }, [clearActionError]);

  const MAX_FILE_SIZE_AUDIO = 100 * 1024 * 1024; // 100 MB
  const MAX_FILE_SIZE_PDF = 50 * 1024 * 1024;    // 50 MB

  const isValidFileForAuditType = (candidate: File) => {
    const lowerFilename = candidate.name.toLowerCase();
    if (auditType === 'pdf') {
      return candidate.type === 'application/pdf' || lowerFilename.endsWith('.pdf');
    }
    return (
      candidate.type.startsWith('audio/') ||
      ['.mp3', '.wav', '.m4a', '.ogg', '.webm'].some((extension) => lowerFilename.endsWith(extension))
    );
  };

  const isFileTooLarge = (candidate: File) => {
    const maxSize = auditType === 'pdf' ? MAX_FILE_SIZE_PDF : MAX_FILE_SIZE_AUDIO;
    return candidate.size > maxSize;
  };

  const setInvalidFileError = () => {
    setInputError(`Por favor, selecione um arquivo ${auditType === 'audio' ? 'de áudio' : 'PDF'} válido.`);
  };

  const setFileTooLargeError = (candidate: File) => {
    const maxMB = auditType === 'pdf' ? 50 : 100;
    const fileMB = (candidate.size / 1024 / 1024).toFixed(1);
    setInputError(`Arquivo muito grande (${fileMB} MB). O limite é ${maxMB} MB.`);
  };

  const handleAuditTypeChange = (nextType: 'audio' | 'pdf') => {
    if (auditType === nextType) {
      return;
    }
    setAuditType(nextType);
    setSelectedSector(null);
    setSelectedAlert(null);
    clearSelectedFile();
  };

  const handleSectorChange = (sectorId: string) => {
    const sector = sectors.find((item) => item.id === sectorId) || null;
    setSelectedSector(sector);
    setOperatorName('');
    setOperatorId('');

    if (sector?.id === 'operacao_taborda') {
      setSelectedAlert(sector.alerts.find((item) => item.id === 'logistica') || null);
      return;
    }

    setSelectedAlert(null);
  };

  const handleAlertChange = (alertId: string) => {
    setSelectedAlert(selectedSector?.alerts.find((item) => item.id === alertId) || null);
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) {
      return;
    }
    if (!isValidFileForAuditType(selectedFile)) {
      setInvalidFileError();
      event.target.value = '';
      return;
    }
    if (isFileTooLarge(selectedFile)) {
      setFileTooLargeError(selectedFile);
      event.target.value = '';
      return;
    }
    setSelectedFile(selectedFile);
  };

  const handleDragOver = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    const droppedFile = event.dataTransfer.files?.[0];
    if (!droppedFile) {
      return;
    }
    if (!isValidFileForAuditType(droppedFile)) {
      setInvalidFileError();
      return;
    }
    if (isFileTooLarge(droppedFile)) {
      setFileTooLargeError(droppedFile);
      return;
    }
    setSelectedFile(droppedFile);
  };

  const handleProcess = async () => {
    if (!file) {
      setInputError('Selecione um arquivo antes de iniciar a análise.');
      return;
    }
    if (!selectedAlert) {
      setInputError('Selecione o alerta antes de iniciar a análise.');
      return;
    }
    if (!selectedSector?.id) {
      setInputError('Selecione o setor antes de iniciar a análise.');
      return;
    }

    const trimmedOperatorName = operatorName.trim();
    const trimmedOperatorId = operatorId.trim();
    if (!trimmedOperatorName) {
      setInputError('Selecione um operador ativo do módulo Operadores.');
      return;
    }

    setInputError(null);
    clearActionError();

    const params = new URLSearchParams({
      sector_id: selectedSector.id,
      search: trimmedOperatorId || trimmedOperatorName,
      limit: '10',
      _t: Date.now().toString(),
    });

    let matchedOperator: OperatorLookupItem | null = null;
    try {
      const operators = await apiFetchJson<OperatorLookupItem[]>(
        `/api/rh/operadores/lookup?${params.toString()}`,
        { timeoutMs: 10000 },
      );
      matchedOperator = findExactOperator(
        Array.isArray(operators) ? operators : [],
        trimmedOperatorName,
        trimmedOperatorId,
      );
    } catch {
      setInputError('Não foi possível validar o operador no módulo Operadores. Tente novamente.');
      return;
    }

    if (!matchedOperator) {
      setInputError('Selecione um operador ativo do módulo Operadores para este setor.');
      return;
    }

    const resolvedOperatorName = matchedOperator.name;
    const resolvedOperatorId = matchedOperator.matricula || matchedOperator.preferredId || trimmedOperatorId;
    setOperatorName(resolvedOperatorName);
    setOperatorId(resolvedOperatorId);
    await processAudio(file, selectedAlert, resolvedOperatorName, resolvedOperatorId, selectedSector.id, audioDate);
  };

  const resetAuditFlow = () => {
    clearSelectedFile();
    setTranscription('');
    setAuditResult(null);
    setSelectedSector(null);
    setSelectedAlert(null);
    setOperatorName('');
    setOperatorId('');
    setAudioDate('');
    setAuditType('audio');
    setIsDragging(false);
    setInputError(null);
    resetSavedState();
  };

  /**
   * Pure state preparation for an audit initiated from the Classifier.
   * Sets file, sector, alert, and operator — no side effects, no API calls.
   * Orchestration (processAudio, navigation) is handled by useAuditOrchestrator.
   */
  const prepareForClassifierAudit = (
    audioFile: File,
    sectorId: string,
    sectorLabel: string,
    alertId: string,
    alertLabel: string,
    opName: string,
    opId: string
  ) => {
    const resolved = resolveSectorAndAlert(sectors, sectorId, sectorLabel, alertId, alertLabel);
    setSelectedFile(audioFile, true);
    if (resolved.sector) {
      setSelectedSector(resolved.sector);
    }
    if (resolved.alert) {
      setSelectedAlert(resolved.alert);
    }
    setOperatorName(opName);
    setOperatorId(opId);

    return resolved;
  };

  return {
    file,
    audioUrl,
    selectedSector,
    selectedAlert,
    operatorName,
    operatorId,
    audioDate,
    auditType,
    isDragging,
    inputError,
    setOperatorName,
    setOperatorId,
    setAudioDate,
    setSelectedFile,
    clearSelectedFile,
    handleAuditTypeChange,
    handleSectorChange,
    handleAlertChange,
    handleFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleProcess,
    resetAuditFlow,
    prepareForClassifierAudit,
  };
}

export type AuditFlowState = ReturnType<typeof useAuditFlow>;
