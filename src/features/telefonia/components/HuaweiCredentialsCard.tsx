import { ShieldCheck, Lock } from 'lucide-react';

import type { HuaweiConfig, SyncStatus } from '../hooks/useTelefoniaSync';

interface HuaweiCredentialsCardProps {
  config: HuaweiConfig;
  status: SyncStatus | null;
}

const INPUT_CLASS =
  'w-full mt-1 p-3 rounded-xl bg-slate-800 border border-white/10 text-white outline-none focus:border-primary-500/50 text-sm '
  + 'theme-light:bg-slate-100 theme-light:text-slate-900 theme-light:border-slate-300 disabled:opacity-60 disabled:cursor-not-allowed';

const LABEL_CLASS = 'text-xs font-semibold text-slate-400 uppercase flex items-center gap-1.5';

export function HuaweiCredentialsCard({ config, status }: HuaweiCredentialsCardProps) {
  const isFromEnv = (key: string) => status?.credentials?.fields?.[key]?.from_env || false;

  const renderLabel = (label: string, key: string) => (
    <span className={LABEL_CLASS}>
      {label}
      {isFromEnv(key) && (
        <span className="flex items-center gap-1 text-[10px] text-emerald-400 normal-case bg-emerald-400/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
          <Lock className="w-2.5 h-2.5" /> Configurado via Servidor
        </span>
      )}
    </span>
  );

  return (
    <div className="panel-box bg-slate-900 border border-white/10 rounded-2xl p-6 theme-light:bg-white theme-light:border-slate-300">
      <div className="flex items-center gap-2 mb-6 border-b border-white/10 pb-4 theme-light:border-slate-300">
        <ShieldCheck className="text-emerald-400 w-6 h-6" />
        <div>
          <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Cofre de credenciais</h3>
          <p className="text-xs text-slate-400 theme-light:text-slate-600 mt-0.5">
            Chaves API Fabric (Huawei). Valores em ambiente (ENV) têm prioridade e são protegidos.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            {renderLabel('Call Center ID (ccId)', 'huawei_ccid')}
            <input
              type="text"
              value={isFromEnv('huawei_ccid') ? '********' : config.huawei_ccid}
              disabled={true}
              className={INPUT_CLASS}
            />
          </label>

          <label className="block">
            {renderLabel('VDN / VCC ID', 'huawei_vdn')}
            <input
              type="text"
              value={isFromEnv('huawei_vdn') ? '********' : config.huawei_vdn}
              disabled={true}
              className={INPUT_CLASS}
            />
          </label>
        </div>

        <label className="block">
          {renderLabel('App Key', 'huawei_app_key')}
          <input
            type="password"
            value={isFromEnv('huawei_app_key') ? '********' : config.huawei_app_key}
            disabled={true}
            placeholder="Ex: 0b62e4a8..."
            className={INPUT_CLASS}
          />
        </label>

        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            {renderLabel('Access Key (AK)', 'huawei_ak')}
            <input
              type="password"
              value={isFromEnv('huawei_ak') ? '********' : config.huawei_ak}
              disabled={true}
              className={INPUT_CLASS}
            />
          </label>

          <label className="block">
            {renderLabel('Secret Key (SK)', 'huawei_sk')}
            <input
              type="password"
              value={isFromEnv('huawei_sk') ? '********' : config.huawei_sk}
              disabled={true}
              className={INPUT_CLASS}
            />
          </label>
        </div>

      </div>
    </div>
  );
}
