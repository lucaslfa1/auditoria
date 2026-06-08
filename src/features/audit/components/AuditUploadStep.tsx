import { useState, useEffect } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import { AlertTriangle, Loader2, Upload, X } from 'lucide-react';

interface AuditUploadStepProps {
  auditType: 'audio' | 'pdf';
  file: File | null;
  isDragging: boolean;
  isProcessing: boolean;
  selectedSectorLabel?: string | null;
  selectedAlertLabel?: string | null;
  stepError?: string | null;
  quotaExceeded?: string | null;
  onForceProcess?: () => Promise<boolean>;
  onBack?: () => void;
  onDragOver: (event: DragEvent<HTMLLabelElement>) => void;
  onDragLeave: (event: DragEvent<HTMLLabelElement>) => void;
  onDrop: (event: DragEvent<HTMLLabelElement>) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onClearFile: () => void;
  onProcess: () => void;
  showBackButton?: boolean;
  className?: string;
}

export function AuditUploadStep({
  auditType,
  file,
  isDragging,
  isProcessing,
  selectedSectorLabel,
  selectedAlertLabel,
  stepError,
  quotaExceeded,
  onForceProcess,
  onBack,
  onDragOver,
  onDragLeave,
  onDrop,
  onFileChange,
  onClearFile,
  onProcess,
  showBackButton = true,
  className = '',
}: AuditUploadStepProps) {
  const [isForcing, setIsForcing] = useState(false);

  const handleForce = async () => {
    if (!onForceProcess) return;
    setIsForcing(true);
    try {
      await onForceProcess();
    } finally {
      setIsForcing(false);
    }
  };

  // Prevenir que o navegador abra o arquivo se solto fora da drop zone
  useEffect(() => {
    const prevent = (e: Event) => e.preventDefault();
    window.addEventListener('dragover', prevent);
    window.addEventListener('drop', prevent);
    return () => {
      window.removeEventListener('dragover', prevent);
      window.removeEventListener('drop', prevent);
    };
  }, []);

  return (
    <div className={`glass-panel rounded-2xl p-6 md:p-8 max-w-3xl mx-auto ${className}`.trim()}>
      {showBackButton ? (
        <button
          type="button"
          onClick={onBack}
          className="btn-ghost mb-7 px-4 py-2 text-[15px] font-medium"
        >
          Voltar
        </button>
      ) : null}

      <div className="text-center mb-10">
        <h2 className="section-title-lg mb-3 md:text-3xl">
          Enviar arquivo
        </h2>
        <p className="text-slate-400 text-base">
          Envie o {auditType === 'audio' ? 'áudio' : 'documento'} para iniciar a auditoria.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
          <span className="px-4 py-1.5 rounded-xl text-sm border border-white/10 bg-slate-900/50 text-slate-300">
            Setor: {selectedSectorLabel || 'não informado'}
          </span>
          <span className="px-4 py-1.5 rounded-xl text-sm border border-white/10 bg-slate-900/50 text-slate-300">
            Alerta: {selectedAlertLabel || 'não informado'}
          </span>
        </div>
      </div>

      {!file ? (
        <label
          tabIndex={0}
          role="button"
          onKeyDown={(e) => {
             if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                const input = e.currentTarget.querySelector('input[type="file"]') as HTMLInputElement;
                if (input) input.click();
             }
          }}
          className={`block w-full border-2 border-dashed rounded-[1.75rem] p-9 md:p-11 text-center transition-all cursor-pointer group relative overflow-hidden focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none ${
            isDragging
              ? 'border-primary-400 bg-primary-500/10 scale-[1.01]'
              : 'border-slate-700 hover:border-primary-500 hover:bg-primary-500/5'
          }`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        >
          <input
            type="file"
            accept={auditType === 'audio' ? 'audio/*' : 'application/pdf'}
            onChange={(e) => {
              onFileChange(e);
              e.target.value = '';
            }}
            className="hidden"
          />
          <div className={`absolute inset-0 bg-gradient-to-b from-transparent to-primary-500/5 transition-opacity ${isDragging ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`} />

          <div
            className={`w-24 h-24 bg-slate-800/50 rounded-full flex items-center justify-center mx-auto mb-6 transition-transform border border-white/10 ${
              isDragging ? 'scale-110 border-primary-400' : 'group-hover:scale-110'
            }`}
          >
            <Upload className={`w-12 h-12 ${isDragging ? 'text-primary-300' : 'text-primary-400'}`} />
          </div>
          <h3 className="section-title-lg mb-3 md:text-2xl">
            {isDragging ? 'Solte o arquivo aqui' : 'Clique para selecionar ou arraste o arquivo'}
          </h3>
          <p className="text-slate-500 text-base">
            {auditType === 'audio' ? 'MP3, WAV, M4A, OGG ou WEBM • máx. 20 MB' : 'PDF • máx. 20 MB'}
          </p>
        </label>
      ) : (
        <div className="space-y-8">
          <div className="glass-card hover-lift rounded-2xl p-5 flex items-center justify-between border border-primary-500/30 bg-primary-500/5">
            <div>
              <p className="section-title-lg">{file.name}</p>
              <p className="text-base text-slate-400 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
            <button
              type="button"
              onClick={onClearFile}
              aria-label="Remover arquivo selecionado"
              title="Remover arquivo"
              className="btn-icon-danger !h-11 !w-11 !rounded-xl"
            >
              <X className="w-7 h-7" />
            </button>
          </div>

          <button
            onClick={onProcess}
            disabled={isProcessing}
            className="btn-primary w-full py-4 text-base font-semibold"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-6 h-6 animate-spin" />
                Processando análise...
              </>
            ) : (
              'Iniciar auditoria'
            )}
          </button>
        </div>
      )}

      {stepError ? (
        <div className="mt-8 p-4 bg-red-500/10 text-red-400 rounded-xl border border-red-500/20 animate-fade-in text-sm md:text-base">
          {stepError}
        </div>
      ) : null}

      {quotaExceeded && !stepError ? (
        <div className="mt-8 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 animate-fade-in">
          <div className="flex items-start gap-3 mb-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-amber-300 text-sm leading-relaxed">{quotaExceeded}</p>
          </div>
          {onForceProcess ? (
            <button
              type="button"
              onClick={handleForce}
              disabled={isForcing || isProcessing}
              className="w-full mt-1 py-3 px-4 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 font-semibold text-sm transition-all flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isForcing || isProcessing ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Processando...</>
              ) : (
                'Enviar mesmo assim'
              )}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
