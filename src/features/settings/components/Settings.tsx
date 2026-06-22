/**
 * Hub de CONFIGURAÇÕES (aba Settings). Componente de layout que reúne os painéis
 * de configuração do sistema (telefonia, automação, usuários, tema, operadores
 * etc.). Cada sub-painel tem seus próprios endpoints; esta casca só organiza a
 * navegação entre eles.
 */
import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { TelephonySettings } from './TelephonySettings';
import { UserManagement } from './UserManagement';

// 1. Zod Schema Definition
const ConfigItemSchema = z.object({
  valor: z.any().transform(v => (v == null ? '' : String(v))),
  descricao: z.any().transform(v => (v == null ? '' : String(v))),
});

const ConfigsSchema = z.record(z.string(), ConfigItemSchema);

type Configs = z.infer<typeof ConfigsSchema>;

export function Settings() {
  const queryClient = useQueryClient();

  // Local state for edits
  const [editedConfigs, setEditedConfigs] = useState<Partial<Configs>>({});
  const [activeTab, setActiveTab] = useState<'telephony' | 'users' | 'ai' | 'other'>('telephony');

  // 2. React Query: Fetching with Zod Validation
  const { data: configs, isLoading, error: loadError } = useQuery<Configs, Error>({
    queryKey: ['configuracoes'],
    queryFn: async () => {
      const rawData = await apiFetchJson('/api/configuracoes');
      // Validate the payload using Zod. If the shape is wrong, it throws a predictable Error
      return ConfigsSchema.parse(rawData);
    },
  });

  // 3. React Query: Mutations
  const updateMutation = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => {
      await apiFetchJson('/api/configuracoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chave: key, valor: value }),
      });
    },
    onSuccess: () => {
      // Invalidate and refetch (silently, without toast spam)
      queryClient.invalidateQueries({ queryKey: ['configuracoes'] });
    },
  });

  const handleConfigChange = (key: string, value: string) => {
    setEditedConfigs((prev) => ({
      ...prev,
      [key]: {
        ...(configs?.[key] ?? { valor: '', descricao: '' }),
        ...(prev[key] ?? {}),
        valor: value,
      },
    }));
  };

  const saveConfig = (key: string, overrideValue?: string) => {
    const finalValue = overrideValue !== undefined 
      ? overrideValue 
      : (editedConfigs[key]?.valor ?? configs?.[key]?.valor ?? '');
      
    updateMutation.mutate({ key, value: finalValue });
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-400 theme-light:text-slate-700">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-2">Erro ao carregar configurações.</p>
          <p className="text-sm text-slate-400">{loadError instanceof Error ? loadError.message : 'Verifique a conexão.'}</p>
        </div>
      </div>
    );
  }

  // Merge the base configs from API with the local uncommitted edits
  const displayConfigs: Configs = { ...(configs ?? {}), ...(editedConfigs as Configs) };

  const navButtonClass = (isActive: boolean) =>
    `btn-nav px-4 py-3 text-sm font-semibold whitespace-nowrap md:whitespace-normal ${isActive ? 'btn-nav-active' : ''
    }`;

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Configurações"
        titleFirstWord="Configurações"
        titleRest="do Sistema"
        subtitle="Gerencie telefonia, usuários e parâmetros técnicos."
      />

      <ModuleInstructions
        storageKey="instructions:settings"
        steps={[
          'Use as abas para telefonia, usuários e parâmetros técnicos.',
          'Edite os campos necessários em cada aba.',
          'Salve para aplicar as mudanças.',
        ]}
      />

      <div className="flex flex-col gap-6 md:flex-row">
        <div className="rail-shell">
          <div className="surface-nav">
            <div className="mb-5">
              <p className="metric-label mb-2">Módulos</p>
              <p className="text-sm text-slate-400 theme-light:text-slate-700">Escolha a área técnica que deseja editar.</p>
            </div>

            <nav className="hide-scrollbar flex flex-row gap-2 overflow-x-auto pb-2 md:flex-col md:overflow-visible md:pb-0">
              <button onClick={() => setActiveTab('telephony')} className={navButtonClass(activeTab === 'telephony')}>
                Telefonia
              </button>

              <button onClick={() => setActiveTab('users')} className={navButtonClass(activeTab === 'users')}>
                Usuários
              </button>

            </nav>
          </div>
        </div>

        <div className="flex-1">
          {activeTab === 'telephony' ? (
            <TelephonySettings
              configs={displayConfigs}
              isSaving={updateMutation.isPending ? { [updateMutation.variables?.key || '']: true } : {}}
              saveStatus={updateMutation.isSuccess ? { [updateMutation.variables?.key || '']: 'success' } : {}}
              onConfigChange={handleConfigChange}
              onSaveConfig={saveConfig}
            />
          ) : null}

          {activeTab === 'users' ? <UserManagement /> : null}
        </div>
      </div>
    </div>
  );
}
