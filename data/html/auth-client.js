'use strict';
(() => {
    const nativeFetch = window.fetch.bind(window);
    let state = null;
    let pending = null;
    let redirecting = false;
    function signIn() {
        if (!redirecting) { redirecting = true; window.location.replace('/login'); }
    }
    // The factory password: the E32 accepts no change until the owner chose their own
    // (403 password_change_required), so the sign-in page asks for it first.
    function choosePassword() {
        if (!redirecting && window.location.pathname !== '/login') { redirecting = true; window.location.replace('/login#password'); }
    }
    async function session() {
        if (state) return state;
        if (!pending) pending = (async () => {
            const controller = new AbortController();
            const deadline = setTimeout(() => controller.abort(), 10000);
            try {
                const response = await nativeFetch('/auth/session', {cache: 'no-store', credentials: 'same-origin', signal: controller.signal});
                if (controller.signal.aborted) throw controller.signal.reason;
                // Explicit compatibility with the unchanged generic (non-E32) webserver only.
                // E32 always registers this route and returns 401/503, never this 404.
                if (response.status === 404) return (state = {legacy: true});
                if (response.status === 401) { signIn(); throw new Error(uiText("Sign in required")); }
                if (!response.ok) throw new Error(uiText("Session check unavailable"));
                // Headers alone do not complete this shared request. Keep its
                // original deadline through body consumption and proof validation.
                const data = await response.json();
                if (controller.signal.aborted) throw controller.signal.reason;
                if (!data || typeof data !== 'object' || Array.isArray(data) || data.authenticated !== true ||
                    typeof data.csrf !== 'string' || !/^[a-f0-9]{64}$/.test(data.csrf)) throw new Error(uiText("Invalid session response"));
                state = {legacy: false, csrf: data.csrf, default_password: data.default_password === true};
                if (state.default_password) choosePassword();
                if (document.readyState !== 'loading') showSession(state); // also after a failed first check (R3-14)
                return state;
            } catch (error) {
                if (controller.signal.aborted) throw new Error(uiText("Session check unavailable"));
                throw error;
            } finally { clearTimeout(deadline); }
        })().finally(() => { pending = null; });
        return pending;
    }
    async function headers() {
        const current = await session();
        return current.legacy ? {} : {'X-OpenThermostat-CSRF': current.csrf};
    }
    window.fetch = async (input, init) => {
        const request = input instanceof Request ? input : null;
        const url = new URL(request ? request.url : input, window.location.href);
        if (url.origin !== window.location.origin) return nativeFetch(input, init);
        const method = (init && init.method || request && request.method || 'GET').toUpperCase();
        const options = {...init};
        await session();
        if (method !== 'GET' && method !== 'HEAD') {
            const combined = new Headers(init && init.headers !== undefined ? init.headers : request ? request.headers : undefined);
            for (const [name, value] of Object.entries(await headers())) combined.set(name, value);
            options.headers = combined;
        }
        const response = await nativeFetch(input, options);
        // Never replay a failed mutation or turn transient network errors into logout.
        if (response.status === 401 && (!state || !state.legacy)) { state = null; signIn(); }
        return response;
    };
    window.OpenThermostatAuth = {headers, ready: session};
    // What depends on the session: Bluetooth (E32 only) and Sign out, an item of the System menu (rc.4, R3-14).
    let signOutReady = false;
    function showSession(current) {
        document.querySelectorAll('[data-bluetooth-settings]').forEach(node => {
            node.hidden = current.legacy;
        });
        const button = document.getElementById('auth-sign-out');
        if (!button || current.legacy || signOutReady) return;
        signOutReady = true;
        const items = document.querySelectorAll('[data-sign-out-item]');
        if (items.length) items.forEach(item => { item.hidden = false; }); else button.hidden = false;
        button.addEventListener('click', async event => {
            event.preventDefault();
            event.stopPropagation(); // Do not let the legacy menu handler clear the page on failed logout.
            button.disabled = true;
            try {
                const response = await window.fetch('/auth/logout', {method: 'POST'});
                if (!response.ok) throw new Error(uiText("Sign out failed"));
                state = null; signIn();
            } catch (error) { button.disabled = false; window.alert(uiText("Could not sign out. Check the connection and try again.")); }
        });
    }
    async function attachSignOut() {
        // Existing fragment navigation uses jQuery.load (GET), not window.fetch.
        if (window.jQuery) window.jQuery(document).ajaxError((event, xhr, settings) => {
            const url = new URL(settings.url, window.location.href);
            if (url.origin === window.location.origin && xhr.status === 401 && (!state || !state.legacy)) {
                state = null; signIn();
            }
        });
        try { showSession(await session()); }
        catch (error) { /* API calls surface the same bounded session error; the next good check shows Sign out. */ }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attachSignOut);
    else attachSignOut();
})();
