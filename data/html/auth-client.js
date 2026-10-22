'use strict';
(() => {
    const nativeFetch = window.fetch.bind(window);
    let state = null;
    let pending = null;
    let redirecting = false;
    function signIn() {
        if (!redirecting) { redirecting = true; window.location.replace('/login'); }
    }
    async function session() {
        if (state) return state;
        if (!pending) pending = (async () => {
            const controller = new AbortController();
            const deadline = setTimeout(() => controller.abort(), 10000);
            let response;
            try { response = await nativeFetch('/auth/session', {cache: 'no-store', credentials: 'same-origin', signal: controller.signal}); }
            finally { clearTimeout(deadline); }
            // Explicit compatibility with the unchanged generic (non-E32) webserver only.
            // E32 always registers this route and returns 401/503, never this 404.
            if (response.status === 404) return (state = {legacy: true});
            if (response.status === 401) { signIn(); throw new Error('Sign in required'); }
            if (!response.ok) throw new Error('Session check unavailable');
            const data = await response.json();
            if (data.authenticated !== true || !/^[a-f0-9]{64}$/.test(data.csrf)) throw new Error('Invalid session response');
            return (state = {legacy: false, csrf: data.csrf});
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
    async function attachSignOut() {
        // Existing fragment navigation uses jQuery.load (GET), not window.fetch.
        if (window.jQuery) window.jQuery(document).ajaxError((event, xhr, settings) => {
            const url = new URL(settings.url, window.location.href);
            if (url.origin === window.location.origin && xhr.status === 401 && (!state || !state.legacy)) {
                state = null; signIn();
            }
        });
        try {
            const current = await session();
            const button = document.getElementById('auth-sign-out');
            if (!button || current.legacy) return;
            button.hidden = false;
            button.addEventListener('click', async event => {
                event.preventDefault();
                event.stopPropagation(); // Do not let the legacy menu handler clear the page on failed logout.
                button.disabled = true;
                try {
                    const response = await window.fetch('/auth/logout', {method: 'POST'});
                    if (!response.ok) throw new Error('Sign out failed');
                    state = null; signIn();
                } catch (error) { button.disabled = false; window.alert('Could not sign out. Check the connection and try again.'); }
            });
        } catch (error) { /* API calls surface the same bounded session error. */ }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attachSignOut);
    else attachSignOut();
})();
