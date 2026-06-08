import { OperatorAutocompleteFields } from '../../../shared/components/OperatorAutocompleteFields';
import type { AuditAlert, AuditSector } from '../types/audit';

interface AuditSetupStepProps {
  auditType: 'audio' | 'pdf';
  sectors: AuditSector[];
  selectedSector: AuditSector | null;
  selectedAlert: AuditAlert | null;
  operatorName: string;
  operatorId: string;
  theme: 'dark' | 'light';
  onAuditTypeChange: (nextType: 'audio' | 'pdf') => void;
  onSectorChange: (sectorId: string) => void;
  onAlertChange: (alertId: string) => void;
  onOperatorNameChange: (value: string) => void;
  onOperatorIdChange: (value: string) => void;
  audioDate: string;
  onAudioDateChange: (value: string) => void;
  onContinue?: () => void;
  showContinueButton?: boolean;
  disabled?: boolean;
  className?: string;
}

const DOCUMENT_AUDIT_SECTOR_IDS = new Set([
  'cadastro',
  'logistica_unilever',
  'logistica',
  'mondelez',
  'checklist',
  'receptivo',
]);

const DOCUMENT_ONLY_SECTOR_IDS = new Set([
  'checklist',
  'receptivo',
]);

const isSectorAvailableForAuditType = (
  sector: AuditSector,
  auditType: 'audio' | 'pdf',
) => {
  if (!sector.alerts.length) {
    return false;
  }

  if (auditType === 'pdf') {
    return DOCUMENT_AUDIT_SECTOR_IDS.has(sector.id);
  }

  return !DOCUMENT_ONLY_SECTOR_IDS.has(sector.id);
};

