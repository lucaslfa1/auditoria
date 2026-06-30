/**
 * Fila de Triagem (Retidos) — painel embutido na tela de Classificação.
 *
 * Lista gravações baixadas pelo sync da telefonia (Huawei) que ficaram retidas
 * aguardando revisão manual antes da auditoria IA — é a entrada do volume
 * automático no fluxo triagem → classificação → auditoria → aprovação →
 * fechamento. O auditor pode triar com IA (individual ou lote), corrigir
 * manualmente (ensinando a IA), enviar para auditoria ou descartar.
 *
 * Dados (API):
 * - GET    /api/revisao/classificacao?status=pending → itens retidos
 * - POST   /api/telefonia/recordings/{hash}/classify → triagem IA (lote: máx 20, 3 simultâneos)
 * - PATCH  /api/classify/{hash}                      → correção manual; abre AIFeedbackModal
 * - POST   /api/telefonia/recordings/{hash}/audit    → agenda auditoria (202; IA em background)
 * - GET    /api/telefonia/recordings/{hash}/audit-status → polling do resultado (5s)
 * - DELETE /api/telefonia/recordings/{hash}/audit    → cancela o envio em andamento
 * - DELETE /api/telefonia/recordings/{hash}          → descarta a gravação
 * - DELETE /api/revisao/classificacao/pendentes      → limpa a fila inteira
 * - GET    /api/telefonia/recordings/{hash}/audio    → áudio autenticado (player)
 *
 * Particularidades:
 * - O polling pausa com document.hidden para não manter o banco acordado à toa
 *   (compute-hours do Neon).
 * - Bloqueios "forçáveis" (v1.3.88): o auditor confirma e envia mesmo assim;
 *   campos faltando (setor/alerta/operador) NÃO são forçáveis — exigem edição.
 */
import { useEffect, useState, useCallback, Fragment } from 'react';
import { RefreshCw, Loader2, Send, Bot, Pencil, Check, X, Trash2 } from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';
import { OperatorAutocompleteFields } from '../../../shared/components/OperatorAutocompleteFields';
import { useAuditCriteria } from '../../../contexts/AuditCriteriaContext';
import { useToast } from '../../../shared/components/ToastProvider';
import { OriginBadge } from '../../../shared/lib/auditOrigin';
import { AIFeedbackModal } from '../../ai-feedback/components/AIFeedbackModal';
import { runWithConcurrency } from '../../../shared/lib/runWithConcurrency';

/** Item da fila como vem de GET /api/revisao/classificacao (campos variam por origem). */
interface TriageQueueItem {
  id?: number | string;
  input_hash?: string;
  status?: string;
  audio_url?: string | null;
  operator_name?: string;
  operator_id?: string;
  operator_matricula?: string;
  matricula?: string;
  operador_previsto?: string;
  setor_previsto?: string;
  alerta_previsto?: string;
  criado_em?: string;
  metadata?: Record<string, any>;
  motivos_json?: string[] | string | null;
  confianca?: number;
  is_oficial?: boolean;
}

/** Resposta de GET .../audit-status — dirige o polling e os toasts de conclusão. */
interface AuditStatusResponse {
  status: 'idle' | 'processing' | 'completed' | 'audited' | 'failed' | 'stale';
  audit_id?: number;
  error_message?: string;
  saved_file_available?: boolean;
  started_at?: string;
}

// ── Helpers puros (badges, parsing de motivos e elegibilidade) ──

/** Badge extra p/ needs_manual_triage sem setor cadastrado; null quando não se aplica. */
const getManualStatusLabel = (item: TriageQueueItem): string | null => {
  const status = String(item.status || '').toLowerCase();
  if (status === 'needs_manual_triage') {
    if (item.setor_previsto === 'desconhecido' || !item.setor_previsto) return 'Setor sem cadastro';        
    return null;
  }
  return null;
};
/** true p/ os valores "vazios" históricos ('erro', 'desconhecido', 'unknown'...). */
const isUnknownAuditValue = (value?: string | null): boolean => {
  const normalized = String(value || '').trim().toLowerCase();
  return ['', 'erro', 'desconhecido', 'nao identificado', 'não identificado', 'unknown', 'none', 'null'].includes(normalized);
};

/** motivos_json pode vir como array ou string JSON — normaliza pra lista de strings. */
const parseMotivos = (raw: TriageQueueItem['motivos_json']): string[] => {
  if (Array.isArray(raw)) return raw.map((m) => String(m || '').trim()).filter(Boolean);
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.map((m) => String(m || '').trim()).filter(Boolean);
    } catch {
      // string solta, ignorar
    }
  }
  return [];
};

