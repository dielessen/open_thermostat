'use strict';
(() => {
    const form = document.getElementById('login');
    const button = document.getElementById('submit');
    const message = document.getElementById('message');
    const recovery = document.getElementById('session-recovery');
    const signIn = document.getElementById('sign-in');
    const choose = document.getElementById('choose-password');
    const chooseMessage = document.getElementById('password-message');
    const save = document.getElementById('save-password');
    // The factory password just used to sign in (only in memory, only for the change below).
    let current = '';
    let csrf = '';
    async function session() {
        const response = await fetch('/auth/session', {credentials: 'same-origin', cache: 'no-store'});
        if (!response.ok) return null;
        const data = await response.json().catch(() => null);
        return data && data.authenticated === true && typeof data.csrf === 'string' && /^[a-f0-9]{64}$/.test(data.csrf) ? data : null;
    }
    // While the E32 still uses the default password nothing else can be changed:
    // this step comes first, right after signing in (also from every other page).
    function choosePassword(state) {
        csrf = state.csrf;
        signIn.hidden = true; choose.hidden = false;
        document.getElementById('new-password').focus();
    }
    // Sent here by another page (auth-client.js) while the default password is in use.
    if (window.location.hash === '#password') session().then(state => { if (state && state.default_password === true) choosePassword(state); }, () => {});
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled || !form.reportValidity()) return;
        button.disabled = true;
        message.textContent = uiText("Signing in…");
        const password = form.elements.password.value;
        const body = new URLSearchParams({username: form.elements.username.value, password});
        if (form.elements.recover_sessions.checked) body.set('recover_sessions', '1');
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch('/auth/login', {method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: body.toString()});
            if (response.ok) {
                const result = await response.json().catch(() => ({}));
                const state = result.default_password === true ? await session().catch(() => null) : null;
                if (state && state.default_password === true) { current = password; message.textContent = ''; choosePassword(state); return; }
                window.location.replace('/'); return;
            }
            const data = await response.json().catch(() => ({}));
            if (data.error === 'session_capacity') recovery.hidden = false;
            message.textContent = data.error === 'session_capacity' ? uiText("Four saved web sessions occupy all sign-in slots. To recover access, select the option below and enter your password again.") :
                data.error === 'session_recovery_busy' ? uiText("Session recovery is unavailable during a boiler test or firmware update. Try again after it has finished.") :
                response.status === 429 ? uiText("Too many attempts. Wait 30 seconds before trying again.") :
                response.status === 401 ? uiText("Username or password was not accepted. Try again.") : uiText("The device could not sign you in. Try again.");
        } catch (error) { message.textContent = uiText("Cannot reach the device. Check the connection and try again."); }
        finally { clearTimeout(deadline); form.elements.password.value = ''; button.disabled = false; }
    });
    choose.addEventListener('submit', async event => {
        event.preventDefault();
        if (save.disabled) return;
        const next = document.getElementById('new-password'), again = document.getElementById('repeat-password');
        const say = text => { chooseMessage.textContent = text; };
        // Characters as the firmware counts them (code points): "Zoë" is 3.
        const length = [...next.value].length;
        if (length < 8) { say(uiText("Use at least 8 characters.")); next.focus(); return; }
        if (length > 64) { say(uiText("Use at most 64 characters.")); next.focus(); return; }
        if (next.value !== again.value) { say(uiText("The two passwords are not the same.")); again.focus(); return; }
        save.disabled = true; say(uiText("Saving the password…"));
        try {
            // The E32 reports default_password only while its password is admin.
            const response = await fetch('/auth/password', {method: 'POST', credentials: 'same-origin', cache: 'no-store',
                headers: {'Content-Type': 'application/json', 'X-OpenThermostat-CSRF': csrf},
                body: JSON.stringify({current: current || 'admin', new: next.value})});
            if (response.ok) { current = ''; choose.reset(); say(uiText("Password saved. Opening OpenThermostat…")); window.location.replace('/'); return; }
            const error = (await response.json().catch(() => ({}))).error;
            if (response.status === 401 || error === 'password_wrong') {
                choose.hidden = true; signIn.hidden = false; current = '';
                message.textContent = uiText("Your session has ended. Sign in again with admin and choose your password.");
                form.elements.password.focus(); return;
            }
            say(error === 'password_too_short' ? uiText("Use at least 8 characters.") : error === 'password_too_long' ? uiText("Use at most 64 characters.")
                : error === 'password_change_busy' ? uiText("An update is running. Choose your password after the update has finished.")
                : response.status === 429 ? uiText("Too many attempts. Wait 30 seconds before trying again.") : uiText("The password was not saved. Try again."));
        } catch (_) { say(uiText("Cannot reach the device. Check the connection and try again.")); }
        finally { save.disabled = false; }
    });
})();