export function AuditSetupStep({
  auditType,
  sectors,
  selectedSector,
  selectedAlert,
  operatorName,
  operatorId,
  theme,
  onAuditTypeChange,
  onSectorChange,
  onAlertChange,
  onOperatorNameChange,
  onOperatorIdChange,
  audioDate,
  onAudioDateChange,
  onContinue,
  showContinueButton = true,
  disabled = false,
  className = '',
}: AuditSetupStepProps) {
  const selectOptionClass = theme === 'dark' ? 'bg-slate-900 text-slate-100' : 'bg-white text-slate-900';
  const selectPlaceholderOptionClass = theme === 'dark' ? 'bg-slate-900 text-slate-500' : 'bg-white text-slate-500';

  return (
    <div
      className={`glass-panel rounded-2xl p-6 md:p-8 theme-light:bg-slate-200 theme-light:border-slate-300 ${className}`.trim()}
    >
      <div className="text-center mb-8 md:mb-10">
        <p className="text-[11px] uppercase tracking-[0.18em] text-primary-400 font-semibold mb-3">
          Configuração inicial
        </p>
        <h3 className="section-title-lg mb-3 md:text-3xl">
          Defina o contexto
        </h3>
        <p className="text-slate-400 text-base theme-light:text-slate-700 max-w-2xl mx-auto">
          Selecione a modalidade, o setor, o alerta e os dados do operador antes de enviar o arquivo.
        </p>
      </div>

      <div className="stagger-group">
        <div className="space-y-7 stagger-item">
          <div className="space-y-4">
            <label className="text-[15px] font-semibold text-slate-300 ml-1">Tipo de auditoria</label>
            <div className="grid sm:grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => onAuditTypeChange('audio')}
                disabled={disabled}
                className={`rounded-2xl p-4 border text-left transition-all hover-lift ${disabled ? 'opacity-60 cursor-not-allowed' : ''} ${auditType === 'audio'
                  ? 'border-primary-400 bg-primary-500/10 shadow-[0_12px_28px_rgba(233,90,31,0.12)]'
                  : 'border-white/10 bg-slate-900/40 hover:border-primary-500/40 hover:bg-slate-900/70'
                  }`}
              >
                <div className="font-bold text-base text-white mb-2">Áudio</div>
                <p className="text-sm text-slate-400 leading-relaxed">Ligações com transcrição e avaliação do atendimento.</p>
              </button>
              <button
                type="button"
                onClick={() => onAuditTypeChange('pdf')}
                disabled={disabled}
                className={`rounded-2xl p-4 border text-left transition-all hover-lift ${disabled ? 'opacity-60 cursor-not-allowed' : ''} ${auditType === 'pdf'
                  ? 'border-primary-400 bg-primary-500/10 shadow-[0_12px_28px_rgba(233,90,31,0.12)]'
                  : 'border-white/10 bg-slate-900/40 hover:border-primary-500/40 hover:bg-slate-900/70'
                  }`}
              >
                <div className="font-bold text-base text-white mb-2">Documento</div>
                <p className="text-sm text-slate-400 leading-relaxed">PDFs de cadastro, logística, Mondelez, checklist e receptivo.</p>
              </button>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <label className="text-[15px] font-semibold text-slate-300 ml-1">Setor</label>
              <div className="relative group">
                <select
                  className="w-full p-3.5 pl-4 glass-input rounded-xl appearance-none cursor-pointer outline-none text-[15px] disabled:opacity-60 disabled:cursor-not-allowed"
                  onChange={(e) => onSectorChange(e.target.value)}
                  value={selectedSector?.id || ''}
                  disabled={disabled}
                >
                  <option value="" className={selectPlaceholderOptionClass}>Selecione o setor</option>
                  {sectors
                    .filter((sector) => isSectorAvailableForAuditType(sector, auditType))
                    .map((sector) => (
                      <option key={sector.id} value={sector.id} className={selectOptionClass}>
                        {sector.label}
                      </option>
                    ))}
                </select>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500 group-hover:text-primary-400 transition-colors">
                  <span className="text-base">v</span>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-[15px] font-semibold text-slate-300 ml-1">Alerta</label>
              <div className="relative group">
                <select
                  className="w-full p-3.5 pl-4 glass-input rounded-xl appearance-none cursor-pointer outline-none disabled:opacity-60 disabled:cursor-not-allowed text-[15px]"
                  disabled={disabled || !selectedSector}
                  onChange={(e) => onAlertChange(e.target.value)}
                  value={selectedAlert?.id || ''}
                >
                  <option value="" className={selectPlaceholderOptionClass}>Selecione o alerta</option>
                  {selectedSector?.alerts.map((alert) => (
                    <option key={alert.id} value={alert.id} className={selectOptionClass}>
                      {alert.label}
                    </option>
                  ))}
                </select>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500 group-hover:text-primary-400 transition-colors">
                  <span className="text-base">v</span>
                </div>
              </div>
            </div>
          </div>

          <div className={disabled ? 'opacity-60 pointer-events-none' : ''}>
            <OperatorAutocompleteFields
              sectorId={selectedSector?.id}
              operatorName={operatorName}
              operatorId={operatorId}
              onOperatorNameChange={onOperatorNameChange}
              onOperatorIdChange={onOperatorIdChange}
              theme={theme}
            />
          </div>

          <div className="space-y-3">
            <label className="text-[15px] font-semibold text-slate-300 ml-1">
              Data do áudio <span className="text-xs text-slate-500 font-normal">(opcional)</span>
            </label>
            <input
              type="date"
              value={audioDate}
              onChange={(e) => onAudioDateChange(e.target.value)}
              disabled={disabled}
              className="w-full p-3.5 pl-4 glass-input rounded-xl appearance-none outline-none text-[15px] disabled:opacity-60 disabled:cursor-not-allowed theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
            />
          </div>
        </div>
      </div>

      {showContinueButton ? (
        <div className="mt-10 md:mt-12 flex justify-end">
          <button
            onClick={onContinue}
            disabled={!selectedAlert}
            className="btn-primary w-full sm:w-auto px-8 md:px-9 py-3.5 text-base font-semibold"
          >
            Continuar
          </button>
        </div>
      ) : null}
    </div>
  );
}