/** true quando TODOS os motivos de retenção são de transcrição (bloqueio forçável). */
const motivosOnlyAboutTranscription = (item: TriageQueueItem): boolean => {
  const motivos = parseMotivos(item.motivos_json);
  if (motivos.length === 0) return false;
  return motivos.every((m) => m.toLowerCase().startsWith('transcricao_'));
};

/** Campos obrigatórios ausentes (setor/alerta/operador) — não forçáveis, exigem edição. */
const getMissingFields = (item: TriageQueueItem): string[] => {
  const missing: string[] = [];
  if (isUnknownAuditValue(item.setor_previsto)) missing.push('setor');
  if (isUnknownAuditValue(item.alerta_previsto)) missing.push('alerta');
  if (isUnknownAuditValue(item.operator_name || item.operador_previsto)) missing.push('operador');
  return missing;
};

// v1.3.88: o auditor pode FORCAR o envio pra auditoria mesmo quando o pipeline
// automatico bloquearia. Retorna razao legivel quando ha bloqueio forcavel
// (auditor confirma e segue); retorna null quando nao ha bloqueio. Campos
// faltando (setor/alerta/operador) NAO sao forcaveis — exigem editar antes.
const getForceableBlockReason = (item: TriageQueueItem): string | null => {
  const status = String(item.status || '').toLowerCase();
  if (status === 'blocked_operator') {
    // Operador inexistente faz o pipeline falhar; force nao supera.
    return null;
  }
  if (status === 'needs_manual_triage' && !motivosOnlyAboutTranscription(item)) {
    return 'O pipeline marcou este item como "precisa correção manual" (classificação incompleta, direção ambígua ou similar).';
  }
  return null;
};

// Limites da triagem em lote: teto de seleção e classificações simultâneas.
const MAX_BATCH_TRIAGE = 20;
const TRIAGE_CONCURRENCY = 3;

// Elegibilidade do "Triar" (mesma regra do botao individual): item ainda nao
// classificado OU com setor/alerta vazio/invalido. Usada tambem pelo checkbox de selecao.
const isTriableItem = (item: TriageQueueItem): boolean => {
  const classificationStatus = item.metadata?.classification_status;
  const alertEmpty = !item.alerta_previsto || item.alerta_previsto === 'erro' || item.alerta_previsto === 'desconhecido';
  const sectorEmpty = !item.setor_previsto || item.setor_previsto === 'erro' || item.setor_previsto === 'desconhecido';
  return classificationStatus !== 'done' || alertEmpty || sectorEmpty;
};

