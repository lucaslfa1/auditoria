import React from 'react';
import { MonitorPlay, KeyRound, Loader2, Save } from 'lucide-react';
import { HuaweiCredentialsCard } from '../../telefonia/components/HuaweiCredentialsCard';
import { useTelefoniaSync } from '../../telefonia/hooks/useTelefoniaSync';

interface ConfigItem {
  valor: string;
  descricao: string;
}

interface TelephonySettingsProps {
  configs: Record<string, ConfigItem>;
  isSaving: Record<string, boolean>;
  saveStatus: Record<string, 'success' | 'error' | null>;
  onConfigChange: (key: string, value: string) => void;
  onSaveConfig: (key: string) => void;
}

export function TelephonySettings({ 
  configs, 
  isSaving, 
  saveStatus, 
  onConfigChange, 
  onSaveConfig 
}: TelephonySettingsProps) {
  const { config: huaweiConfig, status: huaweiStatus } = useTelefoniaSync();
  
  const renderField = (key: string, label: string, type: 'text' | 'password', icon: React.ReactNode) => {
    const config = configs[key];
    if (!config) return null;

    return (
      <div className="panel-box-lg mb-6 theme-light:bg-slate-200 theme-light:border-slate-300">
        <div className="flex items-start gap-4 mb-4">
          <div className="p-3 bg-primary-500/10 rounded-xl text-primary-400 border border-primary-500/20">
            {icon}
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-white theme-light:text-slate-900 mb-1">{label}</h3>
            <p className="text-sm text-slate-400 theme-light:text-slate-600 mb-4">{config.descricao}</p>
            
            <div className="relative">
              <input
                type={type}
                value={config.valor}
                onChange={(e) => onConfigChange(key, e.target.value)}
                className="w-full p-4 glass-input rounded-xl outline-none"
                placeholder={`Insira ${label.toLowerCase()}...`}
              />
            </div>

            <div className="mt-4 flex items-center justify-end gap-3">
              {saveStatus[key] === 'success' && (
                <span className="text-sm text-green-400 font-medium">Salvo com sucesso!</span>
              )}
              {saveStatus[key] === 'error' && (
                <span className="text-sm text-red-400 font-medium">Erro ao salvar.</span>
              )}
              <button
                onClick={() => onSaveConfig(key)}
                disabled={isSaving[key]}
                className={`btn-primary px-6 py-2.5 rounded-lg font-semibold flex items-center gap-2 ${
                  isSaving[key] ? 'opacity-70 cursor-not-allowed' : ''
                }`}
              >
                {isSaving[key] ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Salvar
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-2 animate-fade-in">
      <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4 theme-light:border-slate-300">
        <div>
          <h2 className="text-2xl font-black text-white theme-light:text-slate-900">Telefonia</h2>
          <p className="text-slate-400 text-sm mt-1">Configure o acesso ao sistema de telefonia usado nas rotinas automáticas.</p>
        </div>
        
        {configs['robo_habilitado'] && (
          <div className="flex items-center gap-3 bg-slate-900/40 p-2 px-4 rounded-full border border-white/5 theme-light:bg-white theme-light:border-slate-300">
            <span className={`text-xs font-bold uppercase tracking-wider ${configs['robo_habilitado'].valor === 'true' ? 'text-emerald-400' : 'text-slate-500'}`}>
              {configs['robo_habilitado'].valor === 'true' ? 'ATIVADO' : 'DESATIVADO'}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={configs['robo_habilitado'].valor === 'true'}
              onClick={() => {
                const newValue = configs['robo_habilitado'].valor === 'true' ? 'false' : 'true';
                onConfigChange('robo_habilitado', newValue);
                onSaveConfig('robo_habilitado');
              }}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 ${
                configs['robo_habilitado'].valor === 'true' ? 'bg-emerald-500' : 'bg-slate-700'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-300 ${
                configs['robo_habilitado'].valor === 'true' ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>
        )}
      </div>

      {renderField('rpa_url_login', 'Endereço do sistema de telefonia', 'text', <MonitorPlay className="w-6 h-6" />)}
      {renderField('rpa_usuario', 'Usuário de acesso', 'text', <KeyRound className="w-6 h-6" />)}
      {renderField('rpa_senha', 'Senha de acesso', 'password', <KeyRound className="w-6 h-6" />)}

      <div className="mt-8">
        <HuaweiCredentialsCard config={huaweiConfig} status={huaweiStatus} />
      </div>
    </div>
  );
}
