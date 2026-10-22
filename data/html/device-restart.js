'use strict';
(() => {
    async function attachRestart() {
        const button = document.getElementById('device-restart');
        const status = document.getElementById('device-restart-status');
        if (!button || !status || !window.OpenThermostatAuth) return;
        try {
            const session = await window.OpenThermostatAuth.ready();
            if (session.legacy) return; // Generic targets do not expose the E32 updater.
        } catch (error) { return; }
        button.hidden = false;
        button.addEventListener('click', async event => {
            event.preventDefault();
            event.stopPropagation();
            if (button.disabled || !window.confirm('Restart this device now? Settings will be kept. All browsers will need to sign in again.')) return;
            button.disabled = true;
            status.textContent = 'Checking device status…';
            let accepted = false;
            const controller = new AbortController();
            const deadline = setTimeout(() => controller.abort(), 10000);
            try {
                const response = await window.fetch('/updates/status', {cache: 'no-store', credentials: 'same-origin', signal: controller.signal});
                if (!response.ok) throw new Error('Device status unavailable. No restart was requested.');
                const current = await response.json();
                if (current.busy !== false || current.boot_pending !== false || current.reboot_scheduled !== false) {
                    throw new Error('Wait until the firmware update and startup checks have finished.');
                }
                const headers = await window.OpenThermostatAuth.headers();
                const result = await window.fetch('/updates/reboot', {method: 'POST', credentials: 'same-origin', headers, signal: controller.signal});
                if (result.status !== 202) {
                    throw new Error(result.status === 409 ? 'The device is busy. Restart was not accepted.' : 'Restart was not confirmed. Check device status before trying again.');
                }
                accepted = true;
                status.textContent = 'Restart requested. Wait for the device, then reload to sign in again.';
            } catch (error) {
                status.textContent = error.name === 'AbortError'
                    ? 'The request timed out. Check device status before trying again.'
                    : error.message || 'Restart was not confirmed. Check device status before trying again.';
            } finally {
                clearTimeout(deadline);
                // An uncertain or failed POST is never replayed automatically.
                if (!accepted) button.disabled = false;
            }
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attachRestart);
    else attachRestart();
})();
