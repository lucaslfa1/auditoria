import type { AuditAlert, TranscriptionSegment } from '../../features/audit/types/audit';

/**
 * Infer the interlocutor identification based on the alert context.
 * Mirrors the backend logic in `transcription_orchestrator.infer_interlocutor_label`.
 */
export function inferInterlocutorLabel(alert: AuditAlert | null): string {
    if (!alert) return 'Motorista';

    const haystack = `${alert.label || ''} ${alert.context || ''}`.toLowerCase();

    if (haystack.includes('ponto de apoio') || haystack.includes('posto')) {
        return 'Ponto de Apoio';
    }
    if (haystack.includes('policia') || haystack.includes('polícia')) {
        return 'Policia';
    }
    if (haystack.includes('cliente')) {
        return 'Cliente';
    }
    return 'Motorista';
}

/** All known interlocutor labels that can appear as the non-operator speaker. */
const KNOWN_DRIVER_LABELS = ['Motorista', 'Cliente', 'Ponto de Apoio', 'Policia'];

/**
 * Re-label interlocutors in the transcription segments.
 * The speaker identity is embedded in the `text` field as a prefix (e.g., "Motorista: Alô").
 * This replaces the old driver prefix with the new one, keeping "Operador" intact.
 */
export function relabelTranscriptionInterlocutors(
    transcription: TranscriptionSegment[],
    oldDriverLabel: string,
    newDriverLabel: string,
): TranscriptionSegment[] {
    if (oldDriverLabel === newDriverLabel) return transcription;

    // Build a set of labels to search for (old + any other known driver label)
    const labelsToReplace = new Set([oldDriverLabel, ...KNOWN_DRIVER_LABELS]);
    // Don't replace "Operador" — that's always the operator
    labelsToReplace.delete('Operador');

    return transcription.map((seg) => {
        let newText = seg.text;
        for (const label of labelsToReplace) {
            if (newText.startsWith(`${label}:`)) {
                newText = `${newDriverLabel}:${newText.slice(label.length + 1)}`;
                break;
            }
        }
        return newText !== seg.text ? { ...seg, text: newText } : seg;
    });
}
