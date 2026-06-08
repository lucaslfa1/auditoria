import { useState, useEffect } from 'react';
import { Loader2, Pencil, Trash2, UserPlus, X } from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

interface UserRow {
  id: number;
  username: string;
  role: string;
  supervisor_name: string;
  sector_id?: string;
  escala?: string;
}

export function UserManagement() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { showToast } = useToast();

  // New user form
  const [showForm, setShowForm] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'supervisor'>('admin');
  const [newSupervisorName, setNewSupervisorName] = useState('');
  const [newSectorId, setNewSectorId] = useState('');
  const [newEscala, setNewEscala] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Edit user state
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [editPassword, setEditPassword] = useState('');
  const [editRole, setEditRole] = useState<'admin' | 'supervisor'>('admin');
  const [editSupervisorName, setEditSupervisorName] = useState('');
  const [editSectorId, setEditSectorId] = useState('');
  const [editEscala, setEditEscala] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);

  const [deletingUser, setDeletingUser] = useState<string | null>(null);

  const fetchUsers = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await apiFetchJson<UserRow[]>('/api/admin/users');
      setUsers(data);
    } catch {
      setError('Falha ao carregar usuários.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreate = async () => {
    if (!newUsername.trim() || !newPassword.trim()) return;
    try {
      setIsCreating(true);
      setError(null);
      await apiFetchJson('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword,
          role: newRole,
          supervisor_name: newSupervisorName.trim(),
          sector_id: newSectorId.trim(),
          escala: newEscala.trim(),
        }),
      });
      setNewUsername('');
      setNewPassword('');
      setNewRole('admin');
      setNewSupervisorName('');
      setNewSectorId('');
      setNewEscala('');
      setShowForm(false);
      showToast({ variant: 'success', title: 'Usuário criado', description: `Conta "${newUsername.trim()}" criada com sucesso.` });
      await fetchUsers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao criar o usuário.';
      setError(message);
    } finally {
      setIsCreating(false);
    }
  };

  const openEditForm = (user: UserRow) => {
    setEditingUser(user.username);
    setEditPassword('');
    setEditRole(user.role as 'admin' | 'supervisor');
    setEditSupervisorName(user.supervisor_name || '');
    setEditSectorId(user.sector_id || '');
    setEditEscala(user.escala || '');
    setShowForm(false);
  };

  const cancelEdit = () => {
    setEditingUser(null);
    setEditPassword('');
  };

  const handleUpdate = async () => {
    if (!editingUser) return;
    try {
      setIsUpdating(true);
      setError(null);
      await apiFetchJson(`/api/admin/users/${encodeURIComponent(editingUser)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          password: editPassword,
          role: editRole,
          supervisor_name: editSupervisorName.trim(),
          sector_id: editSectorId.trim(),
          escala: editEscala.trim(),
        }),
      });
      showToast({ variant: 'success', title: 'Usuário atualizado', description: `Conta "${editingUser}" atualizada.` });
      cancelEdit();
      await fetchUsers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao atualizar o usuário.';
      setError(message);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async (username: string) => {
    if (!window.confirm(`Excluir o usuário "${username}"?`)) return;
    try {
      setDeletingUser(username);
      setError(null);
      await apiFetchJson(`/api/admin/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
      await fetchUsers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao excluir o usuário.';
      setError(message);
    } finally {
      setDeletingUser(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-2 animate-fade-in">
      <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4 theme-light:border-slate-300">
        <div>
          <h2 className="text-2xl font-black text-white theme-light:text-slate-900">Usuários</h2>
          <p className="text-slate-400 text-sm mt-1">Gerencie as contas de acesso ao sistema.</p>
        </div>
        <button
          onClick={() => { setShowForm(!showForm); cancelEdit(); }}
          className="btn-primary px-4 py-2.5 rounded-lg font-semibold flex items-center gap-2 text-sm"
        >
          <UserPlus className="w-4 h-4" />
          Novo usuário
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-red-400 text-sm mb-4">
          {error}
        </div>
      )}

      {showForm && (
        <div className="panel-box-lg mb-6 theme-light:bg-slate-200 theme-light:border-slate-300">
          <h3 className="text-lg font-bold text-white theme-light:text-slate-900 mb-4">Criar usuário</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <input
              type="text"
              placeholder="Nome de usuário"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className="p-3 glass-input rounded-xl outline-none text-sm"
            />
            <input
              type="password"
              placeholder="Senha"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="p-3 glass-input rounded-xl outline-none text-sm"
            />
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as 'admin' | 'supervisor')}
              className="p-3 glass-input rounded-xl outline-none text-sm bg-transparent"
            >
              <option value="admin">Administrador</option>
              <option value="supervisor">Supervisor</option>
            </select>
            <input
              type="text"
              placeholder="Nome do supervisor (opcional)"
              value={newSupervisorName}
              onChange={(e) => setNewSupervisorName(e.target.value)}
              className="p-3 glass-input rounded-xl outline-none text-sm"
            />
            <input
              type="text"
              placeholder="Setor (opcional)"
              value={newSectorId}
              onChange={(e) => setNewSectorId(e.target.value)}
              className="p-3 glass-input rounded-xl outline-none text-sm"
            />
            <input
              type="text"
              placeholder="Escala (opcional)"
              value={newEscala}
              onChange={(e) => setNewEscala(e.target.value)}
              className="p-3 glass-input rounded-xl outline-none text-sm"
            />
          </div>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-white transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={handleCreate}
              disabled={isCreating || !newUsername.trim() || !newPassword.trim()}
              className={`btn-primary px-6 py-2 rounded-lg font-semibold text-sm flex items-center gap-2 ${
                isCreating ? 'opacity-70 cursor-not-allowed' : ''
              }`}
            >
              {isCreating && <Loader2 className="w-4 h-4 animate-spin" />}
              Criar usuário
            </button>
          </div>
        </div>
      )}

      {editingUser && (
        <div className="panel-box-lg mb-6 border-primary-500/30 bg-primary-500/5 theme-light:bg-primary-50 theme-light:border-primary-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-white theme-light:text-slate-900">
              Editar usuário: <span className="text-primary-400">{editingUser}</span>
            </h3>
            <button onClick={cancelEdit} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase">Nova senha (deixe vazio)</span>
              <input
                type="password"
                placeholder="••••••••"
                value={editPassword}
                onChange={(e) => setEditPassword(e.target.value)}
                className="w-full p-3 glass-input rounded-xl outline-none text-sm"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase">Perfil</span>
              <select
                value={editRole}
                onChange={(e) => setEditRole(e.target.value as 'admin' | 'supervisor')}
                className="w-full p-3 glass-input rounded-xl outline-none text-sm bg-transparent"
              >
                <option value="admin">Administrador</option>
                <option value="supervisor">Supervisor</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase">Nome supervisor</span>
              <input
                type="text"
                placeholder="Nome do supervisor"
                value={editSupervisorName}
                onChange={(e) => setEditSupervisorName(e.target.value)}
                className="w-full p-3 glass-input rounded-xl outline-none text-sm"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase">Setor</span>
              <input
                type="text"
                placeholder="Setor"
                value={editSectorId}
                onChange={(e) => setEditSectorId(e.target.value)}
                className="w-full p-3 glass-input rounded-xl outline-none text-sm"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-400 uppercase">Escala</span>
              <input
                type="text"
                placeholder="Escala"
                value={editEscala}
                onChange={(e) => setEditEscala(e.target.value)}
                className="w-full p-3 glass-input rounded-xl outline-none text-sm"
              />
            </label>
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={cancelEdit} className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-white transition-colors">
              Cancelar
            </button>
            <button
              onClick={handleUpdate}
              disabled={isUpdating}
              className={`btn-primary px-6 py-2 rounded-lg font-semibold text-sm flex items-center gap-2 ${
                isUpdating ? 'opacity-70 cursor-not-allowed' : ''
              }`}
            >
              {isUpdating && <Loader2 className="w-4 h-4 animate-spin" />}
              Salvar alterações
            </button>
          </div>
        </div>
      )}

      <div className="panel-box-plain theme-light:bg-slate-200 theme-light:border-slate-300">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 theme-light:border-slate-300">
              <th className="text-left px-6 py-4 text-slate-400 font-semibold uppercase text-xs tracking-wider">Usuário</th>
              <th className="text-left px-6 py-4 text-slate-400 font-semibold uppercase text-xs tracking-wider">Perfil</th>
              <th className="text-left px-6 py-4 text-slate-400 font-semibold uppercase text-xs tracking-wider">Supervisor</th>
              <th className="text-right px-6 py-4 text-slate-400 font-semibold uppercase text-xs tracking-wider">Ações</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-white/5 theme-light:border-slate-200 hover:bg-white/5 transition-colors">
                <td className="px-6 py-4 text-white theme-light:text-slate-900 font-medium">{u.username}</td>
                <td className="px-6 py-4">
                  <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                    u.role === 'admin'
                      ? 'bg-primary-500/15 text-primary-400 border border-primary-500/30'
                      : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  }`}>
                    {u.role === 'admin' ? 'Administrador' : 'Supervisor'}
                  </span>
                </td>
                <td className="px-6 py-4 text-slate-400">{u.supervisor_name || '—'}</td>
                <td className="px-6 py-4 text-right">
                  <div className="inline-flex gap-1">
                    <button
                      onClick={() => openEditForm(u)}
                      className="text-primary-400/60 hover:text-primary-400 transition-colors p-1.5 rounded-lg hover:bg-primary-500/10"
                      title="Editar usuário"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(u.username)}
                      disabled={deletingUser === u.username}
                      className="text-red-400/60 hover:text-red-400 transition-colors p-1.5 rounded-lg hover:bg-red-500/10"
                      title="Excluir usuário"
                    >
                      {deletingUser === u.username ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                  Nenhum usuário cadastrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
