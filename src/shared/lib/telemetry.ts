export const logToTelemetry = async (level: 'info' | 'warn' | 'error', message: string, stack?: string) => {
    try {
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
