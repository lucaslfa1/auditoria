import { useEffect, useState } from 'react';
import { Loader2, Plus, Pencil, Trash2, Users } from 'lucide-react';
import { PageHeader } from '../../../shared/components/PageHeader';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

interface Sector {
    id: string;
    label: string;
    description: string | null;
}

interface CreateForm {
    id: string;
    label: string;
    description: string;
    motivo: string;
}

interface RenameForm {
    sectorId: string;
    currentLabel: string;
    newLabel: string;
    description: string;
    cascade: boolean;
    motivo: string;
}

export function SectorManagement() {
    const { showToast } = useToast();
    const [sectors, setSectors] = useState<Sector[]>([]);
    const [memberCounts, setMemberCounts] = useState<Record<string, number>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const [createOpen, setCreateOpen] = useState(false);
    const [createForm, setCreateForm] = useState<CreateForm>({ id: '', label: '', description: '', motivo: '' });

    const [renameForm, setRenameForm] = useState<RenameForm | null>(null);
    const [renamePreview, setRenamePreview] = useState<{ loading: boolean; count: number | null }>({ loading: false, count: null });

    const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
    const [deleteMotivo, setDeleteMotivo] = useState('');

    const fetchData = async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            setError(null);
            const data = await apiFetchJson<Sector[]>('/api/admin/sectors');
            setSectors(data);
            // Contagem de vinculados (best-effort, em paralelo) — não bloqueia a lista.
            const entries = await Promise.allSettled(
                data.map(async (s) => {
                    const res = await apiFetchJson<{ count: number }>(
                        `/api/admin/sectors/${encodeURIComponent(s.id)}/members`
                    );
                    return [s.id, res.count] as const;
                })
            );
            const counts: Record<string, number> = {};
            for (const e of entries) {
                if (e.status === 'fulfilled') counts[e.value[0]] = e.value[1];
            }
            setMemberCounts(counts);
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar setores');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleCreate = async () => {
        if (!createForm.id.trim() || !createForm.label.trim()) {
            showToast({ variant: 'error', title: 'Campos obrigatórios', description: 'Informe o ID e o nome do setor.' });
            return;
        }
        try {
            setSubmitting(true);
            await apiFetchJson('/api/admin/sectors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: createForm.id.trim(),
                    label: createForm.label.trim(),
                    description: createForm.description || null,
                    motivo: createForm.motivo || null,
                }),
            });
            setCreateOpen(false);
            await fetchData(true);
            showToast({ variant: 'success', title: 'Setor criado', description: `"${createForm.label}" foi criado.` });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao criar', description: err.message });
        } finally {
            setSubmitting(false);
        }
    };

    const openRename = async (sector: Sector) => {
        setRenameForm({
            sectorId: sector.id,
            currentLabel: sector.label,
            newLabel: sector.label,
            description: sector.description || '',
            cascade: true,
            motivo: '',
        });
        setRenamePreview({ loading: true, count: null });
        try {
            const res = await apiFetchJson<{ count: number }>(
                `/api/admin/sectors/${encodeURIComponent(sector.id)}/members`
            );
            setRenamePreview({ loading: false, count: res.count });
        } catch {
            setRenamePreview({ loading: false, count: null });
        }
    };

    const handleRename = async () => {
        if (!renameForm) return;
        if (!renameForm.newLabel.trim()) {
            showToast({ variant: 'error', title: 'Nome obrigatório', description: 'Informe o novo nome do setor.' });
            return;
        }
        try {
            setSubmitting(true);
            const res = await apiFetchJson<{ affected: number }>(
                `/api/admin/sectors/${encodeURIComponent(renameForm.sectorId)}/rename`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        new_label: renameForm.newLabel.trim(),
                        description: renameForm.description || null,
                        cascade: renameForm.cascade,
                        motivo: renameForm.motivo || null,
                    }),
                }
            );
            setRenameForm(null);
            await fetchData(true);
            showToast({
                variant: 'success',
                title: 'Setor renomeado',
                description: renameForm.cascade
                    ? `${res.affected} colaborador(es) atualizados. Regras de auditoria mantidas.`
                    : 'Rótulo atualizado. Regras de auditoria mantidas.',
            });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao renomear', description: err.message });
        } finally {
            setSubmitting(false);
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        if (!deleteMotivo.trim()) {
            showToast({ variant: 'error', title: 'Motivo obrigatório', description: 'Informe o motivo da exclusão.' });
            return;
        }
        try {
            setSubmitting(true);
            await apiFetchJson(
                `/api/admin/sectors/${encodeURIComponent(deleteTarget.id)}?motivo=${encodeURIComponent(deleteMotivo)}`,
                { method: 'DELETE' }
            );
            setDeleteTarget(null);
            await fetchData(true);
            showToast({ variant: 'success', title: 'Setor removido', description: `"${deleteTarget.label}" foi excluído.` });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao excluir', description: err.message });
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-primary-500 w-8 h-8" /></div>;
    }

    return (
        <div className="space-y-6 pb-10">
            <PageHeader
                eyebrow="nstech | Administração"
                titleFirstWord="Setores"
                titleRest="de Auditoria"
                subtitle="Crie e renomeie setores. Ao renomear, o novo nome é aplicado a todos os colaboradores vinculados — e as regras de auditoria continuam exatamente as mesmas."
            />
            {error && <div className="text-red-400 p-4 rounded bg-red-500/10 border border-red-500/20">{error}</div>}

            <div className="flex justify-between mb-4">
                <button
                    onClick={() => { setCreateForm({ id: '', label: '', description: '', motivo: '' }); setCreateOpen(true); }}
                    className="btn-primary text-sm px-4 py-2 flex items-center gap-2"
                >
                    <Plus size={16} /> Novo Setor
                </button>
            </div>

            <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden shadow-sm">
                {sectors.length === 0 ? (
                    <div className="p-6 text-center text-slate-400">Nenhum setor cadastrado.</div>
                ) : (
                    <table className="w-full text-left text-sm text-slate-300">
                        <thead className="bg-slate-900/50 border-b border-white/10 text-slate-400 text-xs uppercase">
                            <tr>
                                <th className="px-4 py-3 font-medium">Nome</th>
                                <th className="px-4 py-3 font-medium">ID interno</th>
                                <th className="px-4 py-3 font-medium">Colaboradores</th>
                                <th className="px-4 py-3 font-medium">Descrição</th>
                                <th className="px-4 py-3 font-medium text-right">Ações</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {sectors.map(sector => (
                                <tr key={sector.id} className="hover:bg-slate-800/40 transition-colors">
                                    <td className="px-4 py-3 font-semibold text-slate-100">{sector.label}</td>
                                    <td className="px-4 py-3 font-mono text-xs text-slate-500">{sector.id}</td>
                                    <td className="px-4 py-3">
                                        <span className="inline-flex items-center gap-1.5 text-slate-300">
                                            <Users size={14} className="text-slate-500" />
                                            {memberCounts[sector.id] ?? '—'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-xs text-slate-400">{sector.description || '—'}</td>
                                    <td className="px-4 py-3 flex items-center justify-end gap-2">
                                        <button
                                            onClick={() => openRename(sector)}
                                            title="Renomear"
                                            className="p-2 text-slate-400 hover:text-primary-300 hover:bg-white/5 rounded-lg transition-colors"
                                        >
                                            <Pencil size={16} />
                                        </button>
                                        <button
                                            onClick={() => { setDeleteTarget({ id: sector.id, label: sector.label }); setDeleteMotivo(''); }}
                                            title="Excluir"
                                            className="p-2 text-slate-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {createOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-y-auto max-h-[90vh]">
                        <h3 className="text-lg font-semibold text-white mb-4">Novo Setor</h3>
                        <div className="space-y-4">
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">ID interno *</span>
                                <input
                                    type="text"
                                    value={createForm.id}
                                    onChange={e => setCreateForm({ ...createForm, id: e.target.value })}
                                    placeholder="ex: distribuicao"
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 font-mono"
                                />
                                <span className="text-[11px] text-slate-500 mt-1 block">Sem acentos/espaços. É a chave das regras — não muda depois.</span>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Nome (rótulo) *</span>
                                <input
                                    type="text"
                                    value={createForm.label}
                                    onChange={e => setCreateForm({ ...createForm, label: e.target.value })}
                                    placeholder="ex: Distribuição"
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50"
                                />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Descrição</span>
                                <textarea
                                    value={createForm.description}
                                    onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                                    rows={2}
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y"
                                ></textarea>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo</span>
                                <textarea
                                    value={createForm.motivo}
                                    onChange={e => setCreateForm({ ...createForm, motivo: e.target.value })}
                                    rows={2}
                                    placeholder="Para registro em auditoria"
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y"
                                ></textarea>
                            </label>
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setCreateOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleCreate} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Criar'}</button>
                        </div>
                    </div>
                </div>
            )}

            {renameForm && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-y-auto max-h-[90vh]">
                        <h3 className="text-lg font-semibold text-white mb-1">Renomear Setor</h3>
                        <p className="text-xs text-slate-400 mb-4">
                            ID interno <span className="font-mono text-slate-300">{renameForm.sectorId}</span> — não muda; as regras de auditoria continuam as mesmas.
                        </p>
                        <div className="space-y-4">
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Novo nome *</span>
                                <input
                                    type="text"
                                    value={renameForm.newLabel}
                                    onChange={e => setRenameForm({ ...renameForm, newLabel: e.target.value })}
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50"
                                />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Descrição</span>
                                <textarea
                                    value={renameForm.description}
                                    onChange={e => setRenameForm({ ...renameForm, description: e.target.value })}
                                    rows={2}
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y"
                                ></textarea>
                            </label>
                            <label className="flex items-start gap-3 cursor-pointer rounded-xl border border-white/10 bg-slate-800/50 p-3">
                                <input
                                    type="checkbox"
                                    checked={renameForm.cascade}
                                    onChange={e => setRenameForm({ ...renameForm, cascade: e.target.checked })}
                                    className="mt-0.5 h-4 w-4 accent-primary-500"
                                />
                                <span className="text-sm text-slate-300">
                                    Aplicar o novo nome aos colaboradores vinculados
                                    <span className="block text-[11px] text-slate-500 mt-0.5">
                                        {renamePreview.loading
                                            ? 'Calculando...'
                                            : renamePreview.count === null
                                                ? 'Não foi possível contar os vinculados.'
                                                : `${renamePreview.count} colaborador(es) serão atualizados.`}
                                    </span>
                                </span>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo</span>
                                <textarea
                                    value={renameForm.motivo}
                                    onChange={e => setRenameForm({ ...renameForm, motivo: e.target.value })}
                                    rows={2}
                                    placeholder="Para registro em auditoria"
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y"
                                ></textarea>
                            </label>
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setRenameForm(null)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleRename} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Renomear'}</button>
                        </div>
                    </div>
                </div>
            )}

            {deleteTarget && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-red-500/30 rounded-2xl p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-red-300 mb-2">Excluir Setor?</h3>
                        <p className="text-sm text-slate-300 mb-4">
                            Excluir o setor <span className="font-semibold text-slate-100">{deleteTarget.label}</span>? Os critérios vinculados a ele podem deixar de ser aplicados.
                        </p>
                        <label className="block">
                            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo da exclusão *</span>
                            <textarea
                                value={deleteMotivo}
                                onChange={e => setDeleteMotivo(e.target.value)}
                                rows={2}
                                className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-red-500/50 resize-y"
                            />
                        </label>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setDeleteTarget(null)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={confirmDelete} className="px-4 py-2 text-sm font-semibold rounded-xl bg-red-500/90 hover:bg-red-500 text-white disabled:opacity-50">{submitting ? 'Excluindo...' : 'Excluir'}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
