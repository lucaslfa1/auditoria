import { useState, useEffect } from 'react';
import { Loader2, Play, Save, CheckCircle2, Bot, ShieldCheck, Activity, AlertTriangle } from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

interface HuaweiConfig {
  huawei_ccid: string;
  huawei_vdn: string;
  huawei_app_key: string;
  huawei_ak: string;
  huawei_sk: string;
  huawei_horas_retroativas: string;
  huawei_cota_max_por_operador_mes: string;
  telefonia_cron_sync_ativa: string;
}

export function AutomationSettings() {
  const { showToast } = useToast();
  const [config, setConfig] = useState<HuaweiConfig>({
    huawei_ccid: '1',
    huawei_vdn: '170',
    huawei_app_key: '',
    huawei_ak: '',
    huawei_sk: '',
    huawei_horas_retroativas: '2',
    huawei_cota_max_por_operador_mes: '2',
    telefonia_cron_sync_ativa: 'true',
  });
  
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<any>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setIsLoading(true);
        const data = await apiFetchJson<Record<string, { valor: string }>>('/api/configuracoes');
        setConfig({
          huawei_ccid: data.huawei_ccid?.valor || '1',
          huawei_vdn: data.huawei_vdn?.valor || '170',
          huawei_app_key: data.huawei_app_key?.valor || '',
          huawei_ak: data.huawei_ak?.valor || '',
          huawei_sk: data.huawei_sk?.valor || '',
          huawei_horas_retroativas: data.huawei_horas_retroativas?.valor || '2',
          huawei_cota_max_por_operador_mes: data.huawei_cota_max_por_operador_mes?.valor || '2',
          telefonia_cron_sync_ativa: data.telefonia_cron_sync_ativa?.valor || 'true',
        });
      } catch {
        showToast({ variant: 'error', title: 'Erro', description: 'Falha ao carregar configurações da Huawei.' });
      } finally {
        setIsLoading(false);
      }
    };
    fetchConfig();
  }, [showToast]);

  const handleSaveConfig = async () => {
    try {
      setIsSaving(true);
      const keys = Object.keys(config) as Array<keyof HuaweiConfig>;
      for (const key of keys) {
        await apiFetchJson('/api/configuracoes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chave: key, valor: config[key] }),
        });
      }
      showToast({ variant: 'success', title: 'Cofre Atualizado', description: 'Credenciais da API salvas com segurança.' });
    } catch {
      showToast({ variant: 'error', title: 'Erro', description: 'Falha ao salvar as credenciais.' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleManualSync = async () => {
    if (!config.huawei_ak || !config.huawei_sk || !config.huawei_app_key || !config.huawei_ccid || !config.huawei_vdn) {
      showToast({ variant: 'error', title: 'Atenção', description: 'Preencha todos os parâmetros (AK, SK, App Key, CCID, VDN) antes de iniciar.' });
      return;
    }

    if (!window.confirm(`O robô irá procurar e auditar chamadas das últimas ${config.huawei_horas_retroativas} horas. Esse processo consome créditos da OpenAI. Deseja continuar?`)) return;

    try {
      setIsSyncing(true);
      setSyncResult(null);
      showToast({ variant: 'info', title: 'Robô Iniciado', description: 'Conectando à Huawei...' });

      const result = await apiFetchJson<any>('/api/automation/huawei-sync/manual', {        method: 'POST',
        timeoutMs: 300000 // 5 minutos de timeout para processos pesados
      });
      
      setSyncResult(result);
      showToast({ 
        variant: 'success', 
        title: 'Ciclo Concluído!', 
        description: result.message
      });
    } catch (err: any) {
      showToast({ variant: 'error', title: 'Falha na Automação', description: err.message || 'Erro de comunicação com a API.' });
    } finally {
      setIsSyncing(false);
    }
  };

  if (isLoading) return <div className="flex justify-center p-10"><Loader2 className="animate-spin text-primary-500 w-8 h-8" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="border-b border-white/10 pb-4 theme-light:border-slate-300">
        <h2 className="text-2xl font-black text-white theme-light:text-slate-900 flex items-center gap-2">
          <Bot className="text-primary-500" /> Automação de Telefonia (AICC)
        </h2>
        <p className="text-slate-400 text-sm mt-1 theme-light:text-slate-600">Conecte o sistema à Huawei para baixar e auditar ligações automaticamente.</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Painel Operacional */}
        <div className="space-y-6">
          <div className="panel-box bg-primary-500/5 border border-primary-500/20 rounded-2xl p-6 theme-light:bg-primary-50 theme-light:border-primary-200">
            <div className="flex items-start gap-3 mb-4">
              <Activity className="text-primary-500 shrink-0 mt-1" />
              <div>
                <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Coleta Ad-hoc (Manual)</h3>
                <p className="text-sm text-slate-400 mt-1 theme-light:text-slate-600">Força o robô a procurar novas ligações na nuvem neste exato momento, auditando e enviando para os supervisores.</p>
              </div>
            </div>

            <button 
              onClick={handleManualSync} 
              disabled={isSyncing || !config.huawei_ak || !config.huawei_ccid} 
              className={`w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 mt-4 transition-all ${
                isSyncing 
                ? 'bg-primary-500/50 text-white cursor-wait' 
                : 'bg-primary-500 hover:bg-primary-400 text-white shadow-lg hover:-translate-y-0.5'
              }`}
            >
              {isSyncing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-current" />}
              {isSyncing ? 'Coletando na Huawei (Aguarde...)' : 'Puxar Ligações Agora'}
            </button>

            {syncResult && (
              <div className={`mt-6 p-4 rounded-xl border animate-fade-in ${syncResult._is_running ? 'border-primary-500/30 bg-primary-500/10' : 'border-emerald-500/30 bg-emerald-500/10'}`}>
                <h4 className={`text-sm font-bold mb-2 flex items-center gap-2 ${syncResult._is_running ? 'text-primary-400' : 'text-emerald-400'}`}>
                  {syncResult._is_running ? <Loader2 className="w-4 h-4 animate-spin"/> : <CheckCircle2 className="w-4 h-4"/>} 
                  {syncResult._is_running ? 'Progresso da Execução' : 'Relatório de Execução'}
                </h4>
                
                {syncResult._is_running ? (
                  <div className="space-y-3 mt-3">
                    {syncResult.progress?.stage === 'downloading' && (
                      <div>
                        <div className="flex justify-between text-xs text-primary-300 mb-1">
                          <span>Sincronizando áudios da Huawei...</span>
                          <span>{syncResult.progress?.completed} / {syncResult.progress?.total} ({Math.round(((syncResult.progress?.completed || 0) / (syncResult.progress?.total || 1)) * 100)}%)</span>
                        </div>
                        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div className="h-full bg-primary-400 transition-all duration-500" style={{ width: `${Math.round(((syncResult.progress?.completed || 0) / (syncResult.progress?.total || 1)) * 100)}%` }} />
                        </div>
                      </div>
                    )}
                    
                    {syncResult.progress?.stage === 'classifying' && (
                      <div>
                        <div className="flex justify-between text-xs text-amber-300 mb-1">
                          <span>IA Auditando ligações...</span>
                          <span>{syncResult.progress?.completed} / {syncResult.progress?.total} ({Math.round(((syncResult.progress?.completed || 0) / (syncResult.progress?.total || 1)) * 100)}%)</span>
                        </div>
                        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-400 transition-all duration-500" style={{ width: `${Math.round(((syncResult.progress?.completed || 0) / (syncResult.progress?.total || 1)) * 100)}%` }} />
                        </div>
                      </div>
                    )}

                    {!syncResult.progress?.stage && (
                      <p className="text-xs text-primary-300/80 animate-pulse">Iniciando conexão e descobrindo chamadas na nuvem...</p>
                    )}
                  </div>
                ) : (
                  <ul className="text-sm text-emerald-200/80 space-y-1 theme-light:text-emerald-800">
                    <li>• Novos áudios baixados do OBS: <strong>{syncResult.baixadas ?? syncResult.novas_ligacoes_baixadas ?? 0}</strong></li>
                    <li>• Auditorias realizadas pela IA: <strong>{syncResult.classificadas ?? syncResult.auditorias_realizadas ?? 0}</strong></li>
                    <li>• Ignoradas por cota: <strong>{syncResult.ignoradas_cota_mensal_pre_download ?? 0}</strong></li>
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/10 flex gap-3 text-amber-200/80 text-sm theme-light:bg-amber-50 theme-light:text-amber-800 theme-light:border-amber-200">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 theme-light:text-amber-600" />
            <p>
              <strong>Roteamento Inteligente:</strong> O robô filtrará apenas as chamadas dos operadores que estiverem marcados como <strong>"ATIVO"</strong> e com o campo <strong>ID Huawei</strong> preenchido na aba de Operadores.
            </p>
          </div>
        </div>

        {/* Cofre de Chaves API */}
        <div className="panel-box bg-slate-900 border border-white/10 rounded-2xl p-6 theme-light:bg-white theme-light:border-slate-300">
          <div className="flex items-center gap-2 mb-6 border-b border-white/10 pb-4 theme-light:border-slate-300">
            <ShieldCheck className="text-emerald-400 w-6 h-6" />
            <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Credenciais API Fabric (Cofre)</h3>
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-xs font-semibold text-slate-400 uppercase">Call Center ID (ccId)</span>
                <input type="text" value={config.huawei_ccid} onChange={e => setConfig({...config, huawei_ccid: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300" />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-400 uppercase">VDN / VCC ID</span>
                <input type="text" value={config.huawei_vdn} onChange={e => setConfig({...config, huawei_vdn: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300" />
              </label>
            </div>

            <label className="block">
              <span className="text-xs font-semibold text-slate-400 uppercase">App Key (Identificador)</span>
              <input type="password" value={config.huawei_app_key} onChange={e => setConfig({...config, huawei_app_key: e.target.value})} placeholder="Ex: 0b62e4a8..." className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300" />
            </label>

            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-xs font-semibold text-slate-400 uppercase">Access Key (AK)</span>
                <input type="password" value={config.huawei_ak} onChange={e => setConfig({...config, huawei_ak: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300" />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-400 uppercase">Secret Key (SK)</span>
                <input type="password" value={config.huawei_sk} onChange={e => setConfig({...config, huawei_sk: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300" />
              </label>
            </div>
            
            <label className="block pt-2">
              <span className="text-xs font-semibold text-slate-400 uppercase flex justify-between">
                Período Retroativo da Busca 
                <span className="text-[10px] text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-500/20">Custo de API</span>
              </span>
              <select value={config.huawei_horas_retroativas} onChange={e => setConfig({...config, huawei_horas_retroativas: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300">
                <option value="1">Última 1 hora</option>
                <option value="2">Últimas 2 horas</option>
                <option value="6">Últimas 6 horas</option>
                <option value="12">Últimas 12 horas</option>
              </select>
            </label>

            <label className="block pt-2">
              <span className="text-xs font-semibold text-slate-400 uppercase flex justify-between">
                Limite de Auditorias Mensais (Por Operador)
                <span className="text-[10px] text-primary-400 bg-primary-400/10 px-2 py-0.5 rounded border border-primary-500/20">Cota</span>
              </span>
              <select value={config.huawei_cota_max_por_operador_mes} onChange={e => setConfig({...config, huawei_cota_max_por_operador_mes: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300">
                <option value="1">1 auditoria / mês</option>
                <option value="2">2 auditorias / mês</option>
                <option value="3">3 auditorias / mês</option>
                <option value="4">4 auditorias / mês</option>
                <option value="5">5 auditorias / mês</option>
                <option value="10">10 auditorias / mês</option>
              </select>
            </label>

            <label className="block pt-2">
              <span className="text-xs font-semibold text-slate-400 uppercase flex justify-between">
                Sincronização Contínua em Segundo Plano
                <span className="text-[10px] text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded border border-emerald-500/20">Cron</span>
              </span>
              <select value={config.telefonia_cron_sync_ativa} onChange={e => setConfig({...config, telefonia_cron_sync_ativa: e.target.value})} className="w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300">
                <option value="true">Ligada (Baixar áudios para triagem)</option>
                <option value="false">Desligada</option>
              </select>
              <p className="text-xs text-slate-500 mt-2">
                Define se o sistema deve ficar buscando ligações periodicamente para preencher a aba "Ligações" (Triagem) quando o Motor de Automação Híbrida estiver pausado.
              </p>
            </label>
          </div>

          <div className="mt-6 flex justify-end">
            <button onClick={handleSaveConfig} disabled={isSaving} className="btn-primary px-6 py-2.5 rounded-xl font-semibold flex items-center gap-2 text-sm disabled:opacity-50">
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Salvar Credenciais
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
