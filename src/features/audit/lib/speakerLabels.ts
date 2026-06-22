/**
 * Helpers puros para o rótulo de locutor da diarização.
 *
 * Na transcrição salva o locutor é um PREFIXO no texto da fala
 * (ex.: "Operador: bom dia"). Estes utilitários leem/trocam esse prefixo —
 * usados pelo controle de "trocar interlocutor" em Arquivos Salvos / Auditorias
 * do mês. Espelha o parse e as cores de `shared/components/ReadOnlyTranscription`.
 */

export interface SpeakerOption {
  value: string;
  label: string;
}

/**
 * Falantes oferecidos no menu de troca. Todos com 1 palavra para casar com
 * `parseSpeakerPrefix` (que só aceita rótulo de até 2 palavras) e com as cores
 * do badge (operador/cliente/motorista/policia/apoio/telefonia).
 */
export const SPEAKER_OPTIONS: SpeakerOption[] = [
  { value: 'Operador', label: 'Operador' },
  { value: 'Cliente', label: 'Cliente' },
  { value: 'Motorista', label: 'Motorista' },
  { value: 'Polícia', label: 'Polícia' },
  { value: 'Apoio', label: 'Ponto de Apoio' },
  { value: 'Telefonia', label: 'Telefonia' },
];

/** Separa o prefixo de locutor ("Operador: ...") do corpo da fala. */
export function parseSpeakerPrefix(text: string): { speaker: string; body: string } {
  const colonIdx = text.indexOf(':');
  if (colonIdx > 0 && colonIdx < 30) {
    const candidate = text.slice(0, colonIdx).trim();
    if (candidate && candidate.split(' ').length <= 2) {
      return { speaker: candidate, body: text.slice(colonIdx + 1).trim() };
    }
  }
  return { speaker: '', body: text };
}

/** Reescreve o texto da fala com o novo locutor (string vazia remove o rótulo). */
export function setSegmentSpeaker(text: string, speaker: string): string {
  const { body } = parseSpeakerPrefix(text);
  const trimmed = speaker.trim();
  return trimmed ? `${trimmed}: ${body}` : body;
}
