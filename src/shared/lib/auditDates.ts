const SP_TZ = 'America/Sao_Paulo';

function safeDate(value: string | null | undefined): Date | null {
  if (!value || typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const d = new Date(trimmed.length === 10 ? trimmed + 'T00:00:00' : trimmed);
  return Number.isNaN(d.getTime()) ? null : d;
}

function isoDateInSP(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: SP_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
  return parts;
}

export function formatAudioMoment(audioDate: string | null | undefined, timestamp: string | null | undefined): string {
  const audioValue = audioDate ? audioDate.trim() : '';
  const audioTs = safeDate(audioValue);
  if (audioTs && audioValue.length > 10) {
    return audioTs.toLocaleString('pt-BR', { timeZone: SP_TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  const audioDay = audioValue ? audioValue.slice(0, 10) : '';
  const ts = safeDate(timestamp);
  if (audioDay && ts && isoDateInSP(ts) === audioDay) {
    return ts.toLocaleString('pt-BR', { timeZone: SP_TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  if (audioDay) {
    const d = safeDate(audioDay);
    return d ? d.toLocaleDateString('pt-BR', { timeZone: SP_TZ, day: '2-digit', month: '2-digit', year: 'numeric' }) : audioDay;
  }
  if (ts) {
    return ts.toLocaleString('pt-BR', { timeZone: SP_TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  return '';
}
