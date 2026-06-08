import { useEffect, useState } from 'react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { PageHeader } from '../../../shared/components/PageHeader';
import { Send, Loader2 } from 'lucide-react';
import { useToast } from '../../../shared/components/ToastProvider';
import { formatOperationalLabel } from '../../../shared/lib/operationalLabels';

interface PendingAudit {
  id: number;
  timestamp: string;
  operator_name: string;
  operator_id: string;
  score: number;
  max_score: number;
  alert_label: string;
  sector_id: string;
}

export function PendingDispatch() {
  const [audits, setAudits] = useState<PendingAudit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const { showToast } = useToast();

  const fetchPending = async () => {
    try {
      setIsLoading(true);
      const res = await apiFetchJson<PendingAudit[]>('/api/audit/pending-dispatch');
      setAudits(res);
    } catch {
      showToast({ variant: 'error', title: 'Erro ao carregar fila pendente.' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const handleSend = async (id: number) => {
    setSendingId(id);
    try {
      const res = await apiFetchJson<{ success: boolean; review_status: string }>(`/api/dashboard/force-send?audit_id=${id}`, {
        method: 'POST',
      });
      if (res.success || res.review_status === 'pending_approval') {
        showToast({ variant: 'success', title: 'Enviada ao supervisor com sucesso!' });
        setAudits(current => current.filter(a => a.id !== id));
      } else {
        showToast({ variant: 'error', title: 'Falha ao enviar.' });
      }
    } catch {
      showToast({ variant: 'error', title: 'Erro na operação.' });
    } finally {
      setSendingId(null);
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-6">
      <PageHeader
        eyebrow="Aguardando Envio"
        titleFirstWord="Fila"
        titleRest="de Pendentes"
        subtitle="Auditorias arquivadas aguardando envio para o supervisor."
      />

      {isLoading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="animate-spin text-primary-500" size={32} />
        </div>
      ) : audits.length === 0 ? (
        <div className="glass-panel p-12 text-center text-slate-400 rounded-2xl">
          Nenhuma auditoria pendente de envio.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {audits.map(audit => (
            <div key={audit.id} className="glass-panel p-5 rounded-2xl space-y-4 relative border border-white/5 bg-white/[0.02]">
              <div>
                <h3 className="font-semibold text-slate-200">{audit.operator_name || 'Desconhecido'}</h3>
                <p className="text-xs text-slate-400">{formatOperationalLabel(audit.sector_id)} | {audit.alert_label || 'Sem alerta'}</p>
                <div className="mt-2 text-sm">
                  Nota: <span className="font-mono text-primary-400">{audit.score}</span> / {audit.max_score}
                </div>
                <div className="text-[10px] text-slate-500 mt-1">Data: {new Date(audit.timestamp).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })}</div>
              </div>
              <button
                onClick={() => handleSend(audit.id)}
                disabled={sendingId === audit.id}
                className="w-full flex items-center justify-center gap-2 btn-primary py-2 px-4 rounded-xl text-sm font-semibold"
              >
                {sendingId === audit.id ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                {sendingId === audit.id ? 'ENVIANDO...' : 'ENVIAR AO SUPERVISOR'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
