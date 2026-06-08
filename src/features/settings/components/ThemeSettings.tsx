import { Check, LayoutTemplate, Loader2, Save } from 'lucide-react';

interface ConfigItem {
  valor: string;
  descricao: string;
}

type ThemePreset = 'corporativo' | 'opentech' | 'nstech';

interface ThemeSettingsProps {
  configs: Record<string, ConfigItem>;
  isSaving: Record<string, boolean>;
  saveStatus: Record<string, 'success' | 'error' | null>;
  activeThemePreset: ThemePreset;
  onConfigChange: (key: string, value: string) => void;
  onSaveConfig: (key: string) => void;
}

const THEME_OPTIONS: Array<{
  id: ThemePreset;
  label: string;
  description: string;
  accentClassName: string;
  surfaceClassName: string;
}> = [
  {
    id: 'corporativo',
    label: 'Corporativo',
    description: 'Equilibrado e institucional para uso geral.',
    accentClassName: 'from-primary-500 to-primary-600',
    surfaceClassName: 'bg-slate-900/70 theme-light:bg-white/80',
  },
  {
    id: 'opentech',
    label: 'OpenTech',
    description: 'Claro, limpo e com contraste mais suave.',
    accentClassName: 'from-cyan-500 to-sky-600',
    surfaceClassName: 'bg-cyan-950/70 theme-light:bg-cyan-50/90',
  },
  {
    id: 'nstech',
    label: 'nstech Blue',
    description: 'Azul institucional mais marcado, sem perder sobriedade.',
    accentClassName: 'from-blue-500 to-indigo-600',
    surfaceClassName: 'bg-blue-950/75 theme-light:bg-blue-50/85',
  },
];

export function ThemeSettings({
  configs,
  isSaving,
  saveStatus,
  activeThemePreset,
  onConfigChange,
  onSaveConfig,
}: ThemeSettingsProps) {
  const config = configs.tema_visual;

  if (!config) {
    return (
      <div className="panel-box-lg theme-light:bg-slate-200 theme-light:border-slate-300">
        <h2 className="text-2xl font-black text-white theme-light:text-slate-900">Tema</h2>
        <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-600">
          A configuração de tema ainda não está disponível neste ambiente.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between border-b border-white/10 pb-4 theme-light:border-slate-300">
        <div>
          <h2 className="text-2xl font-black text-white theme-light:text-slate-900">Tema</h2>
          <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-600">
            Escolha o visual padrão da interface. O alternador no topo continua controlando claro e escuro.
          </p>
        </div>
        <div className="hidden rounded-full border border-white/10 bg-slate-900/40 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 theme-light:border-slate-300 theme-light:bg-white md:block">
          {activeThemePreset}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {THEME_OPTIONS.map((option) => {
          const isSelected = config.valor === option.id;
          const isApplied = activeThemePreset === option.id;

          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onConfigChange('tema_visual', option.id)}
              className={`glass-card rounded-2xl border p-5 text-left transition-all duration-200 ${
                isSelected ? 'border-primary-500/40 shadow-[0_12px_30px_rgba(15,23,42,0.18)]' : 'border-white/10'
              }`}
            >
              <div className={`mb-4 h-28 rounded-2xl border border-white/10 p-4 ${option.surfaceClassName}`}>
                <div className="flex h-full flex-col justify-between">
                  <div className={`h-3 w-20 rounded-full bg-gradient-to-r ${option.accentClassName}`} />
                  <div className="grid grid-cols-[1.4fr_0.8fr] gap-3">
                    <div className="rounded-xl bg-white/10 p-3 theme-light:bg-white/70">
                      <div className="mb-2 h-2.5 w-16 rounded-full bg-white/35 theme-light:bg-slate-300" />
                      <div className="h-2.5 w-24 rounded-full bg-white/20 theme-light:bg-slate-200" />
                    </div>
                    <div className="rounded-xl bg-black/20 p-3 theme-light:bg-slate-100">
                      <div className={`mb-2 h-2.5 w-10 rounded-full bg-gradient-to-r ${option.accentClassName}`} />
                      <div className="h-2.5 w-14 rounded-full bg-white/20 theme-light:bg-slate-200" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <LayoutTemplate className="h-4 w-4 text-primary-400" />
                    <h3 className="text-lg font-bold text-white theme-light:text-slate-900">{option.label}</h3>
                  </div>
                  <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-600">{option.description}</p>
                </div>
                {(isSelected || isApplied) && (
                  <span className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${
                    isSelected
                      ? 'border-primary-500/30 bg-primary-500/10 text-primary-400'
                      : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
                  }`}>
                    <Check className="h-4 w-4" />
                  </span>
                )}
              </div>

              <div className="mt-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em]">
                {isSelected ? (
                  <span className="rounded-full border border-primary-500/30 bg-primary-500/10 px-3 py-1 text-primary-400">
                    Selecionado
                  </span>
                ) : null}
                {isApplied ? (
                  <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-emerald-400">
                    Aplicado
                  </span>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      <div className="panel-box-lg theme-light:bg-slate-200 theme-light:border-slate-300">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Aplicar tema padrão</h3>
            <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-600">
              Esse tema define o visual padrão da interface. O modo claro ou escuro continua sendo alternado no topo.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {saveStatus.tema_visual === 'success' && (
              <span className="text-sm font-medium text-green-400">Tema salvo com sucesso.</span>
            )}
            {saveStatus.tema_visual === 'error' && (
              <span className="text-sm font-medium text-red-400">Erro ao salvar o tema.</span>
            )}
            <button
              type="button"
              onClick={() => onSaveConfig('tema_visual')}
              disabled={isSaving.tema_visual}
              className={`btn-primary inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold ${
                isSaving.tema_visual ? 'cursor-not-allowed opacity-70' : ''
              }`}
            >
              {isSaving.tema_visual ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Salvar tema
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
