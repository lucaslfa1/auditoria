import type { RefObject } from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import type { TranscriptionSegment } from '../types/audit';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';
import { ReadOnlyTranscription } from '../../../shared/components/ReadOnlyTranscription';

interface AuditTranscriptPanelProps {
  auditType: 'audio' | 'pdf';
  audioUrl: string | null;
  audioSourceType?: string;
  fileName?: string;
  audioRef: RefObject<HTMLAudioElement | null>;
  transcription: TranscriptionSegment[];
  isEditingTranscription: boolean;
  tempTranscription: TranscriptionSegment[];
  isProcessing: boolean;
  onEditTranscription: () => void;
  onCancelEditing: () => void;
  onSaveTranscription: () => void;
  onUpdateTranscriptionSegment: (index: number, field: keyof TranscriptionSegment, value: string) => void;
  onAddTranscriptionSegment?: (afterIndex: number) => void;
  onRemoveTranscriptionSegment?: (index: number) => void;
  onSeekAudio: (timeStr: string) => void;
}

export function AuditTranscriptPanel({
  auditType,
  audioUrl,
  fileName,
  audioRef,
  transcription,
  isEditingTranscription,
  tempTranscription,
  isProcessing,
  onEditTranscription,
  onCancelEditing,
  onSaveTranscription,
  onUpdateTranscriptionSegment,
  onAddTranscriptionSegment,
  onRemoveTranscriptionSegment,
  onSeekAudio,
}: AuditTranscriptPanelProps) {
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="glass-panel p-6 rounded-2xl">
        <h3 className="section-title-lg mb-5">
          {auditType === 'audio' ? 'Áudio enviado' : 'Documento enviado'}
        </h3>
        {auditType === 'audio' && audioUrl ? (
          <AuthenticatedAudioPlayer
            className="w-full mb-5 custom-audio"
            audioUrl={audioUrl}
            ref={audioRef}
          />
        ) : null}
        {auditType === 'pdf' ? (
          <div className="w-full h-44 bg-slate-900/50 rounded-xl flex flex-col items-center justify-center border border-white/5 text-slate-500 mb-5">
            <p className="text-base">Documento processado</p>
            <p className="text-sm opacity-70 mt-1">{fileName}</p>
          </div>
        ) : null}
        <div className="text-sm text-slate-500 text-center">
          {auditType === 'audio' ? 'Clique em um trecho da transcrição para ouvir o áudio correspondente.' : 'Conteúdo extraído do documento enviado.'}
        </div>
      </div>

      <div className="glass-panel custom-scrollbar flex max-h-[560px] flex-col overflow-y-auto rounded-2xl p-6">
        <div className="sticky top-0 z-10 mb-5 flex flex-col gap-3 rounded-xl bg-slate-900/95 p-3 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
          <h3 className="section-title-lg">
            {auditType === 'audio' ? 'Transcrição da chamada' : 'Texto extraído'}
          </h3>
          {!isEditingTranscription ? (
            <button
              onClick={onEditTranscription}
              className="btn-accent px-3.5 py-2 text-sm"
            >
              Editar Transcrição
            </button>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                onClick={onCancelEditing}
                className="btn-ghost px-3.5 py-2 text-sm"
              >
                Cancelar
              </button>
              <button
                onClick={onSaveTranscription}
                disabled={isProcessing}
                className="btn-success px-3.5 py-2 text-sm"
              >
                {isProcessing ? <Loader2 size={14} className="animate-spin" /> : null}
                {isProcessing ? 'Reprocessando...' : 'Salvar e reprocessar'}
              </button>
            </div>
          )}
        </div>

        <div className="space-y-3 flex-1">
          {!isEditingTranscription ? (
            <div className="pt-2">
              <ReadOnlyTranscription
                transcription={transcription}
                onSeekAudio={auditType === 'audio' ? onSeekAudio : undefined}
                maxHeightClass=""
              />
            </div>
          ) : (
            tempTranscription.map((segment, idx) => (
              <div key={`seg-${idx}-${segment.start}-${segment.end}`}>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10 space-y-3">
                  {auditType === 'audio' ? (
                    <div className="flex gap-2 items-center">
                      <input
                        type="text"
                        value={segment.start}
                        onChange={(e) => onUpdateTranscriptionSegment(idx, 'start', e.target.value)}
                        className="w-24 bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm font-mono text-primary-400"
                        placeholder="00:00"
                      />
                      <input
                        type="text"
                        value={segment.end}
                        onChange={(e) => onUpdateTranscriptionSegment(idx, 'end', e.target.value)}
                        className="w-24 bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm font-mono text-primary-400"
                        placeholder="00:00"
                      />
                      {onRemoveTranscriptionSegment && tempTranscription.length > 1 ? (
                        <button
                          type="button"
                          onClick={() => onRemoveTranscriptionSegment(idx)}
                          className="ml-auto p-1.5 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Remover segmento"
                        >
                          <Trash2 size={15} />
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    onRemoveTranscriptionSegment && tempTranscription.length > 1 ? (
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => onRemoveTranscriptionSegment(idx)}
                          className="p-1.5 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Remover fala"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ) : null
                  )}
                  <textarea
                    value={segment.text}
                    onChange={(e) => onUpdateTranscriptionSegment(idx, 'text', e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 rounded-xl p-3 text-[15px] text-slate-200 outline-none focus:border-primary-500/50 resize-none"
                    rows={auditType === 'audio' ? 2 : 3}
                    placeholder={auditType === 'audio' ? 'Texto da fala...' : 'Locutor: mensagem'}
                  />
                </div>
                {onAddTranscriptionSegment ? (
                  <div className="flex justify-center py-1">
                    <button
                      type="button"
                      onClick={() => onAddTranscriptionSegment(idx)}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs text-primary-400/70 hover:text-primary-300 hover:bg-primary-500/10 border border-dashed border-primary-500/20 hover:border-primary-500/40 transition-all"
                      title="Inserir nova fala abaixo"
                    >
                      <Plus size={13} />
                      Inserir fala
                    </button>
                  </div>
                ) : null}
              </div>
            ))
          )}
          {!transcription || transcription.length === 0 ? (
            <p className="text-slate-500 text-base italic">Transcrição indisponível.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
