/* Local UI preference only. No device configuration, control or user data is translated. */
'use strict';
(() => {
    const messages = window.OT_UI_MESSAGES || {};
    const saved = document.cookie.match(/(?:^|;\s*)ot_ui_lang=(en|nl)(?:;|$)/);
    const language = saved ? saved[1] : 'en';
    const normalize = value => value.trim().replace(/\s+/g, ' ');
    function text(value) {
        if (typeof value !== 'string') return value;
        const key = normalize(value);
        if (language !== 'nl' || !Object.hasOwn(messages, key)) return value; // English is the fallback for new source messages.
        const leading = value.match(/^\s*/)[0], trailing = value.match(/\s*$/)[0];
        return leading + messages[key] + trailing;
    }
    function html(value) {
        // Called on source literals before interpolation; never on a user's rendered content.
        return value.replace(/(^|>)([^<>]+)(?=<|$)/g, (all, prefix, content) => {
            const decoded = content.replace(/&(?:amp|deg|times|nbsp);/g, entity => ({'&amp;':'&','&deg;':'°','&times;':'×','&nbsp;':' '})[entity]);
            const translated = text(decoded);
            return translated === content ? all : prefix + translated.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        });
    }
    function apply(root) {
        if (!root || !root.querySelectorAll) return;
        const nodes = [...root.querySelectorAll('[data-i18n],[data-i18n-title],[data-i18n-placeholder],[data-i18n-aria-label],[data-i18n-alt]')];
        if (root.nodeType === 1) nodes.unshift(root);
        for (const node of nodes) {
            if (node.hasAttribute('data-i18n')) node.textContent = text(node.getAttribute('data-i18n'));
            for (const name of ['title', 'placeholder', 'aria-label', 'alt']) {
                const key = node.getAttribute('data-i18n-' + name);
                if (key !== null) node.setAttribute(name, text(key));
            }
        }
    }
    function selector() {
        const host = document.getElementById('navbarNavDropdown') || document.querySelector('main') || document.body;
        if (!host || document.getElementById('ui-language-choice')) return;
        const label = document.createElement('label');
        label.style.cssText = 'display:inline-flex;align-items:center;gap:8px;margin:8px;color:inherit;font-size:14px';
        label.append(document.createTextNode(language === 'nl' ? 'Taal' : 'Language'));
        const select = document.createElement('select');select.id = 'ui-language-choice';select.setAttribute('aria-label',language === 'nl'?'Taal':'Language');
        for (const [value, name] of [['en','English'],['nl','Nederlands']]) {
            const option = document.createElement('option'); option.value = value;option.textContent = name;select.append(option);
        }
        select.value = language;
        select.addEventListener('change', () => {
            if (!window.confirm(text('Changing language reloads this page. Unsaved changes will be lost. Continue?'))) {select.value = language;return;}
            document.cookie = 'ot_ui_lang=' + select.value + '; Path=/; Max-Age=31536000; SameSite=Strict';
            window.location.reload();
        });
        label.append(select);host.prepend(label);
    }
    window.uiText = text;window.uiHtml = html;
    window.OpenThermostatLanguage = Object.freeze({language,locale:language === 'nl'?'nl-NL':'en-GB',apply});
    document.documentElement.lang = language;
    document.addEventListener('DOMContentLoaded', () => {
        apply(document);selector();
        new MutationObserver(records => {
            for (const record of records) for (const node of record.addedNodes) if (node.nodeType === 1) apply(node);
        }).observe(document.body, {childList:true,subtree:true});
    });
})();
