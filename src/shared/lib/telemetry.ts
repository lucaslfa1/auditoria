let logsSentInLastMinute = 0;
let windowStartTime = Date.now();
const MAX_LOGS_PER_MINUTE = 20;

export const logToTelemetry = async (level: 'info' | 'warn' | 'error', message: string, stack?: string) => {
    try {
        const now = Date.now();
        if (now - windowStartTime > 60000) {
            logsSentInLastMinute = 0;
            windowStartTime = now;
        }

        if (logsSentInLastMinute >= MAX_LOGS_PER_MINUTE) {
            // Silently drop log to prevent network flooding and API abuse
            return;
        }

        logsSentInLastMinute++;

        const payload = {
            level,
            message,
            stack,
            url: window.location.href,
            user_agent: navigator.userAgent
        };
        
        // We use a fire-and-forget fetch that doesn't trigger the API interceptors
        // to avoid infinite loops if the telemetry endpoint itself fails.
        fetch('/api/system/client-logs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).catch(() => { /* silently ignore telemetry failures */ });
    } catch {
        // Safe fallback
    }
};
