'use strict';
(() => {
    // One confirmed restart request; shared by the System menu and inline "Restart now" buttons.
    async function restart(button, status) {
        if (button.disabled || !window.confirm(uiText("Restart this device now? Settings will be kept. All browsers will need to sign in again."))) return;
        button.disabled = true;
        status.textContent = uiText("Checking device status…");
        let accepted = false;
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 10000);
        try {
            const response = await window.fetch('/updates/status', {cache: 'no-store', credentials: 'same-origin', signal: controller.signal});
            if (!response.ok) throw new Error(uiText("Device status unavailable. No restart was requested."));
            const current = await response.json();
            if (current.busy !== false || current.boot_pending !== false || current.reboot_scheduled !== false) {
                throw new Error(uiText("Wait until the firmware update and startup checks have finished."));
            }
            const headers = await window.OpenThermostatAuth.headers();
            const result = await window.fetch('/updates/reboot', {method: 'POST', credentials: 'same-origin', headers, signal: controller.signal});
            if (result.status !== 202) {
                throw new Error(result.status === 409 ? uiText("The device is busy. Restart was not accepted.") : uiText("Restart was not confirmed. Check device status before trying again."));
            }
            accepted = true;
            status.textContent = uiText("Restart requested. Wait for the device, then reload to sign in again.");
        } catch (error) {
            status.textContent = error.name === 'AbortError'
                ? uiText("The request timed out. Check device status before trying again.")
                : error.message || uiText("Restart was not confirmed. Check device status before trying again.");
        } finally {
            clearTimeout(deadline);
            // An uncertain or failed POST is never replayed automatically.
            if (!accepted) button.disabled = false;
        }
    }
    window.OpenThermostatRestart = restart;
    async function attachRestart() {
        const button = document.getElementById('device-restart');
        const status = document.getElementById('device-restart-status');
        if (!button || !status || !window.OpenThermostatAuth) return;
        try {
            const session = await window.OpenThermostatAuth.ready();
            if (session.legacy) return; // Generic targets do not expose the E32 updater.
        } catch (error) { return; }
        button.hidden = false;
        button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            return restart(button, status);
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attachRestart);
    else attachRestart();
})();
