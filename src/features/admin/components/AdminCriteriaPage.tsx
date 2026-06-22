/**
 * Tela de admin do CATÁLOGO de auditoria: setores → alertas → critérios
 * (Inteligência Artificial > Critérios). É a fonte de verdade que a IA usa
 * para auditar.
 *
 * CRUD via `/api/admin/sectors`, `/api/admin/alerts`, `/api/admin/criteria`
 * (GET lista; POST cria; PUT `/{id}` edita; DELETE `/{id}` remove). Histórico em
 * `/api/admin/criteria/audit-log`. O que muda aqui passa a valer nas PRÓXIMAS
 * auditorias (o backend resolve o alerta contra este catálogo).
 */
import { useEffect, useState, useCallback } from 'react';
import { Loader2, Plus, Pencil, Trash2, ChevronDown, ChevronRight, History, X } from 'lucide-react';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

interface Criterion {
    id?: number;
    alert_id?: number | string;
    chave: string;
    label: string;
    weight: number;
    description: string;
    type: string;
    deflator: number;
    referencia?: string;
    exemplo?: string;
}

interface Alert {
    id: string;
    label: string;
    context: string;
    original_id?: string;
    pop_ref?: string;
    expected_direction?: string;
    criterios: Criterion[];
}

interface Sector {
    id: string;
    label: string;
    description: string;
    alertas: Alert[];
}

interface SectorForm { id: string; label: string; description: string; motivo: string; }
interface AlertForm { original_id: string; label: string; context: string; sector_id: string; pop_ref: string; expected_direction: string; motivo: string; }
interface CriterionForm { alert_id: string; chave: string; label: string; weight: number; description: string; type: string; deflator: number; referencia: string; exemplo: string; motivo: string; }

type EntityType = 'sector' | 'alert' | 'criterion';

interface AuditLogEntry {
    id: number;
    acao: 'create' | 'update' | 'delete';
    entity_id: string;
    payload_antes: Record<string, any> | null;
    payload_depois: Record<string, any> | null;
    alterado_por: string;
    alterado_em: string;
    motivo: string | null;
    origem: string;
}

interface EntityTarget { type: EntityType; id: string | number; label: string; }

const ENTITY_LABEL: Record<EntityType, string> = {
    sector: 'setor',
    alert: 'alerta',
    criterion: 'critério',
};

const formatTimestamp = (iso: string): string => {
    try {
        return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
    } catch {
        return iso;
    }
};

