/**
 * Tela de admin dos APELIDOS de setor (sector_aliases): mapeia rótulos crus
 * (ex.: "BASE PR - AZUL") para o setor canônico interno (ex.: "bas").
 *
 * CRUD via `/api/admin/sector-aliases` (GET; POST; PUT `/{id}`; DELETE `/{id}`),
 * com `/cache/invalidate` para recarregar. Resolver o alias certo é o que liga a
 * ligação ao catálogo de critérios correto na classificação/auditoria.
 */
import { useEffect, useState } from 'react';
import { Loader2, Plus, Pencil, Trash2, RefreshCw } from 'lucide-react';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

interface SectorAlias {
    id: number;
    pattern_type: string;
    pattern_value: string;
    canonical_sector_id: string;
    priority: number;
    descricao: string;
}

interface AliasForm {
    pattern_type: string;
    pattern_value: string;
    canonical_sector_id: string;
    priority: number;
    descricao: string;
    motivo: string;
}

export function AdminSectorAliasesPage() {
    const { showToast } = useToast();
    const [aliases, setAliases] = useState<SectorAlias[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [formOpen, setFormOpen] = useState(false);
    const [form, setForm] = useState<AliasForm>({ pattern_type: 'exact', pattern_value: '', canonical_sector_id: '', priority: 0, descricao: '', motivo: '' });
    const [editingId, setEditingId] = useState<number | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const [deleteTarget, setDeleteTarget] = useState<{ id: number, value: string } | null>(null);
    const [deleteMotivo, setDeleteMotivo] = useState('');

    const fetchData = async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            setError(null);
            const data = await apiFetchJson<SectorAlias[]>('/api/admin/sector-aliases');
            setAliases(data);
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar apelidos');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleInvalidateCache = async () => {
        try {
            await apiFetchJson('/api/admin/sector-aliases/cache/invalidate', { method: 'POST' });
            showToast({ variant: 'success', title: 'Cache invalidado', description: 'O cache de apelidos foi limpo com sucesso.' });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao invalidar cache', description: err.message });
        }
    };

    const handleSave = async () => {
        if (!form.pattern_value.trim() || !form.canonical_sector_id.trim()) {
            showToast({ variant: 'error', title: 'Campos obrigatórios', description: 'Preencha o valor e o setor canônico.' });
            return;
        }
        if (!form.motivo.trim()) {
            showToast({ variant: 'error', title: 'Motivo obrigatório', description: 'Descreva o motivo da alteração.' });
            return;
        }

        try {
            setSubmitting(true);
            if (editingId) {
                await apiFetchJson(`/api/admin/sector-aliases/${editingId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(form)
                });
            } else {
                await apiFetchJson('/api/admin/sector-aliases', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(form)
                });
            }
            setFormOpen(false);
            await fetchData(true);
            showToast({ variant: 'success', title: 'Sucesso', description: editingId ? 'Apelido atualizado.' : 'Apelido criado.' });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro', description: err.message });
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
            await apiFetchJson(`/api/admin/sector-aliases/${deleteTarget.id}?motivo=${encodeURIComponent(deleteMotivo)}`, { method: 'DELETE' });
            setDeleteTarget(null);
            await fetchData(true);
            showToast({ variant: 'success', title: 'Sucesso', description: 'Apelido removido.' });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro', description: err.message });
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-primary-500 w-8 h-8" /></div>
    }

    return (
        <div className="space-y-6 pb-10">
            <PageHeader
                eyebrow="nstech | Administração"
                titleFirstWord="Apelidos"
                titleRest="de Setor"
                subtitle="Ensine o sistema a reconhecer os setores corretos quando a telefonia enviar nomes diferentes, com erro ou abreviados."
            />

            <ModuleInstructions
                storageKey="instructions:aliases"
                steps={[
                    'Cadastre apelidos para os nomes de setor que a telefonia envia.',
                    'Vincule cada apelido (abreviado ou com erro) ao setor correto.',
                    'O sistema passa a reconhecer esses nomes automaticamente.',
                ]}
            />
            {error && <div className="text-red-400 p-4 rounded bg-red-500/10 border border-red-500/20">{error}</div>}

            <div className="flex justify-between mb-4">
                <button onClick={() => {
                    setEditingId(null);
                    setForm({ pattern_type: 'exact', pattern_value: '', canonical_sector_id: '', priority: 0, descricao: '', motivo: '' });
                    setFormOpen(true);
                }} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
                    <Plus size={16} /> Novo Apelido
                </button>
                <button onClick={handleInvalidateCache} className="btn-ghost text-sm px-4 py-2 flex items-center gap-2 text-slate-300 hover:text-white">
                    <RefreshCw size={16} /> Invalidar Cache
                </button>
            </div>

            <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden shadow-sm">
                {aliases.length === 0 ? (
                    <div className="p-6 text-center text-slate-400">Nenhum apelido cadastrado.</div>
                ) : (
                    <table className="w-full text-left text-sm text-slate-300">
                        <thead className="bg-slate-900/50 border-b border-white/10 text-slate-400 text-xs uppercase">
                            <tr>
                                <th className="px-4 py-3 font-medium">Prioridade</th>
                                <th className="px-4 py-3 font-medium">Tipo</th>
                                <th className="px-4 py-3 font-medium">Valor (Pattern)</th>
                                <th className="px-4 py-3 font-medium">Canônico</th>
                                <th className="px-4 py-3 font-medium">Descrição</th>
                                <th className="px-4 py-3 font-medium text-right">Ações</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {aliases.map(alias => (
                                <tr key={alias.id} className="hover:bg-slate-800/40 transition-colors">
                                    <td className="px-4 py-3 font-mono">{alias.priority}</td>
                                    <td className="px-4 py-3"><span className="bg-slate-800 px-2 py-1 rounded text-xs">{alias.pattern_type}</span></td>
                                    <td className="px-4 py-3 font-mono text-emerald-300">{alias.pattern_value}</td>
                                    <td className="px-4 py-3 font-bold text-slate-200">{alias.canonical_sector_id}</td>
                                    <td className="px-4 py-3 text-xs text-slate-400">{alias.descricao}</td>
                                    <td className="px-4 py-3 flex items-center justify-end gap-2">
                                        <button onClick={() => {
                                            setEditingId(alias.id);
                                            setForm({
                                                pattern_type: alias.pattern_type,
                                                pattern_value: alias.pattern_value,
                                                canonical_sector_id: alias.canonical_sector_id,
                                                priority: alias.priority,
                                                descricao: alias.descricao || '',
                                                motivo: ''
                                            });
                                            setFormOpen(true);
                                        }} className="p-2 text-slate-400 hover:text-primary-300 hover:bg-white/5 rounded-lg transition-colors"><Pencil size={16} /></button>
                                        <button onClick={() => {
                                            setDeleteTarget({ id: alias.id, value: alias.pattern_value });
                                            setDeleteMotivo('');
                                        }} className="p-2 text-slate-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"><Trash2 size={16} /></button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {formOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-y-auto max-h-[90vh]">
                        <h3 className="text-lg font-semibold text-white mb-4">{editingId ? 'Editar Apelido' : 'Novo Apelido'}</h3>
                        <div className="space-y-4">
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Tipo *</span>
                                <select value={form.pattern_type} onChange={e => setForm({ ...form, pattern_type: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50">
                                    <option value="exact">Exato (exact)</option>
                                    <option value="contains">Contém (contains)</option>
                                    <option value="regex">Regex (regex)</option>
                                </select>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Valor (Pattern) *</span>
                                <input type="text" value={form.pattern_value} onChange={e => setForm({ ...form, pattern_value: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 font-mono" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Setor Canônico (ID) *</span>
                                <input type="text" value={form.canonical_sector_id} onChange={e => setForm({ ...form, canonical_sector_id: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Prioridade</span>
                                <input type="number" value={form.priority} onChange={e => setForm({ ...form, priority: parseInt(e.target.value) || 0 })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50" />
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Descrição</span>
                                <textarea value={form.descricao} onChange={e => setForm({ ...form, descricao: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" rows={2}></textarea>
                            </label>
                            <label className="block">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo da Alteração *</span>
                                <textarea value={form.motivo} onChange={e => setForm({ ...form, motivo: e.target.value })} className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" rows={2} placeholder="Obrigatório para registro em auditoria"></textarea>
                            </label>
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setFormOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleSave} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Salvar'}</button>
                        </div>
                    </div>
                </div>
            )}

            {deleteTarget && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-slate-900 border border-red-500/30 rounded-2xl p-6 shadow-2xl">
                        <h3 className="text-lg font-semibold text-red-300 mb-2">Excluir Apelido?</h3>
                        <p className="text-sm text-slate-300 mb-4">
                            Você tem certeza que deseja excluir o apelido <span className="font-mono text-emerald-300">{deleteTarget.value}</span>?
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