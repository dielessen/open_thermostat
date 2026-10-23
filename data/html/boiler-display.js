'use strict';
(() => {
    const models = Object.freeze({
        none: {name: uiText("No boiler selected yet")},
        'nefit-ecomline-classic': {name: 'Nefit Ecomline Classic', image: '/boiler-nefit-ecomline.svg',
            note: uiText("Classic monitoring via the Bosch EasyControl Adapter; control is still in beta development.")},
    });
    let selected = null, generation = 0;
    function valid(data) { return data && typeof data.model === 'string' && Object.hasOwn(models, data.model); }
    function renderHome() {
        const box = document.getElementById('boiler-home');
        if (!box) return;
        box.replaceChildren();
        const model = selected === null ? null : models[selected];
        if (model?.image) {
            const image = document.createElement('img');
            image.src = model.image; image.alt = uiText("Illustration of a Nefit Ecomline Classic boiler");
            image.width = 92; image.height = 140; box.append(image);
        }
        const text = document.createElement('div'), title = document.createElement('h2');
        title.textContent = model ? model.name : uiText("Boiler selection unavailable");
        text.append(title);
        const note = document.createElement('p');
        note.textContent = model?.note || uiText("Choose your boiler under Settings → My boiler.");
        text.append(note);
        const link = document.createElement('a'); link.href = '#'; link.textContent = uiText("Set up boiler");
        link.addEventListener('click', event => {event.preventDefault(); window.loadNativePage('boiler_display');});
        text.append(link); box.append(text);
    }
    async function load() {
        const own = ++generation;
        try {
            const response = await fetch('/config/boiler-display', {cache:'no-store'});
            if (!response.ok) throw Error('read');
            const data = await response.json();
            if (!valid(data)) throw Error('model');
            if (own === generation) { selected = data.model; renderHome(); }
            return own === generation ? data.model : selected;
        } catch (error) {
            if (own === generation) { selected = null; renderHome(); }
            throw error;
        }
    }
    function mountHome(parent) {
        let box = document.getElementById('boiler-home');
        if (!box) {box = document.createElement('section');box.id = 'boiler-home';parent.prepend(box);}
        box.className = 'boiler-summary'; renderHome();
    }
    async function settings(root) {
        const select = root.querySelector('select'), save = root.querySelector('button[type=submit]');
        const message = root.querySelector('[role=status]'), preview = root.querySelector('figure');
        function picture() {
            preview.replaceChildren(); const model = models[select.value];
            if (model?.image) {
                const image = document.createElement('img');image.src = model.image;
                image.alt = uiText("Illustration of the selected boiler");image.width = 130;image.height = 198;
                preview.append(image);
            }
        }
        for (const [id,model] of Object.entries(models)) {
            const option = document.createElement('option');option.value=id;option.textContent=model.name;select.append(option);
        }
        select.addEventListener('change',picture);
        root.addEventListener('submit',async event => {
            event.preventDefault();const model = select.value;if (!Object.hasOwn(models,model)) return;
            const own = ++generation;select.disabled = save.disabled = true;message.textContent = 'Opslaan…';
            try {
                const response = await fetch('/config/boiler-display', {method:'POST',
                    headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
                if (!response.ok) throw Error('save');
                const result = await response.json();
                if (!valid(result) || result.model !== model) throw Error('readback');
                if (own === generation) {selected = model;renderHome();}
                if (root.isConnected) message.textContent = uiText("Boiler selection saved. Your boiler appears on the home page.");
            } catch (_) {
                if (own === generation) {selected = null;renderHome();}
                if (root.isConnected) message.textContent = uiText("Saving could not be confirmed. Reload to check the saved selection.");
            } finally {if (root.isConnected) select.disabled = save.disabled = false;}
        });
        select.disabled = save.disabled = true;
        try {
            const model = await load();if (!root.isConnected || !Object.hasOwn(models,model)) return;
            select.value = model;picture();select.disabled = save.disabled = false;message.textContent = '';
        } catch (_) {if (root.isConnected) message.textContent = uiText("The boiler selection could not be loaded. Open My boiler again to retry.");}
    }
    const style = document.createElement('style');
    style.textContent = '.boiler-summary{display:flex;align-items:center;gap:24px;background:#f3f7f7;border:1px solid #d9e5e3;border-radius:14px;padding:20px;margin:0 0 20px;max-width:100%;box-sizing:border-box}.boiler-summary img{object-fit:contain;flex:none}.boiler-summary h2{font-size:1.3rem;margin:0 0 8px}.boiler-summary p{margin:0 0 10px;color:#526a70;overflow-wrap:anywhere}.boiler-summary a{color:#076b60}.boiler-summary>div{min-width:0}@media(max-width:400px){.boiler-summary{gap:14px;padding:14px}.boiler-summary img{width:66px;height:100px}.boiler-summary h2{font-size:1.1rem}}';
    document.head.append(style);
    window.BoilerDisplay = {load,mountHome,settings};
    document.addEventListener('DOMContentLoaded', () => {void load().catch(()=>{});});
})();
