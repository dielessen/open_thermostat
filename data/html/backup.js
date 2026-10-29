'use strict';
// Backup and restore of the E32 settings (POST /config/backup). Staged restore:
// choose a file, check it (the E32 validates and summarises), then restore.
// User data (names, hosts) is only ever inserted as text.
(() => {
    // Dutch for this panel only: loaded with the panel, not with every page
    // (ui-messages.js keeps the Home payload budget). Never replaces an entry.
    const dutch = {
        "Device name": "Apparaatnaam",
        "Web page port": "Poort van de webpagina",
        "EMS bus": "EMS-bus",
        "EMS forwarder": "EMS-doorsturing",
        "Clock chip": "Klokchip",
        "Time from the internet": "Tijd van internet",
        "Time server": "Tijdserver",
        "UTC offset": "Verschil met UTC",
        "Daylight saving offset": "Verschil zomertijd",
        "MQTT": "MQTT",
        "Home Assistant link": "Koppeling met Home Assistant",
        "Home Assistant adapter ID": "Adapter-ID van Home Assistant",
        "MQTT discovery": "MQTT-discovery",
        "MQTT broker": "MQTT-broker",
        "MQTT port": "MQTT-poort",
        "MQTT user": "MQTT-gebruiker",
        "MQTT password": "MQTT-wachtwoord",
        "MQTT client ID": "MQTT-client-ID",
        "MQTT topic": "MQTT-topic",
        "MQTT keep-alive": "MQTT-keep-alive",
        "MQTT interval": "MQTT-interval",
        "OpenWeather": "OpenWeather",
        "OpenWeather API key": "OpenWeather-API-sleutel",
        "Bluetooth listening time": "Luistertijd Bluetooth",
        "Bluetooth pause": "Pauze Bluetooth",
        "Room settings": "Instellingen van de ruimtes",
        "Lowest flow temperature": "Laagste aanvoertemperatuur",
        "Highest flow temperature": "Hoogste aanvoertemperatuur",
        "Weather curve": "Weersafhankelijke stooklijn",
        "Use learned values": "Geleerde waarden gebruiken",
        "Design flow temperature": "Ontwerp-aanvoertemperatuur",
        "Wi-Fi password": "Wifi-wachtwoord",
        "Web page password": "Wachtwoord van de webpagina",
        "Bluetooth sensor keys": "Sleutels van Bluetooth-sensoren",
        "Bluetooth key for {v}": "Bluetooth-sleutel van {v}",
        "Made with firmware {v}.": "Gemaakt met firmware {v}.",
        "Skipped, not known by this firmware: {v}": "Overgeslagen, onbekend voor deze firmware: {v}",
        "Invalid value: {v}": "Ongeldige waarde: {v}",
        "The connection type stays as it is, so you can still reach this page.": "Het verbindingstype blijft zoals het is, zodat je deze pagina kunt blijven bereiken.",
        "The web page port stays the same, so you can still reach this page.": "De poort van de webpagina blijft gelijk, zodat je deze pagina kunt blijven bereiken.",
        "MQTT stays off until you enter the MQTT password.": "MQTT blijft uit tot je het MQTT-wachtwoord invoert.",
        "Weather settings are managed by Home Assistant and stay as they are.": "De weerinstellingen worden door Home Assistant beheerd en blijven zoals ze zijn.",
        "The rooms are restored in shadow mode. Switch to active control yourself when you are ready.": "De ruimtes worden in schaduwmodus teruggezet. Schakel zelf over naar actieve regeling als je er klaar voor bent.",
        "Wi-Fi is not changed by a restore. Use the Wi-Fi setup for another network.": "Terugzetten verandert de wifi niet. Gebruik de wifi-installatie voor een ander netwerk.",
        "Passwords and keys in the backup are skipped because no passphrase was entered.": "Wachtwoorden en sleutels in de back-up worden overgeslagen, want er is geen wachtzin ingevoerd.",
        "Unknown boiler model skipped: {v}": "Onbekend ketelmodel overgeslagen: {v}",
        "Unknown language skipped.": "Onbekende taal overgeslagen.",
        "Rooms: {v}": "Ruimtes: {v}",
        "Bluetooth sensors: {v}": "Bluetooth-sensoren: {v}",
        "This file is not an OpenThermostat E32 backup.": "Dit bestand is geen back-up van een OpenThermostat E32.",
        "This backup was made by newer firmware. Update this E32 first.": "Deze back-up is gemaakt met nieuwere firmware. Werk deze E32 eerst bij.",
        "This backup belongs to another type of device.": "Deze back-up hoort bij een ander soort apparaat.",
        "The passphrase is not correct.": "De wachtzin klopt niet.",
        "Use a passphrase of 8 to 64 characters.": "Gebruik een wachtzin van 8 tot 64 tekens.",
        "Restore is blocked while the E32 controls the boiler or a boiler test is running.": "Terugzetten kan niet zolang de E32 de ketel regelt of er een keteltest loopt.",
        "Wait until the firmware update has finished.": "Wacht tot de firmware-update klaar is.",
        "The file is too large for a backup.": "Het bestand is te groot voor een back-up.",
        "The settings on this E32 changed after the check. Check the backup again.": "De instellingen van deze E32 zijn na de controle gewijzigd. Controleer de back-up opnieuw.",
        "Saving failed. The previous settings are kept.": "Opslaan is mislukt. De vorige instellingen blijven behouden.",
        "Saving failed and not every previous setting could be put back. Check the settings pages.": "Opslaan is mislukt en niet alle vorige instellingen konden worden teruggezet. Controleer de instellingenpagina's.",
        "The E32 is busy. Try again in a minute.": "De E32 is bezig. Probeer het over een minuut opnieuw.",
        "The settings of this E32 could not be read.": "De instellingen van deze E32 konden niet worden gelezen.",
        "Save the settings of this E32 in a file, or restore them on a new or reset E32.": "Bewaar de instellingen van deze E32 in een bestand, of zet ze terug op een nieuwe of gewiste E32.",
        "Download backup": "Back-up downloaden",
        "Include passwords and Bluetooth keys, encrypted with a passphrase": "Wachtwoorden en Bluetooth-sleutels meenemen, versleuteld met een wachtzin",
        "Passphrase": "Wachtzin",
        "Repeat passphrase": "Herhaal de wachtzin",
        "Restore a backup": "Een back-up terugzetten",
        "Backup file": "Back-upbestand",
        "Passphrase of this backup": "Wachtzin van deze back-up",
        "Leave empty to restore without passwords and keys.": "Laat leeg om zonder wachtwoorden en sleutels terug te zetten.",
        "Check backup": "Back-up controleren",
        "Restore these settings": "Deze instellingen terugzetten",
        "Making the backup…": "Back-up maken…",
        "Backup downloaded.": "Back-up gedownload.",
        "Not in this backup; enter these again after a restore:": "Niet in deze back-up; voer dit na het terugzetten opnieuw in:",
        "The passphrases do not match.": "De wachtzinnen zijn niet gelijk.",
        "Checking the backup…": "Back-up controleren…",
        "This backup holds encrypted passwords and keys.": "Deze back-up bevat versleutelde wachtwoorden en sleutels.",
        "The backup is valid. These settings will change:": "De back-up is geldig. Deze instellingen veranderen:",
        "Nothing changes: this E32 already has these settings.": "Er verandert niets: deze E32 heeft deze instellingen al.",
        "Notes:": "Opmerkingen:",
        "Enter these again after the restore:": "Voer dit na het terugzetten opnieuw in:",
        "The E32 restarts after the restore; sign in again afterwards.": "De E32 start na het terugzetten opnieuw op; log daarna opnieuw in.",
        "Restoring…": "Terugzetten…",
        "Settings restored.": "Instellingen teruggezet.",
        "The E32 restarts in about {v} seconds. Sign in again afterwards.": "De E32 start over ongeveer {v} seconden opnieuw op. Log daarna opnieuw in.",
        "Restart the E32 to use all restored settings.": "Start de E32 opnieuw op om alle teruggezette instellingen te gebruiken.",
        "The file could not be read.": "Het bestand kon niet worden gelezen.",
        "The backup contains invalid settings.": "De back-up bevat ongeldige instellingen.",
        "The request was not confirmed. Try again.": "Het verzoek is niet bevestigd. Probeer het opnieuw.",
        "will change": "verandert",
        "Choose a backup file first.": "Kies eerst een back-upbestand."
    };
    const catalog = window.OT_UI_MESSAGES;
    if (catalog && typeof catalog === 'object') for (const [key, value] of Object.entries(dutch)) if (!Object.hasOwn(catalog, key)) catalog[key] = value;
    const t = value => (typeof window.uiText === 'function' ? window.uiText(value) : value);
    const fill = (value, v) => t(value).replace('{v}', v);
    const maxBytes = 24576;
    const sections = {network: "Network", bluetooth: "Bluetooth sensors", heating: "Rooms", flow: "Flow temperature", boiler_display: "Boiler model"};
    const fields = {
        hostname: "Device name", interface_mode: "Connection", listenPort: "Web page port", emsEnabled: "EMS bus",
        emsForwarderEnabled: "EMS forwarder", rtcEnabled: "Clock chip", ntpEnabled: "Time from the internet", ntpHost: "Time server",
        ntpUtcOffset: "UTC offset", ntpDaylightUtcOffset: "Daylight saving offset", timeZone: "Time zone",
        loggerEnabled: "Debugging over socket", loggerHost: "Debugging over socket", loggerPort: "Debugging over socket", loggerTimeoutMs: "Debugging over socket",
        'mqtt.enabled': "MQTT", 'mqtt.modern_shadow': "Home Assistant link", 'mqtt.adapter_id': "Home Assistant adapter ID",
        'mqtt.publishHomeAssistantDiscovery': "MQTT discovery", 'mqtt.brokerAddress': "MQTT broker", 'mqtt.brokerPort': "MQTT port",
        'mqtt.username': "MQTT user", 'mqtt.password': "MQTT password", 'mqtt.clientId': "MQTT client ID", 'mqtt.base': "MQTT topic",
        'mqtt.keepAlive': "MQTT keep-alive", 'mqtt.interval': "MQTT interval", 'openweather.enabled': "OpenWeather",
        'openweather.latitude': "OpenWeather", 'openweather.longitude': "OpenWeather", 'openweather.interval': "OpenWeather",
        'openweather.appid': "OpenWeather API key", 'bt.scanTime': "Bluetooth listening time", 'bt.scanInterval': "Bluetooth pause",
        devices: "Sensors", rooms: "Rooms", room_settings: "Room settings", minimum_flow_c: "Lowest flow temperature",
        maximum_flow_c: "Highest flow temperature", weather_curve: "Weather curve", apply_learned: "Use learned values",
        curve_design_flow_c: "Design flow temperature", model: "Boiler model"
    };
    const reenter = {wifi_password: "Wi-Fi password", web_password: "Web page password", mqtt_password: "MQTT password",
        openweather_key: "OpenWeather API key", bluetooth_keys: "Bluetooth sensor keys", bluetooth_key: "Bluetooth key for {v}"};
    const warnings = {
        other_firmware: "Made with firmware {v}.", unknown_key: "Skipped, not known by this firmware: {v}", invalid_value: "Invalid value: {v}",
        interface_kept: "The connection type stays as it is, so you can still reach this page.",
        listen_port_kept: "The web page port stays the same, so you can still reach this page.",
        mqtt_off_until_password: "MQTT stays off until you enter the MQTT password.",
        weather_managed_kept: "Weather settings are managed by Home Assistant and stay as they are.",
        plan_mode_shadow: "The rooms are restored in shadow mode. Switch to active control yourself when you are ready.",
        wifi_not_restored: "Wi-Fi is not changed by a restore. Use the Wi-Fi setup for another network.",
        secrets_skipped: "Passwords and keys in the backup are skipped because no passphrase was entered.",
        unknown_boiler_model: "Unknown boiler model skipped: {v}", unknown_language: "Unknown language skipped.",
        heating: "Rooms: {v}", bluetooth: "Bluetooth sensors: {v}"
    };
    const errors = {
        not_a_backup: "This file is not an OpenThermostat E32 backup.", newer_schema: "This backup was made by newer firmware. Update this E32 first.",
        other_board: "This backup belongs to another type of device.", wrong_passphrase: "The passphrase is not correct.",
        invalid_passphrase: "Use a passphrase of 8 to 64 characters.",
        boiler_owned: "Restore is blocked while the E32 controls the boiler or a boiler test is running.",
        busy: "Wait until the firmware update has finished.", backup_too_large: "The file is too large for a backup.",
        settings_changed: "The settings on this E32 changed after the check. Check the backup again.",
        save_failed_restored: "Saving failed. The previous settings are kept.",
        save_partial: "Saving failed and not every previous setting could be put back. Check the settings pages.",
        out_of_memory: "The E32 is busy. Try again in a minute.", settings_unavailable: "The settings of this E32 could not be read."
    };
    const messages = [sections, fields, reenter, warnings, errors].flatMap(Object.values).concat([
        "Backup and restore", "Save the settings of this E32 in a file, or restore them on a new or reset E32.",
        "Download backup", "Include passwords and Bluetooth keys, encrypted with a passphrase", "Passphrase", "Repeat passphrase",
        "Restore a backup", "Backup file", "Passphrase of this backup", "Leave empty to restore without passwords and keys.",
        "Check backup", "Restore these settings", "Making the backup…", "Backup downloaded.",
        "Not in this backup; enter these again after a restore:", "The passphrases do not match.", "Checking the backup…",
        "This backup holds encrypted passwords and keys.", "The backup is valid. These settings will change:",
        "Nothing changes: this E32 already has these settings.", "Notes:", "Enter these again after the restore:",
        "The E32 restarts after the restore; sign in again afterwards.", "Restoring…", "Settings restored.",
        "The E32 restarts in about {v} seconds. Sign in again afterwards.", "Restart the E32 to use all restored settings.",
        "The file could not be read.", "The backup contains invalid settings.", "The request was not confirmed. Try again.",
        "On", "Off", "will change", "Choose a backup file first."]);

    function element(tag, attributes = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attributes)) {
            if (key === 'text') node.textContent = value; else if (key in node) node[key] = value; else node.setAttribute(key, value);
        }
        node.append(...children);
        return node;
    }
    function shown(value) {
        if (value === true) return t("On");
        if (value === false) return t("Off");
        if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
        if (value === null || value === undefined || value === '') return '—';
        return String(value);
    }
    function coded(map, item) {
        const at = String(item).indexOf(':'), code = at < 0 ? item : item.slice(0, at), detail = at < 0 ? '' : item.slice(at + 1);
        return Object.hasOwn(map, code) ? fill(map[code], detail) : String(item);
    }
    function label(change) {
        const section = t(sections[change.section] || change.section), field = t(fields[change.field] || change.field);
        return section === field ? field : section + ' · ' + field;
    }
    async function post(body, ms = 30000) {
        const controller = new AbortController(), deadline = setTimeout(() => controller.abort(), ms);
        try {
            const response = await fetch('/config/backup', {method: 'POST', cache: 'no-store', credentials: 'same-origin', signal: controller.signal,
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
            let value = null;
            try { value = await response.json(); } catch (_) {}
            return {status: response.status, ok: response.ok, value};
        } finally { clearTimeout(deadline); }
    }

    function mount(root = document.getElementById('ConfigBackup')) {
        const body = root && root.querySelector('#ConfigBackupBody');
        if (!body || body.dataset.mounted) return;
        body.dataset.mounted = '1';
        let file = null, checked = null, busy = false;
        const status = element('p', {role: 'status', 'aria-live': 'polite', id: 'BackupStatus'});
        const restoreStatus = element('div', {role: 'status', 'aria-live': 'polite', id: 'RestoreStatus'});
        const include = element('input', {type: 'checkbox', className: 'form-check-input', id: 'BackupSecrets'});
        const pass = element('input', {type: 'password', className: 'form-control', id: 'BackupPassphrase', autocomplete: 'new-password', minLength: 8, maxLength: 64});
        const pass2 = element('input', {type: 'password', className: 'form-control', id: 'BackupPassphrase2', autocomplete: 'new-password', minLength: 8, maxLength: 64});
        const passRow = element('div', {className: 'mb-2', hidden: true},
            element('label', {htmlFor: 'BackupPassphrase', className: 'form-label', text: t("Passphrase")}), pass,
            element('label', {htmlFor: 'BackupPassphrase2', className: 'form-label mt-2', text: t("Repeat passphrase")}), pass2);
        const download = element('button', {type: 'button', className: 'btn btn-primary mb-2', id: 'BackupDownload', text: t("Download backup")});
        const picker = element('input', {type: 'file', className: 'form-control', id: 'RestoreFile', accept: '.json,application/json'});
        const restorePass = element('input', {type: 'password', className: 'form-control', id: 'RestorePassphrase', autocomplete: 'off', maxLength: 64});
        const restorePassRow = element('div', {className: 'mb-2', hidden: true},
            element('label', {htmlFor: 'RestorePassphrase', className: 'form-label', text: t("Passphrase of this backup")}), restorePass,
            element('small', {className: 'form-text text-muted', text: t("Leave empty to restore without passwords and keys.")}));
        const check = element('button', {type: 'button', className: 'btn btn-outline-primary mb-2 mr-2', id: 'RestoreCheck', text: t("Check backup"), disabled: true});
        const apply = element('button', {type: 'button', className: 'btn btn-primary mb-2', id: 'RestoreApply', text: t("Restore these settings"), disabled: true});
        const summary = element('div', {id: 'RestoreSummary', className: 'mb-2'});
        body.append(
            element('p', {className: 'pd-help', text: t("Save the settings of this E32 in a file, or restore them on a new or reset E32.")}),
            element('div', {className: 'form-check mb-2'}, include, element('label', {className: 'form-check-label', htmlFor: 'BackupSecrets',
                text: t("Include passwords and Bluetooth keys, encrypted with a passphrase")})),
            passRow, download, status,
            element('hr'), element('h3', {className: 'h6 mt-3', text: t("Restore a backup")}),
            element('label', {htmlFor: 'RestoreFile', className: 'form-label', text: t("Backup file")}), picker,
            restorePassRow, element('div', {className: 'mt-2'}, check, apply), summary, restoreStatus);
        const controls = () => {
            download.disabled = busy; picker.disabled = busy; check.disabled = busy || !file;
            apply.disabled = busy || !checked; include.disabled = busy;
        };
        const fail = (target, result) => {
            const code = result && result.value && result.value.error;
            target.replaceChildren(element('span', {text: Object.hasOwn(errors, code || '') ? t(errors[code])
                : /invalid/.test(code || '') ? t("The backup contains invalid settings.") : t("The request was not confirmed. Try again.")}));
            const notes = result && result.value && Array.isArray(result.value.warnings) ? result.value.warnings : [];
            if (notes.length) target.append(element('ul', {}, ...notes.map(n => element('li', {text: coded(warnings, n)}))));
        };
        include.addEventListener('change', () => { passRow.hidden = !include.checked; });
        download.addEventListener('click', async () => {
            if (busy) return;
            const secrets = include.checked;
            if (secrets && (pass.value.length < 8 || pass.value.length > 64)) { status.textContent = t(errors.invalid_passphrase); return; }
            if (secrets && pass.value !== pass2.value) { status.textContent = t("The passphrases do not match."); return; }
            busy = true; controls(); status.textContent = t("Making the backup…");
            try {
                const request = {action: 'export', language: (window.OpenThermostatLanguage && window.OpenThermostatLanguage.language) || 'en'};
                if (secrets) request.passphrase = pass.value;
                const result = await post(request);
                if (result.status !== 200 || !result.value || result.value.format !== 'openthermostat-e32-backup') { fail(status, result); return; }
                const text = JSON.stringify(result.value, null, 2);
                const day = typeof result.value.created === 'string' ? result.value.created.slice(0, 10) : new Date().toISOString().slice(0, 10);
                const link = element('a', {href: URL.createObjectURL(new Blob([text], {type: 'application/json'})), download: 'openthermostat-e32-backup-' + day + '.json'});
                document.body.append(link); link.click(); link.remove();
                setTimeout(() => URL.revokeObjectURL(link.href), 60000);
                const missing = Array.isArray(result.value.not_included) ? result.value.not_included : [];
                status.replaceChildren(element('span', {text: t("Backup downloaded.") + ' '}));
                if (missing.length) status.append(element('span', {text: t("Not in this backup; enter these again after a restore:") + ' ' + missing.map(m => coded(reenter, m)).join(', ')}));
                pass.value = pass2.value = '';
            } catch (_) { fail(status, null); }
            finally { busy = false; controls(); }
        });
        picker.addEventListener('change', async () => {
            file = null; checked = null; summary.replaceChildren(); restoreStatus.textContent = ''; restorePassRow.hidden = true; controls();
            const chosen = picker.files && picker.files[0];
            if (!chosen) return;
            if (chosen.size > maxBytes) { restoreStatus.textContent = t(errors.backup_too_large); return; }
            try {
                const value = JSON.parse(await chosen.text());
                if (!value || typeof value !== 'object' || value.format !== 'openthermostat-e32-backup') { restoreStatus.textContent = t(errors.not_a_backup); return; }
                file = value;
                restorePassRow.hidden = !(value.secrets && typeof value.secrets === 'object');
                if (!restorePassRow.hidden) restoreStatus.textContent = t("This backup holds encrypted passwords and keys.");
            } catch (_) { restoreStatus.textContent = t("The file could not be read."); }
            finally { controls(); }
        });
        const request = action => {
            const value = {action, backup: file};
            if (restorePass.value) value.passphrase = restorePass.value;
            if (action === 'apply') value.fingerprint = checked.fingerprint;
            return value;
        };
        check.addEventListener('click', async () => {
            if (busy) return;
            if (!file) { restoreStatus.textContent = t("Choose a backup file first."); return; }
            busy = true; checked = null; controls(); summary.replaceChildren(); restoreStatus.textContent = t("Checking the backup…");
            try {
                const result = await post(request('validate'));
                if (result.status !== 200 || !result.value || result.value.valid !== true || typeof result.value.fingerprint !== 'string') { fail(restoreStatus, result); return; }
                const v = result.value, changes = Array.isArray(v.changes) ? v.changes : [];
                restoreStatus.textContent = '';
                summary.append(element('p', {className: 'mb-1', text: changes.length ? t("The backup is valid. These settings will change:") : t("Nothing changes: this E32 already has these settings.")}));
                if (changes.length) summary.append(element('ul', {}, ...changes.map(c => element('li', {},
                    element('strong', {text: label(c) + ': '}),
                    element('span', {text: c.hidden ? t("will change") : shown(c.from) + ' → ' + shown(c.to)})))));
                const notes = Array.isArray(v.warnings) ? v.warnings : [];
                if (notes.length) summary.append(element('p', {className: 'mb-1', text: t("Notes:")}), element('ul', {}, ...notes.map(n => element('li', {text: coded(warnings, n)}))));
                const again = Array.isArray(v.reenter) ? v.reenter : [];
                if (again.length) summary.append(element('p', {className: 'mb-1', text: t("Enter these again after the restore:") + ' ' + again.map(r => coded(reenter, r)).join(', ')}));
                if (v.restart) summary.append(element('p', {className: 'mb-1', text: t("The E32 restarts after the restore; sign in again afterwards.")}));
                checked = changes.length ? v : null;
            } catch (_) { fail(restoreStatus, null); }
            finally { busy = false; controls(); }
        });
        apply.addEventListener('click', async () => {
            if (busy || !checked) return;
            busy = true; controls(); restoreStatus.textContent = t("Restoring…");
            try {
                const result = await post(request('apply'));
                if (result.status !== 201 || !result.value || result.value.applied !== true) { checked = null; fail(restoreStatus, result); return; }
                const v = result.value;
                if ((v.language === 'en' || v.language === 'nl') && window.OpenThermostatLanguage && v.language !== window.OpenThermostatLanguage.language)
                    document.cookie = 'ot_ui_lang=' + v.language + '; Path=/; Max-Age=31536000; SameSite=Strict';
                summary.replaceChildren();
                restoreStatus.replaceChildren(element('p', {className: 'mb-1', text: t("Settings restored.")}));
                if (v.restart_scheduled) restoreStatus.append(element('p', {className: 'mb-1', text: fill("The E32 restarts in about {v} seconds. Sign in again afterwards.", v.restart_in_s)}));
                else if (v.restart) restoreStatus.append(element('p', {className: 'mb-1', text: t("Restart the E32 to use all restored settings.")}));
                const again = Array.isArray(v.reenter) ? v.reenter : [];
                if (again.length) restoreStatus.append(element('p', {className: 'mb-1', text: t("Enter these again after the restore:") + ' ' + again.map(r => coded(reenter, r)).join(', ')}));
                checked = null; restorePass.value = '';
            } catch (_) { checked = null; fail(restoreStatus, null); }
            finally { busy = false; controls(); }
        });
        controls();
    }
    window.ConfigBackupPage = Object.freeze({mount, messages: Object.freeze([...new Set(messages)])});
})();
