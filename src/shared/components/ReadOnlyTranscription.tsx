interface TranscriptionSegment {
  start: string;
  end: string;
  text: string;
}

interface ReadOnlyTranscriptionProps {
  transcription: TranscriptionSegment[];
  onSeekAudio?: (timeStr: string) => void;
  maxHeightClass?: string;
}

function parseSpeakerPrefix(text: string): { speaker: string; body: string } {
  const colonIdx = text.indexOf(':');
  if (colonIdx > 0 && colonIdx < 30) {
    const candidate = text.slice(0, colonIdx).trim();
    if (candidate && candidate.split(' ').length <= 2) {
      return { speaker: candidate, body: text.slice(colonIdx + 1).trim() };
    }
  }
  return { speaker: '', body: text };
}

function getSpeakerBadgeClass(speaker: string): string {
  const lower = speaker.toLowerCase();
  if (lower.includes('operador')) {
    return 'bg-blue-500/15 text-blue-300 border-blue-500/25 theme-light:bg-blue-50 theme-light:text-blue-700 theme-light:border-blue-300';
  }
  if (lower.includes('motorista') || lower.includes('cliente')) {
    return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25 theme-light:bg-emerald-50 theme-light:text-emerald-700 theme-light:border-emerald-300';
  }
  if (lower.includes('policia') || lower.includes('polícia')) {
    return 'bg-orange-500/15 text-orange-300 border-orange-500/25 theme-light:bg-orange-50 theme-light:text-orange-700 theme-light:border-orange-300';
  }
  if (lower.includes('ponto') || lower.includes('apoio')) {
    return 'bg-purple-500/15 text-purple-300 border-purple-500/25 theme-light:bg-purple-50 theme-light:text-purple-700 theme-light:border-purple-300';
  }
  if (lower === 'telefonia') {
    return 'bg-slate-500/15 text-slate-400 border-slate-500/25 theme-light:bg-slate-100 theme-light:text-slate-600 theme-light:border-slate-300';
  }
  return 'bg-slate-600/15 text-slate-400 border-slate-600/20 theme-light:bg-slate-100 theme-light:text-slate-600 theme-light:border-slate-300';
}

export function ReadOnlyTranscription({
  transcription,
  onSeekAudio,
  maxHeightClass = 'max-h-[24rem]'
}: ReadOnlyTranscriptionProps) {
  if (!transcription || transcription.length === 0) {
    return <p className="text-sm text-slate-500">Transcrição não disponível para esta auditoria.</p>;
  }

  return (
    <div className={`${maxHeightClass} overflow-y-auto pr-1`}>
      {transcription.map((segment, index) => {
        const { speaker, body } = parseSpeakerPrefix(segment.text);
        const badgeClass = speaker ? getSpeakerBadgeClass(speaker) : '';
        
        // Se houver onSeekAudio, renderizamos como botão
        if (onSeekAudio) {
          return (
            <button
              type="button"
              key={`${segment.start}-${segment.end}-${index}`}
              onClick={() => onSeekAudio(segment.start)}
              className="w-full text-left flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-white/[0.03] transition-colors theme-light:hover:bg-slate-50 group border border-transparent hover:border-primary-500/20"
            >
              <span className="w-[4.5rem] shrink-0 pt-0.5 font-mono text-[10px] font-semibold text-slate-500 group-hover:text-primary-400 transition-colors theme-light:text-slate-400">
                {segment.start}
              </span>
              <div className="min-w-0 flex-1">
                {speaker && (
                  <span className={`mb-1 inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase ${badgeClass}`}>
                    {speaker}
                  </span>
                )}
                <p className="text-sm leading-relaxed text-slate-300 group-hover:text-white transition-colors theme-light:text-slate-800 theme-light:group-hover:text-slate-900">
                  {body || segment.text}
                </p>
              </div>
            </button>
          );
        }

        // Senão, modo passivo
        return (
          <div
            key={`${segment.start}-${segment.end}-${index}`}
            className="flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-white/[0.03] transition-colors theme-light:hover:bg-slate-50"
          >
            <span className="w-[4.5rem] shrink-0 pt-0.5 font-mono text-[10px] font-semibold text-slate-500 theme-light:text-slate-400">
              {segment.start}
            </span>
            <div className="min-w-0 flex-1">
              {speaker && (
                <span className={`mb-1 inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase ${badgeClass}`}>
                  {speaker}
                </span>
              )}
              <p className="text-sm leading-relaxed text-slate-300 theme-light:text-slate-800">
                {body || segment.text}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