export function AdminCriteriaPage() {
    const { showToast } = useToast();
    const [sectors, setSectors] = useState<Sector[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [expandedSectors, setExpandedSectors] = useState<Set<string>>(new Set());
    const [expandedAlerts, setExpandedAlerts] = useState<Set<string>>(new Set());

    const [sectorFormOpen, setSectorFormOpen] = useState(false);
    const [sectorForm, setSectorForm] = useState<SectorForm>({ id: '', label: '', description: '', motivo: '' });
    const [editingSectorId, setEditingSectorId] = useState<string | null>(null);

    const [alertFormOpen, setAlertFormOpen] = useState(false);
    const [alertForm, setAlertForm] = useState<AlertForm>({ original_id: '', label: '', context: '', sector_id: '', pop_ref: '', expected_direction: '', motivo: '' });
    const [editingAlertId, setEditingAlertId] = useState<string | null>(null);

    const [criterionFormOpen, setCriterionFormOpen] = useState(false);
    const [criterionForm, setCriterionForm] = useState<CriterionForm>({ alert_id: '', chave: '', label: '', weight: 0, description: '', type: 'boolean', deflator: 0, referencia: '', exemplo: '', motivo: '' });
    const [editingCriterionId, setEditingCriterionId] = useState<number | null>(null);

    const [submitting, setSubmitting] = useState(false);

    const [deleteTarget, setDeleteTarget] = useState<EntityTarget | null>(null);
    const [deleteMotivo, setDeleteMotivo] = useState('');

    const [historyTarget, setHistoryTarget] = useState<EntityTarget | null>(null);
    const [historyEntries, setHistoryEntries] = useState<AuditLogEntry[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyExpandedId, setHistoryExpandedId] = useState<number | null>(null);

    const toggleSector = (id: string) => {
        setExpandedSectors(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleAlert = (id: string) => {
        setExpandedAlerts(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const fetchData = async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            setError(null);

            const [sectorsData, alertsData, criteriaData] = await Promise.all([
                apiFetchJson<any[]>('/api/admin/sectors'),
                apiFetchJson<any[]>('/api/admin/alerts'),
                apiFetchJson<any[]>('/api/admin/criteria'),
            ]);

            const sectorsMap = new Map<string, Sector>();
            for (const s of sectorsData) {
                sectorsMap.set(s.id, { id: s.id, label: s.label, description: s.description || '', alertas: [] });
            }

            const alertsMap = new Map<string, Alert>();
            for (const a of alertsData) {
                const alertObj: Alert = {
                    id: a.id,
                    original_id: a.original_id,
                    label: a.label,
                    context: a.context || '',
                    pop_ref: a.pop_ref || '',
                    criterios: [],
                };
                alertsMap.set(a.id, alertObj);
                const sector = sectorsMap.get(a.sector_id);
                if (sector) sector.alertas.push(alertObj);
            }

            for (const c of criteriaData) {
                const critObj: Criterion = { id: c.id, alert_id: c.alert_id, chave: c.chave, label: c.label, weight: c.weight, description: c.description || '', type: c.type || 'boolean', deflator: c.deflator };
                const alert = alertsMap.get(c.alert_id);
                if (alert) alert.criterios.push(critObj);
            }

            setSectors(Array.from(sectorsMap.values()));
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar dados');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    // --- Helpers ---
    const ensureMotivo = (motivo: string): string | null => {
        const trimmed = motivo.trim();
        if (!trimmed) {
            showToast({ variant: 'error', title: 'Motivo obrigatório', description: 'Descreva por que essa alteração está sendo feita.' });
            return null;
        }
        return trimmed;
    };

    // --- Sector Logic ---
    const handleSaveSector = async () => {
        if (!sectorForm.label.trim() || (!editingSectorId && !sectorForm.id.trim())) return;
        const motivo = ensureMotivo(sectorForm.motivo);
        if (motivo == null) return;
        try {
            setSubmitting(true);
            if (editingSectorId) {
                await apiFetchJson(`/api/admin/sectors/${encodeURIComponent(editingSectorId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: sectorForm.label, description: sectorForm.description, motivo })
                });
            } else {
                await apiFetchJson(`/api/admin/sectors`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: sectorForm.id, label: sectorForm.label, description: sectorForm.description, motivo })
                });
            }
            setSectorFormOpen(false);
            await fetchData(true);
        } catch (err: any) { showToast({ variant: 'error', title: 'Erro', description: err.message }); }
        finally { setSubmitting(false); }
    };

    // --- Alert Logic ---
    const handleSaveAlert = async () => {
        if (!alertForm.label.trim() || (!editingAlertId && !alertForm.sector_id.trim())) return;
        const motivo = ensureMotivo(alertForm.motivo);
        if (motivo == null) return;
        try {
            setSubmitting(true);
            if (editingAlertId) {
                await apiFetchJson(`/api/admin/alerts/${encodeURIComponent(editingAlertId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: alertForm.label, context: alertForm.context, pop_ref: alertForm.pop_ref || null, expected_direction: alertForm.expected_direction || null, motivo })
                });
            } else {
                await apiFetchJson(`/api/admin/alerts`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sector_id: alertForm.sector_id, label: alertForm.label, context: alertForm.context, original_id: alertForm.original_id, pop_ref: alertForm.pop_ref || null, expected_direction: alertForm.expected_direction || null, motivo })
                });
            }
            setAlertFormOpen(false);
            await fetchData(true);
        } catch (err: any) { showToast({ variant: 'error', title: 'Erro', description: err.message }); }
        finally { setSubmitting(false); }
    };

    // --- Criterion Logic ---
    const handleSaveCriterion = async () => {
        if (!criterionForm.label.trim() || !criterionForm.chave.trim()) return;
        const motivo = ensureMotivo(criterionForm.motivo);
        if (motivo == null) return;
        try {
            setSubmitting(true);
            if (editingCriterionId) {
                await apiFetchJson(`/api/admin/criteria/${editingCriterionId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chave: criterionForm.chave,
                        label: criterionForm.label,
                        weight: criterionForm.weight,
                        description: criterionForm.description,
                        type: criterionForm.type,
                        deflator: criterionForm.deflator,
                        motivo,
                    })
                });
            } else {
                await apiFetchJson(`/api/admin/criteria`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        alert_id: criterionForm.alert_id,
                        chave: criterionForm.chave,
                        label: criterionForm.label,
                        weight: criterionForm.weight,
                        description: criterionForm.description,
                        type: criterionForm.type,
                        deflator: criterionForm.deflator,
                        motivo,
                    })
                });
            }
            setCriterionFormOpen(false);
            await fetchData(true);
        } catch (err: any) { showToast({ variant: 'error', title: 'Erro', description: err.message }); }
        finally { setSubmitting(false); }
    };

    // --- Delete Logic (shared via deleteTarget) ---
    const openDelete = (type: EntityType, id: string | number, label: string) => {
        setDeleteTarget({ type, id, label });
        setDeleteMotivo('');
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        const motivo = ensureMotivo(deleteMotivo);
        if (motivo == null) return;
        try {
            setSubmitting(true);
            const qs = `?motivo=${encodeURIComponent(motivo)}`;
            if (deleteTarget.type === 'sector') {
                await apiFetchJson(`/api/admin/sectors/${encodeURIComponent(String(deleteTarget.id))}${qs}`, { method: 'DELETE' });
            } else if (deleteTarget.type === 'alert') {
                await apiFetchJson(`/api/admin/alerts/${encodeURIComponent(String(deleteTarget.id))}${qs}`, { method: 'DELETE' });
            } else {
                await apiFetchJson(`/api/admin/criteria/${deleteTarget.id}${qs}`, { method: 'DELETE' });
            }
            setDeleteTarget(null);
            await fetchData(true);
        } catch (err: any) { showToast({ variant: 'error', title: 'Erro', description: err.message }); }
        finally { setSubmitting(false); }
    };

    // --- History Drawer ---
    const openHistory = (type: EntityType, id: string | number, label: string) => {
        setHistoryTarget({ type, id, label });
        setHistoryExpandedId(null);
    };

    const closeHistory = () => {
        setHistoryTarget(null);
        setHistoryEntries([]);
        setHistoryExpandedId(null);
    };

    const loadHistory = useCallback(async (target: EntityTarget) => {
        try {
            setHistoryLoading(true);
            const url = `/api/admin/criteria/audit-log?entity_type=${target.type}&entity_id=${encodeURIComponent(String(target.id))}&limit=50`;
            const data = await apiFetchJson<AuditLogEntry[]>(url);
            setHistoryEntries(Array.isArray(data) ? data : []);
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao carregar histórico', description: err.message });
            setHistoryEntries([]);
        } finally {
            setHistoryLoading(false);
        }
    }, [showToast]);

    useEffect(() => {
        if (historyTarget) {
            loadHistory(historyTarget);
        }
    }, [historyTarget, loadHistory]);

    if (loading) {
        return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-primary-500 w-8 h-8" /></div>
    }

    return (
        <div className="space-y-6 pb-10">
            <PageHeader
                eyebrow="nstech | Critérios"
                titleFirstWord="Critérios"
                titleRest="de Auditoria"
                subtitle="Gerencie o catálogo de setores, alertas e critérios da auditoria. Toda alteração exige motivo e fica registrada no histórico."
            />

            <ModuleInstructions
                storageKey="instructions:criteria"
                steps={[
                    'Gerencie setores, alertas e critérios da auditoria.',
                    'Ajuste pesos, perguntas e regras de cada critério.',
                    'Toda alteração exige um motivo e fica registrada no histórico.',
                ]}
            />
            {error && <div className="text-red-400 p-4 rounded bg-red-500/10 border border-red-500/20">{error}</div>}

            <div className="flex justify-start mb-4">
                <button onClick={() => { setEditingSectorId(null); setSectorForm({ id: '', label: '', description: '', motivo: '' }); setSectorFormOpen(true); }} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
                    <Plus size={16} /> Novo Setor
                </button>
            </div>

            <div className="space-y-2">
                {sectors.map(sector => (
                    <div key={sector.id} className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden shadow-sm">
                        <div className="p-4 flex items-center justify-between hover:bg-slate-800/60 transition-colors">
                            <div className="flex items-center gap-3 cursor-pointer select-none flex-1" onClick={() => toggleSector(sector.id)}>
                                {expandedSectors.has(sector.id) ? <ChevronDown size={20} className="text-slate-400" /> : <ChevronRight size={20} className="text-slate-400" />}
                                <div className="font-semibold text-lg text-slate-200">{sector.label} <span className="text-xs text-slate-500 font-normal ml-2">({sector.id})</span></div>
                            </div>
                            <div className="flex items-center gap-2">
                                <button title="Histórico" onClick={() => openHistory('sector', sector.id, sector.label)} className="p-2 text-slate-400 hover:text-amber-300 hover:bg-white/5 rounded-lg transition-colors"><History size={16} /></button>
                                <button onClick={() => {
                                    setEditingSectorId(sector.id);
                                    setSectorForm({ id: sector.id, label: sector.label, description: sector.description, motivo: '' });
                                    setSectorFormOpen(true);
                                }} className="p-2 text-slate-400 hover:text-primary-300 hover:bg-white/5 rounded-lg transition-colors"><Pencil size={16} /></button>
                                <button onClick={() => openDelete('sector', sector.id, sector.label)} className="p-2 text-slate-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"><Trash2 size={16} /></button>
                            </div>
                        </div>

                        {expandedSectors.has(sector.id) && (
                            <div className="p-4 pt-0 border-t border-white/5 pl-10 space-y-3">
                                <div className="flex justify-end pt-3">
                                    <button onClick={() => { setEditingAlertId(null); setAlertForm({ original_id: '', label: '', context: '', sector_id: sector.id, pop_ref: '', expected_direction: '', motivo: '' }); setAlertFormOpen(true); }} className="text-xs text-primary-400 font-semibold flex items-center gap-1 hover:text-primary-300">
                                        <Plus size={14} /> Adicionar Alerta
                                    </button>
                                </div>
                                {sector.alertas.map(alert => (
                                    <div key={alert.id} className="bg-slate-800/60 border border-white/10 rounded-lg overflow-hidden">
                                        <div className="p-3 flex items-center justify-between hover:bg-slate-800 transition-colors">
                                            <div className="flex items-center gap-2 cursor-pointer select-none flex-1" onClick={() => toggleAlert(alert.id)}>
                                                {expandedAlerts.has(alert.id) ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}
                                                <div className="font-medium text-slate-300">
                                                    {alert.original_id ? <span className="bg-primary-500/20 text-primary-300 px-1.5 py-0.5 rounded text-[10px] mr-2">{alert.original_id}</span> : null}
                                                    {alert.label}
                                                    {alert.pop_ref ? <span className="ml-2 text-[10px] text-emerald-300 bg-emerald-500/10 px-1.5 py-0.5 rounded">POP {alert.pop_ref}</span> : null}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <button title="Histórico" onClick={() => openHistory('alert', alert.id, alert.label)} className="p-1.5 text-slate-400 hover:text-amber-300 hover:bg-white/5 rounded transition-colors"><History size={14} /></button>
                                                <button onClick={() => {
                                                    setEditingAlertId(alert.id);
                                                    setAlertForm({ original_id: alert.original_id || '', label: alert.label, context: alert.context, sector_id: sector.id, pop_ref: alert.pop_ref || '', expected_direction: alert.expected_direction || '', motivo: '' });
                                                    setAlertFormOpen(true);
                                                }} className="p-1.5 text-slate-400 hover:text-primary-300 hover:bg-white/5 rounded transition-colors"><Pencil size={14} /></button>
                                                <button onClick={() => openDelete('alert', alert.id, alert.label)} className="p-1.5 text-slate-400 hover:text-red-300 hover:bg-red-500/10 rounded transition-colors"><Trash2 size={14} /></button>
                                            </div>
                                        </div>

                                        {expandedAlerts.has(alert.id) && (
                                            <div className="p-3 pt-0 border-t border-white/5 pl-8 space-y-2 mt-2">
                                                <div className="flex justify-end pt-1">
                                                    <button onClick={() => { setEditingCriterionId(null); setCriterionForm({ alert_id: alert.id, chave: '', label: '', weight: 1, description: '', type: 'boolean', deflator: 0, referencia: '', exemplo: '', motivo: '' }); setCriterionFormOpen(true); }} className="text-[11px] text-primary-400 font-semibold flex items-center gap-1 hover:text-primary-300">
                                                        <Plus size={12} /> Adicionar Critério
                                                    </button>
                                                </div>
                                                {alert.criterios.map(crit => (
                                                    <div key={crit.id} className="flex flex-col sm:flex-row sm:items-center justify-between bg-slate-900 border border-white/5 rounded-md p-2 gap-2 group">
                                                        <div className="flex flex-col">
                                                            <div className="text-sm font-medium text-slate-300">{crit.label} <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded ml-1 font-mono">{crit.chave}</span></div>
                                                            <div className="text-[10px] text-slate-500 line-clamp-1">{crit.description}</div>
                                                        </div>
                                                        <div className="flex items-center gap-3 shrink-0">
                                                            <span className="text-[10px] text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded font-medium">Peso: {crit.weight}</span>
                                                            {crit.deflator > 0 && <span className="text-[10px] text-red-400 bg-red-400/10 px-2 py-0.5 rounded font-medium">Deflator: -{crit.deflator}</span>}
                                                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                                <button title="Histórico" onClick={() => openHistory('criterion', crit.id!, crit.label)} className="text-slate-400 hover:text-amber-300"><History size={12} /></button>
                                                                <button onClick={() => {
                                                                    setEditingCriterionId(crit.id!);
                                                                    setCriterionForm({ alert_id: alert.id, chave: crit.chave, label: crit.label, weight: crit.weight, description: crit.description, type: crit.type, deflator: crit.deflator, referencia: crit.referencia || '', exemplo: crit.exemplo || '', motivo: '' });
                                                                    setCriterionFormOpen(true);
                                                                }} className="text-slate-400 hover:text-primary-300"><Pencil size={12} /></button>
                                                                <button onClick={() => openDelete('criterion', crit.id!, crit.label)} className="text-slate-400 hover:text-red-300"><Trash2 size={12} /></button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                                {alert.criterios.length === 0 && <div className="text-xs text-slate-500 text-center py-2">Nenhum critério cadastrado.</div>}
                                            </div>
                                        )}
                                    </div>
                                ))}
                                {sector.alertas.length === 0 && <div className="text-sm text-slate-500 text-center py-4">Nenhum alerta cadastrado.</div>}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* --- Sector Modal --- */}
            {sectorFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-white mb-4">{editingSectorId ? 'Editar Setor' : 'Novo Setor'}</h3>
                        <div className="space-y-4">
                            {!editingSectorId && (
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">ID (Ex: transferencia) *</span>
                                    <input type="text" value={sectorForm.id} onChange={e => setSectorForm({ ...sectorForm, id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                                </label>
                            )}
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Label (Ex: Setor A) *</span>
                                <input type="text" value={sectorForm.label} onChange={e => setSectorForm({ ...sectorForm, label: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                            </label>
                            <MotivoField value={sectorForm.motivo} onChange={v => setSectorForm({ ...sectorForm, motivo: v })} />
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setSectorFormOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleSaveSector} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Salvar'}</button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- Alert Modal --- */}
            {alertFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-white mb-4">{editingAlertId ? 'Editar Alerta' : 'Novo Alerta'}</h3>
                        <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-4">
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">ID Original</span>
                                    <input type="text" value={alertForm.original_id} onChange={e => setAlertForm({ ...alertForm, original_id: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" placeholder="Opcional" />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">POP Ref</span>
                                    <input type="text" value={alertForm.pop_ref} onChange={e => setAlertForm({ ...alertForm, pop_ref: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" placeholder="Opcional" />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Direção (Opcional)</span>
                                    <select value={alertForm.expected_direction} onChange={e => setAlertForm({ ...alertForm, expected_direction: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50">
                                        <option value="">Ambas (N/A)</option>
                                        <option value="efetivada">Efetivada (Ativo)</option>
                                        <option value="receptiva">Receptiva</option>
                                    </select>
                                </label>
                            </div>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Label *</span>
                                <input type="text" value={alertForm.label} onChange={e => setAlertForm({ ...alertForm, label: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Contexto detalhado</span>
                                <textarea value={alertForm.context} onChange={e => setAlertForm({ ...alertForm, context: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" rows={3}></textarea>
                            </label>
                            <MotivoField value={alertForm.motivo} onChange={v => setAlertForm({ ...alertForm, motivo: v })} />
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setAlertFormOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleSaveAlert} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Salvar'}</button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- Criterion Modal --- */}
            {criterionFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-lg bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
                        <h3 className="text-lg font-semibold text-white mb-4">{editingCriterionId ? 'Editar Critério' : 'Novo Critério'}</h3>
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chave Única *</span>
                                    <input type="text" value={criterionForm.chave} onChange={e => setCriterionForm({ ...criterionForm, chave: e.target.value.toLowerCase().replace(/[^a-z_]/g, '') })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 font-mono" placeholder="ex: senha_mestre" />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Tipo *</span>
                                    <select value={criterionForm.type} onChange={e => setCriterionForm({ ...criterionForm, type: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50">
                                        <option value="boolean">Boleano (Conforme/Não Conforme)</option>
                                    </select>
                                </label>
                            </div>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Nome de exibição *</span>
                                <input type="text" value={criterionForm.label} onChange={e => setCriterionForm({ ...criterionForm, label: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Descrição</span>
                                <textarea value={criterionForm.description} onChange={e => setCriterionForm({ ...criterionForm, description: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" rows={2}></textarea>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Referência</span>
                                <input type="text" value={criterionForm.referencia} onChange={e => setCriterionForm({ ...criterionForm, referencia: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" placeholder="Material de apoio ou POP de referência" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Exemplo</span>
                                <textarea value={criterionForm.exemplo} onChange={e => setCriterionForm({ ...criterionForm, exemplo: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" rows={2} placeholder="Exemplo do que considerar acerto ou erro"></textarea>
                            </label>
                            <div className="grid grid-cols-2 gap-4">
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">Peso * <span className="font-normal text-[9px] bg-amber-500/20 text-amber-300 px-1 rounded">Impacta NQ</span></span>
                                    <input type="number" step="0.01" min="0" value={criterionForm.weight} onChange={e => setCriterionForm({ ...criterionForm, weight: parseFloat(e.target.value) || 0 })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">Deflator <span className="font-normal text-[9px] bg-red-500/20 text-red-300 px-1 rounded">Zera Avaliação</span></span>
                                    <input type="number" step="0.01" min="0" value={criterionForm.deflator} onChange={e => setCriterionForm({ ...criterionForm, deflator: parseFloat(e.target.value) || 0 })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" placeholder="0 para não deflar" />
                                </label>
                            </div>
                            <MotivoField value={criterionForm.motivo} onChange={v => setCriterionForm({ ...criterionForm, motivo: v })} />
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setCriterionFormOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleSaveCriterion} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Salvar'}</button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- Delete Confirm Modal --- */}
            {deleteTarget && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-red-500/30 rounded-2xl p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-red-300 mb-2">Excluir {ENTITY_LABEL[deleteTarget.type]}?</h3>
                        <p className="text-sm text-slate-300 mb-4">
                            <span className="font-medium text-slate-100">{deleteTarget.label}</span>
                            {deleteTarget.type !== 'criterion' && (
                                <span className="block mt-1 text-xs text-amber-300">Esta ação remove em cascata os itens filhos.</span>
                            )}
                        </p>
                        <label className="block">
                            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo da exclusão *</span>
                            <textarea
                                value={deleteMotivo}
                                onChange={e => setDeleteMotivo(e.target.value)}
                                rows={3}
                                placeholder="Explique brevemente por que está excluindo."
                                className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-red-500/50 resize-y"
                            />
                        </label>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setDeleteTarget(null)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button
                                disabled={submitting}
                                onClick={confirmDelete}
                                className="px-4 py-2 text-sm font-semibold rounded-xl bg-red-500/90 hover:bg-red-500 text-white disabled:opacity-50"
                            >
                                {submitting ? 'Excluindo...' : 'Excluir'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- History Drawer --- */}
            {historyTarget && (
                <div className="fixed inset-0 z-50 flex">
                    <div className="flex-1 bg-black/60 backdrop-blur-sm" onClick={closeHistory} />
                    <div className="w-full max-w-md bg-slate-900 border-l border-white/10 shadow-2xl flex flex-col">
                        <div className="p-4 border-b border-white/10 flex items-start justify-between">
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-slate-500">Histórico do {ENTITY_LABEL[historyTarget.type]}</div>
                                <div className="text-base font-semibold text-slate-100 mt-0.5">{historyTarget.label}</div>
                                <div className="text-[10px] font-mono text-slate-500 mt-0.5">id: {historyTarget.id}</div>
                            </div>
                            <button onClick={closeHistory} className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/5 rounded-lg"><X size={18} /></button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                            {historyLoading && <div className="flex justify-center py-10"><Loader2 className="animate-spin text-primary-500 w-6 h-6" /></div>}
                            {!historyLoading && historyEntries.length === 0 && (
                                <div className="text-sm text-slate-500 text-center py-10">Nenhuma alteração registrada ainda.</div>
                            )}
                            {!historyLoading && historyEntries.map(entry => (
                                <HistoryEntryCard
                                    key={entry.id}
                                    entry={entry}
                                    expanded={historyExpandedId === entry.id}
                                    onToggle={() => setHistoryExpandedId(historyExpandedId === entry.id ? null : entry.id)}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function MotivoField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    return (
        <label className="block">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo da alteração *</span>
            <textarea
                value={value}
                onChange={e => onChange(e.target.value)}
                rows={2}
                placeholder="Explique brevemente por que essa mudança está sendo feita (fica registrado no histórico)."
                className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y"
            />
        </label>
    );
}

function HistoryEntryCard({ entry, expanded, onToggle }: { entry: AuditLogEntry; expanded: boolean; onToggle: () => void }) {
    const acaoBadge: Record<AuditLogEntry['acao'], string> = {
        create: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
        update: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
        delete: 'bg-red-500/15 text-red-300 border-red-500/30',
    };
    const acaoLabel: Record<AuditLogEntry['acao'], string> = {
        create: 'Criado',
        update: 'Editado',
        delete: 'Excluído',
    };
    return (
        <div className="bg-slate-800/60 border border-white/10 rounded-xl overflow-hidden">
            <button onClick={onToggle} className="w-full p-3 text-left hover:bg-slate-800/80 transition-colors">
                <div className="flex items-center justify-between gap-2">
                    <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded border ${acaoBadge[entry.acao]}`}>{acaoLabel[entry.acao]}</span>
                    <span className="text-[10px] text-slate-500">{formatTimestamp(entry.alterado_em)}</span>
                </div>
                <div className="mt-2 text-xs text-slate-300">
                    por <span className="font-semibold text-slate-100">{entry.alterado_por}</span>
                    <span className="text-slate-500"> · {entry.origem}</span>
                </div>
                {entry.motivo && (
                    <div className="mt-1 text-xs text-slate-400 italic line-clamp-2">"{entry.motivo}"</div>
                )}
            </button>
            {expanded && (
                <div className="px-3 pb-3 pt-1 border-t border-white/5 space-y-2">
                    <DiffView antes={entry.payload_antes} depois={entry.payload_depois} acao={entry.acao} />
                </div>
            )}
        </div>
    );
}

function DiffView({ antes, depois, acao }: { antes: Record<string, any> | null; depois: Record<string, any> | null; acao: AuditLogEntry['acao'] }) {
    if (acao === 'create' && depois) {
        return (
            <div>
                <div className="text-[10px] uppercase text-emerald-300 mb-1">Valores criados</div>
                <PayloadKv obj={depois} variant="depois" />
            </div>
        );
    }
    if (acao === 'delete' && antes) {
        return (
            <div>
                <div className="text-[10px] uppercase text-red-300 mb-1">Valores removidos</div>
                <PayloadKv obj={antes} variant="antes" />
            </div>
        );
    }
    if (acao === 'update' && antes && depois) {
        const keys = new Set([...Object.keys(antes), ...Object.keys(depois)]);
        const changed: Array<{ key: string; antes: any; depois: any }> = [];
        keys.forEach(k => {
            if (JSON.stringify(antes[k]) !== JSON.stringify(depois[k])) {
                changed.push({ key: k, antes: antes[k], depois: depois[k] });
            }
        });
        if (changed.length === 0) {
            return <div className="text-[11px] text-slate-500">Sem alterações visíveis no payload.</div>;
        }
        return (
            <div className="space-y-1.5">
                <div className="text-[10px] uppercase text-amber-300">Campos alterados</div>
                {changed.map(({ key, antes: a, depois: d }) => (
                    <div key={key} className="bg-slate-900 rounded-md p-2 border border-white/5">
                        <div className="text-[10px] font-mono text-slate-400 mb-0.5">{key}</div>
                        <div className="text-[11px] text-red-300 font-mono break-all">- {formatValue(a)}</div>
                        <div className="text-[11px] text-emerald-300 font-mono break-all">+ {formatValue(d)}</div>
                    </div>
                ))}
            </div>
        );
    }
    return <div className="text-[11px] text-slate-500">Sem payload registrado.</div>;
}

function PayloadKv({ obj, variant }: { obj: Record<string, any>; variant: 'antes' | 'depois' }) {
    const color = variant === 'depois' ? 'text-emerald-300' : 'text-red-300';
    return (
        <div className="space-y-0.5 bg-slate-900 rounded-md p-2 border border-white/5">
            {Object.entries(obj).map(([k, v]) => (
                <div key={k} className="text-[11px] font-mono">
                    <span className="text-slate-500">{k}:</span> <span className={`${color} break-all`}>{formatValue(v)}</span>
                </div>
            ))}
        </div>
    );
}

function formatValue(v: any): string {
    if (v === null || v === undefined) return '∅';
    if (typeof v === 'string') return v;
    return JSON.stringify(v);
}