export function RemoteTriageQueue() {
  const { showToast } = useToast();
  // ── Estado: fila, seleção em lote e operações em andamento (sets/refs por hash) ──
  const [items, setItems] = useState<TriageQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendingHash, setSendingHash] = useState<string | null>(null);
  const [classifyingHashes, setClassifyingHashes] = useState<Set<string>>(new Set());
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set());
  const [batchTriaging, setBatchTriaging] = useState(false);
  const [deletingHash, setDeletingHash] = useState<string | null>(null);
  const [cancelingHash, setCancelingHash] = useState<string | null>(null);
  const [processingHashes, setProcessingHashes] = useState<Set<string>>(new Set());

  // ── Estado: edição inline (setor/alerta/operador) + modal de ensino da IA ──
  const [editingHash, setEditingHash] = useState<string | null>(null);
  const [editSectorId, setEditSectorId] = useState('');
  const [editAlertId, setEditAlertId] = useState('');
  const [editOperatorName, setEditOperatorName] = useState('');
  const [editOperatorId, setEditOperatorId] = useState('');
  const [editSupervisor, setEditSupervisor] = useState('');
  const [editEscala, setEditEscala] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [learningModalData, setLearningModalData] = useState<{
    isOpen: boolean;
    tipo: string;
    setor: string;
    situacao: string;
    correcao: string;
    transcription: string;
  } | null>(null);

  const { data: auditCriteriaData } = useAuditCriteria();
  const sectors = auditCriteriaData?.sectors || [];
  const sectorOptions = sectors.map(s => ({ id: s.id, label: s.label }));
  
  const getAlertsForSector = (sectorId: string) => {
    const sector = sectors.find(s => s.id === sectorId);
    return sector?.alerts.map(a => ({ id: a.id, label: a.label })) || [];
  };

  // ── Dados: carga da fila + polling do resultado das auditorias em background ──

  /** Carrega a fila normalizando campos espalhados pelo metadata (operador, setor, áudio). */
  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetchJson<TriageQueueItem[]>('/api/revisao/classificacao?status=pending');
      const mapped = (data || []).map(it => {
        const metadata = it.metadata || {};
        const operatorMatricula =
          it.operator_matricula
          || it.matricula
          || metadata.operator_matricula
          || metadata.matricula
          || '';
        return {
          ...it,
          operator_name:
            it.operator_name
            || it.operador_previsto
            || metadata.operator_name
            || metadata.operator_name_real
            || metadata.huawei_operator_name
            || '',
          operator_matricula: operatorMatricula,
          matricula: operatorMatricula,
          operator_id:
            it.operator_id
            || metadata.operator_matricula
            || metadata.matricula
            || metadata.id_huawei
            || metadata.operator_id
            || metadata.huawei_agent_id
            || '',
          status: String(it.status || ''),
          setor_previsto:
            it.setor_previsto
            || metadata.operator_sector_id
            || '',
          audio_url: it.input_hash ? `/api/telefonia/recordings/${it.input_hash}/audio` : null,
        };
      });
      setItems(mapped);
      setSelectedHashes(new Set());
      // Re-popula o set de polling com itens que ja estavam processando antes de um refresh/reload.
      const inflight = mapped
        .filter(it => it.input_hash && it.metadata?.audit_task_status === 'processing')
        .map(it => it.input_hash as string);
      if (inflight.length > 0) {
        setProcessingHashes(prev => {
          const next = new Set(prev);
          inflight.forEach(h => next.add(h));
          return next;
        });
      }
    } catch (err) {
      console.error('Failed to load triage queue', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Polling: enquanto houver hashes em processamento, consulta /audit-status a cada 5s.
  // Quando uma task vira completed/failed/stale, retira do set e notifica o usuario.
  useEffect(() => {
    if (processingHashes.size === 0) return;

    const checkOne = async (hash: string) => {
      try {
        const res = await apiFetchJson<AuditStatusResponse>(
          `/api/telefonia/recordings/${encodeURIComponent(hash)}/audit-status`
        );
        if (res.status === 'processing' || res.status === 'idle') return;

        setProcessingHashes(prev => {
          const next = new Set(prev);
          next.delete(hash);
          return next;
        });

        if (res.status === 'completed' || res.status === 'audited') {
          showToast({
            variant: 'success',
            title: 'Auditoria concluída',
            description: res.saved_file_available ? 'Auditoria criada e enviada para Arquivos Salvos.' : 'Auditoria finalizada com sucesso.',
          });
          void fetchItems();
        } else if (res.status === 'failed') {
          showToast({
            variant: 'error',
            title: 'Erro na auditoria',
            description: res.error_message || 'A IA falhou ao processar a ligação.',
          });
          void fetchItems();
        } else if (res.status === 'stale') {
          showToast({
            variant: 'warning',
            title: 'Auditoria estagnada',
            description: 'Task pendente há mais de 10min sem progresso. Tente novamente.',
          });
        }
      } catch (err) {
        console.error('Polling /audit-status falhou para', hash, err);
      }
    };

    const interval = window.setInterval(() => {
      // Aba oculta: pausa o polling para nao manter o Neon acordado a toa
      // (compute-hours). O proximo tick com a aba visivel retoma o ciclo.
      if (document.hidden) return;
      processingHashes.forEach(hash => { void checkOne(hash); });
    }, 5000);

    return () => window.clearInterval(interval);
  }, [processingHashes, showToast, fetchItems]);

  // Classifica UM item (nunca lanca): usado tanto pelo botao individual quanto
  // pelo lote. Mantem o spinner por item via classifyingHashes.
  const classifyOne = async (hash: string): Promise<{ hash: string; ok: boolean; error?: string }> => {
    setClassifyingHashes(prev => { const next = new Set(prev); next.add(hash); return next; });
    try {
      await apiFetchJson<{ sector_id: string; alert_id: string; message: string }>(
        `/api/telefonia/recordings/${encodeURIComponent(hash)}/classify`,
        { method: 'POST' }
      );
      return { hash, ok: true };
    } catch (err: any) {
      return { hash, ok: false, error: err?.message || 'Erro ao classificar com IA.' };
    } finally {
      setClassifyingHashes(prev => { const next = new Set(prev); next.delete(hash); return next; });
    }
  };

  // ── Handlers: triagem IA, seleção/lote, exclusão, envio e edição ──

  /** Triagem IA de um único item (botão Triar/Re-triar), com toast em caso de erro. */
  const handleClassify = async (item: TriageQueueItem) => {
    if (!item.input_hash) return;
    const res = await classifyOne(item.input_hash);
    if (!res.ok) {
      showToast({ variant: 'error', title: 'Erro', description: res.error || 'Erro ao classificar com IA.' });
    }
    void fetchItems();
  };

  /** Alterna a seleção p/ lote, respeitando o teto de MAX_BATCH_TRIAGE. */
  const toggleSelected = (hash: string) => {
    setSelectedHashes(prev => {
      const next = new Set(prev);
      if (next.has(hash)) next.delete(hash);
      else if (next.size < MAX_BATCH_TRIAGE) next.add(hash);
      return next;
    });
  };

  // Triagem em lote: classifica os selecionados elegiveis, no maximo
  // TRIAGE_CONCURRENCY (3) simultaneos, com spinner por item; resumo no final.
  const handleTriarSelecionados = async () => {
    const hashes = items
      .filter(it => !!it.input_hash && selectedHashes.has(it.input_hash) && isTriableItem(it))
      .map(it => it.input_hash as string)
      .slice(0, MAX_BATCH_TRIAGE);
    if (hashes.length === 0) return;
    setBatchTriaging(true);
    try {
      const results = await runWithConcurrency(hashes, TRIAGE_CONCURRENCY, classifyOne);
      const ok = results.filter(r => r.value?.ok).length;
      const fail = hashes.length - ok;
      const firstError = results.find(r => r.value && !r.value.ok)?.value?.error;
      showToast({
        variant: fail === 0 ? 'success' : ok === 0 ? 'error' : 'warning',
        title: 'Triagem em lote concluída',
        description:
          `${ok} triado(s) com sucesso` +
          (fail > 0 ? `, ${fail} falhou(aram)${firstError ? `: ${firstError}` : ''}` : '') +
          '.',
      });
      setSelectedHashes(new Set());
      await fetchItems();
    } finally {
      setBatchTriaging(false);
    }
  };

  /** Remove e descarta a gravação da fila (DELETE), após confirmação. */
  const handleDelete = async (item: TriageQueueItem) => {
    if (!item.input_hash) return;
    if (!window.confirm('Tem certeza que deseja remover e descartar esta gravação?')) return;

    setDeletingHash(item.input_hash);
    try {
      await apiFetchJson(
        `/api/telefonia/recordings/${encodeURIComponent(item.input_hash)}`,
        { method: 'DELETE' }
      );
      fetchItems();
    } catch (err: any) {
      alert(err.message || 'Erro ao remover gravação.');
    } finally {
      setDeletingHash(null);
    }
  };

  /**
   * Envia p/ auditoria IA: campos faltando abrem o editor (não forçável);
   * bloqueio forçável pede confirm() e reenvia com force=true; o 202 do
   * backend inicia o polling do resultado.
   */
  const handleSendToAudit = async (item: TriageQueueItem, { force = false }: { force?: boolean } = {}) => {
    if (!item.input_hash) return;
    const missing = getMissingFields(item);
    if (missing.length > 0) {
      // Campos faltando nao sao forcaveis — abre editor inline pro auditor preencher.
      handleStartEdit(item);
      showToast({
        variant: 'warning',
        title: 'Falta preencher',
        description: `Preencha ${missing.join(', ')} antes de enviar.`,
      });
      return;
    }
    if (!force) {
      const forceReason = getForceableBlockReason(item);
      if (forceReason) {
        const ok = window.confirm(
          `${forceReason}\n\nDeseja FORÇAR o envio para auditoria mesmo assim?`,
        );
        if (!ok) return;
        force = true;
      }
    }
    setSendingHash(item.input_hash);
    try {
      await apiFetchJson<{ status: string; input_hash: string; started_at?: string }>(
        `/api/telefonia/recordings/${encodeURIComponent(item.input_hash)}/audit`,
        { method: 'POST', timeoutMs: 30000, body: JSON.stringify({ force }), headers: { 'Content-Type': 'application/json' } }
      );
      // Endpoint retorna 202 rapido. IA roda em background; polling pega o resultado.
      setProcessingHashes(prev => new Set(prev).add(item.input_hash!));
      showToast({
        variant: 'info',
        title: 'Auditoria iniciada',
        description: 'A IA está analisando em background. O resultado aparece sozinho em alguns minutos.',
      });
      await fetchItems();
    } catch (err: any) {
      showToast({
        variant: 'error',
        title: 'Erro ao enviar',
        description: err.message || 'Falha ao agendar auditoria.',
      });
    } finally {
      setSendingHash(null);
    }
  };

  /** Cancela a auditoria em background e devolve o item à fila para edição. */
  const handleCancelAudit = async (item: TriageQueueItem) => {
    if (!item.input_hash) return;
    if (!window.confirm('Deseja cancelar o envio para auditoria e liberar este arquivo para edição?')) return;
    setCancelingHash(item.input_hash);
    try {
      await apiFetchJson(
        `/api/telefonia/recordings/${encodeURIComponent(item.input_hash)}/audit`,
        { method: 'DELETE' }
      );
      setProcessingHashes(prev => {
        const next = new Set(prev);
        next.delete(item.input_hash!);
        return next;
      });
      showToast({ variant: 'success', title: 'Auditoria cancelada', description: 'Restaurado para a fila.' });
      await fetchItems();
    } catch (err: any) {
      showToast({ variant: 'error', title: 'Erro', description: err.message || 'Falha ao cancelar.' });
    } finally {
      setCancelingHash(null);
    }
  };

  /** Abre a edição inline normalizando setor/alerta inválidos ('erro'/'desconhecido') p/ o 1º válido. */
  const handleStartEdit = (item: TriageQueueItem) => {
    if (!item.input_hash) return;

    let initialSectorId = item.setor_previsto || '';
    let initialAlertId = item.alerta_previsto || '';

    if (initialSectorId === 'erro' || initialSectorId === 'desconhecido' || !sectors.some(s => s.id === initialSectorId)) {
        initialSectorId = sectors[0]?.id || '';
    }

    const validAlerts = getAlertsForSector(initialSectorId);
    if (initialAlertId === 'erro' || initialAlertId === 'desconhecido' || !validAlerts.some(a => a.id === initialAlertId)) {
        initialAlertId = validAlerts[0]?.id || '';
    }

    setEditingHash(item.input_hash);
    setEditSectorId(initialSectorId);
    setEditAlertId(initialAlertId);
    setEditOperatorName(item.operator_name || '');
    setEditOperatorId(item.operator_matricula || item.matricula || item.metadata?.operator_matricula || item.metadata?.matricula || item.metadata?.id_huawei || item.operator_id || '');
    setEditSupervisor(item.metadata?.operator_supervisor || '');
    setEditEscala(item.metadata?.operator_escala || '');
  };

  const handleCancelEdit = () => {
    setEditingHash(null);
  };

  /** Troca o setor em edição; mantém o alerta atual se ele existir no novo setor. */
  const handleEditSectorChange = (sectorId: string) => {
    setEditSectorId(sectorId);
    const alerts = getAlertsForSector(sectorId);
    if (alerts.length > 0) {
        const stillExists = alerts.some(a => a.id === editAlertId);
        if (!stillExists) {
            setEditAlertId(alerts[0].id);
        }
    }
  };

  /** Persiste a correção (PATCH /api/classify/{hash}) e abre o AIFeedbackModal para ensinar a IA. */
  const handleConfirmEdit = async () => {
    if (!editingHash) return;
    const sector = sectors.find(s => s.id === editSectorId);
    const alert = sector?.alerts.find(a => a.id === editAlertId);
    if (!sector || !alert) return;
    const originalItem = items.find(item => item.input_hash === editingHash);
    const originalSector = originalItem?.setor_previsto || 'não informado';
    const originalAlert = originalItem?.metadata?.alert_label || originalItem?.alerta_previsto || 'não informado';
    const originalOperator = originalItem?.operator_name || originalItem?.operador_previsto || 'não informado';
    const transcriptionContext = String(
      originalItem?.metadata?.transcription
      || originalItem?.metadata?.transcricao
      || originalItem?.metadata?.transcription_text
      || ''
    );

    setIsSavingEdit(true);
    try {
      await apiFetchJson(
          `/api/classify/${encodeURIComponent(editingHash)}`,
          {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  sector_id: sector.id,
                  alert_id: alert.id,
                  operator_name: editOperatorName,
                  operator_id: editOperatorId,
                  supervisor: editSupervisor,
                  escala: editEscala,
              }),
          },
      );
      setLearningModalData({
        isOpen: true,
        tipo: 'classificacao',
        setor: sector.id,
        situacao: `A IA/triagem indicou setor "${originalSector}", alerta "${originalAlert}" e operador "${originalOperator}".`,
        correcao: `O auditor corrigiu para setor "${sector.label}", alerta "${alert.label}" e operador "${editOperatorName || 'não informado'}".`,
        transcription: transcriptionContext,
      });
      setEditingHash(null);
      fetchItems();
    } catch (err: any) {
      window.alert(err.message || 'Erro ao salvar a correção manual.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  // ── Render: o painel some quando a fila está vazia; tabela alterna linha normal | linha em edição ──
  if (!loading && items.length === 0) {
    return null;
  }

  return (
    <div className="panel-box bg-slate-900 border border-white/10 rounded-2xl p-6 mb-6 theme-light:bg-white theme-light:border-slate-300">
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/10 theme-light:border-slate-300">
        <div>
          <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Fila de Triagem (Retidos)</h3>
          <p className="text-xs text-slate-400 theme-light:text-slate-600 mt-0.5">
            Gravações baixadas aguardando revisão manual antes da auditoria IA.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedHashes.size > 0 && (
            <button
              onClick={handleTriarSelecionados}
              disabled={batchTriaging}
              className="btn-primary flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
              title="Classifica os itens selecionados em lote (até 3 simultâneos)"
            >
              {batchTriaging ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
              Triar selecionados ({selectedHashes.size})
            </button>
          )}
          {items.length > 0 && (
            <button
              onClick={async () => {
                if (!window.confirm('Tem certeza que deseja remover TODAS as ligações que estão retidas na triagem?')) return;
                setLoading(true);
                try {
                  const res = await apiFetchJson<{ message?: string }>('/api/revisao/classificacao/pendentes', { method: 'DELETE' });
                  showToast({ variant: 'success', title: 'Sucesso', description: res.message || 'Fila de triagem limpa com sucesso.' });
                  await fetchItems();
                } catch (err: any) {
                  showToast({ variant: 'error', title: 'Erro', description: err.message || 'Falha ao limpar a fila de triagem.' });
                  setLoading(false);
                }
              }}
              disabled={loading}
              className="btn-ghost flex items-center gap-2 px-3 py-2 text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
              title="Remove todas as ligações pendentes de triagem"
            >
              <X className="w-4 h-4" />
              Limpar Tudo
            </button>
          )}
          <button
            onClick={fetchItems}
            disabled={loading}
            className="btn-ghost flex items-center gap-2 px-3 py-2 text-xs"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Atualizar
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="py-2 pr-2 w-8"></th>
              <th className="py-2 pr-3">Data e Horário</th>
              <th className="py-2 pr-3">Operador</th>
              <th className="py-2 pr-3">Matrícula</th>
              <th className="py-2 pr-3">Setor Previsto</th>
              <th className="py-2 pr-3">Alerta Previsto</th>
              <th className="py-2 pr-3">Áudio</th>
              <th className="py-2 pl-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((item, idx) => {
              const matricula = item.operator_matricula || item.matricula || item.metadata?.operator_matricula || item.metadata?.matricula || item.metadata?.id_huawei || item.operator_id || '—';
              
              let callTime = '—';
              const beginMs = item.metadata?.huawei_begin_time || item.metadata?.begin_time;
              if (beginMs) {
                const dt = new Date(Number(beginMs));
                if (!isNaN(dt.getTime())) {
                  callTime = dt.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
                }
              }
              if (callTime === '—' && item.criado_em) {
                callTime = new Date(item.criado_em).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
              }

              const isEditing = editingHash === item.input_hash;

              return (
                <Fragment key={item.input_hash || idx}>
                  {isEditing ? (
                    <tr className="bg-slate-800/50 theme-light:bg-slate-50 border border-primary-500/20 rounded-xl relative z-10 shadow-lg">
                      <td colSpan={8} className="p-4">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                          <div className="md:col-span-2">
                            <OperatorAutocompleteFields
                                operatorName={editOperatorName}
                                operatorId={editOperatorId}
                                onOperatorNameChange={setEditOperatorName}
                                onOperatorIdChange={setEditOperatorId}
                                onOperatorSelect={(op: any) => {
                                    setEditOperatorName(op.name);
                                    setEditOperatorId(op.preferredId || op.matricula || '');
                                    setEditSupervisor(op.supervisor || '');
                                    setEditEscala(op.escala || '');
                                }}
                                theme="dark"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-slate-400 theme-light:text-slate-500 mb-1.5">Setor (Ensina IA)</label>
                            <select
                                value={editSectorId}
                                onChange={e => handleEditSectorChange(e.target.value)}
                                className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary-500 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                            >
                                {sectorOptions.map(opt => (
                                    <option key={opt.id} value={opt.id}>{opt.label}</option>
                                ))}
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-slate-400 theme-light:text-slate-500 mb-1.5">Alerta (Ensina IA)</label>
                            <select
                                value={editAlertId}
                                onChange={e => setEditAlertId(e.target.value)}
                                className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary-500 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                            >
                                {getAlertsForSector(editSectorId).map(opt => (
                                    <option key={opt.id} value={opt.id}>{opt.label}</option>
                                ))}
                            </select>
                          </div>
                        </div>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={handleCancelEdit}
                            disabled={isSavingEdit}
                            className="btn-ghost px-3 py-1.5 text-xs font-semibold"
                          >
                            <X className="w-3.5 h-3.5 mr-1" />
                            Cancelar
                          </button>
                          <button
                            onClick={handleConfirmEdit}
                            disabled={isSavingEdit}
                            className="btn-primary px-3 py-1.5 text-xs font-semibold"
                          >
                            {isSavingEdit ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Check className="w-3.5 h-3.5 mr-1" />}
                            Salvar Correção e Ensinar IA
                          </button>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    <tr className="text-slate-200 theme-light:text-slate-800">
                      <td className="py-3 pr-2 w-8 align-top">
                        {isTriableItem(item) && (
                          <input
                            type="checkbox"
                            checked={!!item.input_hash && selectedHashes.has(item.input_hash)}
                            onChange={() => { if (item.input_hash) toggleSelected(item.input_hash); }}
                            disabled={batchTriaging || (!!item.input_hash && !selectedHashes.has(item.input_hash) && selectedHashes.size >= MAX_BATCH_TRIAGE)}
                            className="h-4 w-4 cursor-pointer rounded border-white/20 bg-white/5 text-primary-600 focus:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40 theme-light:border-slate-300 theme-light:bg-white"
                            title="Selecionar para triagem em lote"
                          />
                        )}
                      </td>
                      <td className="py-3 pr-3 text-slate-400">{callTime}</td>
                      <td className="py-3 pr-3">
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium">
                            {!item.operator_name || ['op mock', 'não identificado', 'nao identificado', 'desconhecido'].includes(String(item.operator_name).toLowerCase())
                              ? '—'
                              : item.operator_name}
                          </span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {item.metadata?.origem === 'huawei_sync'
                              && item.metadata?.is_manual !== true
                              && item.metadata?.is_manual !== 'true' && (
                              <OriginBadge criadoPor="automacao" size="sm" autoOnly />
                            )}
                            {item.is_oficial === false && (
                              <span className="inline-flex items-center rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-500 ring-1 ring-inset ring-amber-500/20">
                                Operador sem cadastro
                              </span>
                            )}
                            {getManualStatusLabel(item) ? (
                              <span className="inline-flex items-center rounded-md bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-400 ring-1 ring-inset ring-cyan-500/20">
                                {getManualStatusLabel(item)}
                              </span>
                            ) : null}
                            {item.alerta_previsto?.includes('Auditavel') || item.alerta_previsto?.includes('Auditável') ? (
                              <span className="inline-flex items-center rounded-md bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 ring-1 ring-inset ring-slate-500/20">
                                Não Auditável
                              </span>
                            ) : null}
                            {(Array.isArray(item.motivos_json)
                              ? item.motivos_json.includes('verificar_setor')
                              : typeof item.motivos_json === 'string' && item.motivos_json.includes('verificar_setor')) && (
                              <span className="inline-flex items-center rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-400 ring-1 ring-inset ring-blue-500/20">
                                Verificar Setor
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-slate-400">{matricula}</td>
                      <td className="py-3 pr-3">{item.setor_previsto || '—'}</td>
                      <td className="py-3 pr-3">
                        {item.alerta_previsto === 'INFORMATIVO'
                          ? 'Informativo'
                          : (item.metadata?.alert_label || item.alerta_previsto || '—')}
                      </td>
                      <td className="py-3 pr-3 min-w-[250px]">
                        {item.audio_url ? (
                          <AuthenticatedAudioPlayer audioUrl={item.audio_url} autoLoad={false} className="w-full" />
                        ) : (
                          <span className="text-xs text-slate-500">Indisponível</span>
                        )}
                      </td>
                      <td className="py-3 pl-3 text-right">
                        <div className="flex flex-col items-end gap-1.5">
                          <div className="flex items-center gap-2">
                            {(() => {
                              const showTriar = isTriableItem(item);
                              if (!showTriar) return null;
                              const isRetry = item.metadata?.classification_status === 'done';
                              return (
                                <button
                                  onClick={() => handleClassify(item)}
                                  disabled={(item.input_hash ? classifyingHashes.has(item.input_hash) : false) || sendingHash === item.input_hash}
                                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-primary-500 disabled:opacity-50"
                                  title={isRetry
                                    ? 'Retentar classificação (a tentativa anterior não identificou setor/alerta)'
                                    : 'Obter sugestão de setor e alerta usando Inteligência Artificial'}
                                >
                                  {(item.input_hash ? classifyingHashes.has(item.input_hash) : false)
                                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    : <Bot className="w-3.5 h-3.5" />}
                                  {(item.input_hash ? classifyingHashes.has(item.input_hash) : false)
                                    ? 'Triando…'
                                    : (isRetry ? 'Re-triar' : 'Triar')}
                                </button>
                              );
                            })()}
                            <button
                              onClick={() => handleStartEdit(item)}
                              disabled={sendingHash === item.input_hash || (item.input_hash ? classifyingHashes.has(item.input_hash) : false)}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs font-semibold text-white transition hover:bg-white/10 disabled:opacity-50 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-700"
                              title="Editar setor, alerta ou operador e orientar a IA"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                              Editar
                            </button>
                            {(() => {
                              const isPolling = !!item.input_hash && processingHashes.has(item.input_hash);
                              const isSending = sendingHash === item.input_hash;
                              const missingFields = getMissingFields(item);
                              const forceableReason = getForceableBlockReason(item);
                              const isBusy = isPolling || isSending || (item.input_hash ? classifyingHashes.has(item.input_hash) : false);
                              const isCanceling = cancelingHash === item.input_hash;
                              const label = isPolling
                                ? 'Em processamento…'
                                : isSending
                                  ? 'Enviando…'
                                  : missingFields.length > 0
                                    ? (missingFields.length === 1 && missingFields[0] === 'alerta' ? 'Definir alerta' : 'Preencher campos')
                                    : forceableReason
                                      ? 'Forçar envio'
                                      : 'Enviar para auditar';
                              const tooltip = isPolling
                                ? 'IA processando em background. O resultado aparece sozinho.'
                                : missingFields.length > 0
                                  ? `Preencha ${missingFields.join(', ')} antes de enviar.`
                                  : forceableReason
                                    ? 'Auditor pode forçar o envio (confirma antes).'
                                    : 'Enviar imediatamente para auditoria com a IA';
                              const buttonClass = forceableReason && missingFields.length === 0
                                ? 'inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-amber-500 disabled:opacity-50'
                                : 'inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50';
                              return (
                                <>
                                  {isPolling && (
                                    <button
                                      onClick={() => handleCancelAudit(item)}
                                      disabled={isCanceling}
                                      className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-xs font-semibold text-rose-400 transition hover:bg-rose-500/20 disabled:opacity-50 theme-light:border-rose-300 theme-light:bg-rose-50 theme-light:text-rose-600"
                                      title="Cancelar envio e liberar para edição"
                                    >
                                      {isCanceling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                                      Cancelar
                                    </button>
                                  )}
                                  <button
                                    onClick={() => handleSendToAudit(item)}
                                    disabled={isBusy}
                                    className={buttonClass}
                                    title={tooltip}
                                  >
                                    {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                                    {label}
                                  </button>
                                </>
                              );
                            })()}
                          </div>
                          <button
                            onClick={() => handleDelete(item)}
                            disabled={deletingHash === item.input_hash || sendingHash === item.input_hash}
                            className="inline-flex items-center gap-1 text-[10px] font-medium text-rose-400 hover:text-rose-300 transition"
                          >
                            {deletingHash === item.input_hash ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                            Excluir da fila
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {learningModalData && (
        <AIFeedbackModal
          isOpen={learningModalData.isOpen}
          onClose={() => setLearningModalData({ ...learningModalData, isOpen: false })}
          initialType={learningModalData.tipo}
          initialSector={learningModalData.setor}
          situacaoContext={learningModalData.situacao}
          correcaoContext={learningModalData.correcao}
          transcriptionContext={learningModalData.transcription}
        />
      )}
    </div>
  );
}
