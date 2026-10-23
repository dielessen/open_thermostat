'use strict';
(() => {
    const form = document.getElementById('login');
    const button = document.getElementById('submit');
    const message = document.getElementById('message');
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled || !form.reportValidity()) return;
        button.disabled = true;
        message.textContent = uiText("Signing in…");
        const body = new URLSearchParams({username: form.elements.username.value, password: form.elements.password.value});
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch('/auth/login', {method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: body.toString()});
            if (response.ok) { window.location.replace('/'); return; }
            const data = await response.json().catch(() => ({}));
            message.textContent = data.error === 'session_capacity' ? uiText("Four browsers are already signed in. Sign out in one, or wait for its session to expire.") :
                response.status === 429 ? uiText("Too many attempts. Wait 30 seconds before trying again.") :
                response.status === 401 ? uiText("Username or password was not accepted. Try again.") : uiText("The device could not sign you in. Try again.");
        } catch (error) { message.textContent = uiText("Cannot reach the device. Check the connection and try again."); }
        finally { clearTimeout(deadline); form.elements.password.value = ''; button.disabled = false; }
    });
})();
