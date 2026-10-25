'use strict';
(() => {
    // BEGIN GENERATED BOILER CATALOG
    const catalog = [{"id":"none","name":"No boiler selected yet","kind":"none","image":null},{"id":"nefit-ecomline-classic","name":"Nefit Ecomline Classic","kind":"local","image":null},{"id":"nefit-ecomline-classic-hrc-22h","name":"Nefit Ecomline Classic HRC 22H","kind":"local","image":null},{"id":"emsesp-product-8","name":"CS5800i, CS6800i, WLW176i, WLW186i","kind":"heatpump","image":null},{"id":"emsesp-product-11","name":"Greenstar 2000","kind":"family","image":null},{"id":"emsesp-product-12","name":"C1200W","kind":"family","image":null},{"id":"emsesp-product-16","name":"CS5800iG","kind":"family","image":null},{"id":"emsesp-product-64","name":"BK13/BK15, Smartline, GB1*2","kind":"family","image":null},{"id":"emsesp-product-72","name":"Logano GB1*5, Logamatic MC10","kind":"family","image":null},{"id":"emsesp-product-81","name":"Cascade CM10","kind":"module","image":null},{"id":"emsesp-product-84","name":"Logamax Plus GB022","kind":"family","image":null},{"id":"emsesp-product-95","name":"Condens, Logamax/Logomatic, Cerapur Top, Greenstar, Generic HT3","kind":"family","image":null},{"id":"emsesp-product-115","name":"Topline, GB162","kind":"family","image":null},{"id":"emsesp-product-121","name":"Cascade MCM10","kind":"module","image":null},{"id":"emsesp-product-122","name":"Proline","kind":"family","image":"https://bbqkees-electronics.nl/wp-content/uploads/ems-devices/nefit/boilers/Nefit-proline-hrc-ems.jpg","imageSource":"https://bbqkees-electronics.nl/ketels-nefit/?lang=nl","imageCredit":"BBQKees","imageModel":"Nefit ProLine HRC (EMS)"},{"id":"emsesp-product-123","name":"GB*72, Trendline, Cerapur, Greenstar Si","kind":"family","image":null},{"id":"emsesp-product-131","name":"GB212","kind":"family","image":null},{"id":"emsesp-product-132","name":"GC7000F","kind":"family","image":null},{"id":"emsesp-product-133","name":"Logano GB125/KB195i, Logamatic MC110","kind":"family","image":null},{"id":"emsesp-product-154","name":"Greenstar 30Ri Compact","kind":"family","image":null},{"id":"emsesp-product-155","name":"Suprapur-o","kind":"family","image":null},{"id":"emsesp-product-167","name":"Cerapur Aero","kind":"family","image":null},{"id":"emsesp-product-168","name":"Hybrid Heatpump","kind":"heatpump","image":null},{"id":"emsesp-product-170","name":"Logano GB212","kind":"family","image":null},{"id":"emsesp-product-172","name":"Enviline, Compress 6000AW, Hybrid 3000-7000iAW, SupraEco/Geo 5xx, WLW196i/WSW196i","kind":"heatpump","image":null},{"id":"emsesp-product-173","name":"Geo 5xx","kind":"heatpump","image":null},{"id":"emsesp-product-195","name":"Condens 5000i, Greenstar 8000/GC9800IW, GB192i*2","kind":"family","image":null},{"id":"emsesp-product-203","name":"Logamax U122, Cerapur","kind":"family","image":null},{"id":"emsesp-product-206","name":"Ecomline Excellent","kind":"family","image":null},{"id":"emsesp-product-208","name":"Logamax Plus, GB192, Condens GC9000, Greenstar ErP","kind":"family","image":null},{"id":"emsesp-product-210","name":"Cascade MC400","kind":"module","image":null},{"id":"emsesp-product-211","name":"EasyControl Adapter","kind":"module","image":null},{"id":"emsesp-product-219","name":"Greenstar HIU, Logamax kompakt WS170","kind":"family","image":null},{"id":"emsesp-product-234","name":"Logamax Plus GB122, Condense 2300, Junkers Cerapur GC2200W","kind":"family","image":null},{"id":"emsesp-doc-bk13-bk15","name":"BK13, BK15","kind":"family","image":null},{"id":"emsesp-doc-gb125-gb135-gb1x2i-gb162-gbx72-gb212-gb162-gb192","name":"GB125, GB135, GB1x2i, GB162, GBx72, GB212, GB162, GB192, GB122, GB192i.2","kind":"family","image":null},{"id":"emsesp-doc-mc10","name":"MC10","kind":"family","image":null},{"id":"emsesp-doc-cascade-cm10-mc400","name":"Cascade CM10, MC400","kind":"family","image":null},{"id":"emsesp-doc-logano","name":"Logano","kind":"family","image":null},{"id":"emsesp-doc-logamax-plus-gb022-u122","name":"Logamax Plus GB022, U122","kind":"family","image":null},{"id":"emsesp-doc-logamatic-mc10-mc110","name":"Logamatic MC10, MC110","kind":"family","image":null},{"id":"emsesp-doc-condens-2500-gc9000","name":"Condens 2500, GC9000","kind":"family","image":null},{"id":"emsesp-doc-bosch-junkers-cerapur-gc2200w","name":"Bosch/Junkers Cerapur GC2200W","kind":"family","image":null},{"id":"emsesp-doc-logomatic","name":"Logomatic","kind":"family","image":null},{"id":"emsesp-doc-bosch-junkers-cerapur-top-aero","name":"Bosch/Junkers Cerapur Top, Aero","kind":"family","image":null},{"id":"emsesp-doc-bosch-junkers-cerapur-zsb-14-3-a","name":"Bosch/Junkers Cerapur ZSB 14-3 A","kind":"family","image":null},{"id":"emsesp-doc-greenstar-si-30ri-compact-erp-hiu-8000","name":"Greenstar Si, 30Ri Compact, ErP, HIU, 8000","kind":"family","image":null},{"id":"emsesp-doc-nefit-topline-trendline","name":"Nefit Topline, Trendline","kind":"family","image":null},{"id":"emsesp-doc-nefit-proline","name":"Nefit Proline","kind":"family","image":"https://bbqkees-electronics.nl/wp-content/uploads/ems-devices/nefit/boilers/Nefit-proline-hrc-ems.jpg","imageSource":"https://bbqkees-electronics.nl/ketels-nefit/?lang=nl","imageCredit":"BBQKees","imageModel":"Nefit ProLine HRC (EMS)"},{"id":"emsesp-doc-nefit-smartline","name":"Nefit Smartline","kind":"family","image":"https://bbqkees-electronics.nl/wp-content/uploads/ems-devices/nefit/boilers/Nefit-smartline-ems.jpg","imageSource":"https://bbqkees-electronics.nl/ketels-nefit/?lang=nl","imageCredit":"BBQKees","imageModel":"Nefit SmartLine"},{"id":"emsesp-doc-gc7000f-gc700iw-gc9800iw","name":"GC7000F, GC700iW, GC9800IW","kind":"family","image":null},{"id":"emsesp-doc-kb195i","name":"KB195i","kind":"family","image":null},{"id":"emsesp-doc-enviline","name":"Enviline","kind":"family","image":null},{"id":"emsesp-doc-compress-6000aw","name":"Compress 6000AW","kind":"family","image":null},{"id":"emsesp-doc-hybrid-3000-7000iaw","name":"Hybrid 3000-7000iAW","kind":"family","image":null},{"id":"emsesp-doc-supraeco","name":"SupraEco","kind":"family","image":null},{"id":"emsesp-doc-wlw196i-wsw196i","name":"WLW196i, WSW196i","kind":"family","image":null},{"id":"emsesp-doc-condens-2300-5000i","name":"Condens 2300, 5000i","kind":"family","image":null},{"id":"nefit-trendline-ii","name":"Nefit TrendLine II","kind":"family","image":"https://www.nefit-bosch.nl/media/country_pool/professioneel/productafbeeldingen/cv-ketels/nefit_trendlineii.jpg","imageSource":"https://www.nefit-bosch.nl/professioneel/installateurs/promotiemateriaal-installateurs/","imageCredit":"Nefit Bosch","imageModel":"Nefit TrendLine II"},{"id":"buderus-gb162","name":"Buderus Logamax plus GB162","kind":"family","image":"https://www.bosch-homecomfort.com/us/media/country_pool/service_support/discontinued-products/gb162_550x310.webp","imageSource":"https://www.bosch-homecomfort.com/us/en/residential/service-support/discontinued-products/discontinued-boilers/buderus-gb162/","imageCredit":"Bosch Home Comfort","imageModel":"Buderus Logamax plus GB162"}];
    // END GENERATED BOILER CATALOG
    const models = Object.freeze(Object.fromEntries(catalog.map(model => [model.id, {
        ...model,
        name: model.id === 'none' ? uiText("No boiler selected yet") : model.name,
        note: model.kind === 'local'
            ? uiText("Classic monitoring via the Bosch EasyControl Adapter; control is still in beta development.")
            : model.kind === 'none' ? '' : uiText("Listed by EMS-ESP. Monitoring and control in OpenThermostat have not been verified for this model.")
    }])));
    function appendPicture(parent, model, width, height) {
        if (!model?.image) return;
        const image = document.createElement('img');
        image.alt = model.imageModel;
        image.width = width; image.height = height;
        image.referrerPolicy = 'no-referrer';
        image.addEventListener('error', () => image.remove(), {once: true});
        image.src = model.image; parent.append(image);
    }
    function appendImageSource(parent, model) {
        if (!model?.imageSource) return;
        const credit = document.createElement('p'), link = document.createElement('a');
        link.href = model.imageSource; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = uiText("Product image source") + ': ' + model.imageCredit;
        credit.append(link); parent.append(credit);
    }
    let selected = null, generation = 0;
    async function request(options={}) {
        const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),5000);
        try {
            const response=await fetch('/config/boiler-display',{cache:'no-store',...options,signal:controller.signal});
            if(!response.ok)throw Error('request');
            return await response.json();
        } finally {clearTimeout(deadline);}
    }
    function valid(data) { return data && typeof data.model === 'string' && Object.hasOwn(models, data.model); }
    function renderHome() {
        const box = document.getElementById('boiler-home');
        if (!box) return;
        box.replaceChildren();
        const model = selected === null ? null : models[selected];
        appendPicture(box, model, 92, 140);
        const text = document.createElement('div'), title = document.createElement('h2');
        title.textContent = model ? model.name : uiText("Boiler selection unavailable");
        text.append(title);
        const note = document.createElement('p');
        note.textContent = model?.note || uiText("Choose your boiler under Settings → My boiler.");
        text.append(note);
        appendImageSource(text, model);
        const link = document.createElement('a'); link.className = 'boiler-setup-link'; link.href = '#'; link.textContent = uiText("Set up boiler");
        link.addEventListener('click', event => {event.preventDefault(); window.loadNativePage('boiler_display');});
        text.append(link); box.append(text);
    }
    async function load() {
        const own = ++generation;
        try {
            const data = await request();
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
        let saving=false, uncertain=false;
        const message = root.querySelector('[role=status]'), preview = root.querySelector('figure');
        function picture() {
            preview.replaceChildren(); const model = models[select.value];
            appendPicture(preview, model, 130, 198);
            const note = document.createElement('figcaption');
            note.textContent = model?.note || '';
            preview.append(note);
            appendImageSource(preview, model);
        }
        const groups = new Map();
        const groupLabels = {
            local: uiText("Existing local models"),
            family: uiText("EMS-ESP model families"),
            heatpump: uiText("EMS-ESP heat pumps"),
            module: uiText("EMS-ESP modules and adapters")
        };
        for (const [id,model] of Object.entries(models)) {
            const option = document.createElement('option');option.value=id;option.textContent=model.name;
            if (model.kind === 'none') {select.append(option);continue;}
            if (!groups.has(model.kind)) {
                const group = document.createElement('optgroup');group.label = groupLabels[model.kind];
                groups.set(model.kind,group);select.append(group);
            }
            groups.get(model.kind).append(option);
        }
        select.addEventListener('change',picture);
        root.addEventListener('submit',async event => {
            event.preventDefault();const model = select.value;if (saving||uncertain||!root.isConnected||!Object.hasOwn(models,model)) return;
            saving=true;
            const own = ++generation;select.disabled = save.disabled = true;message.textContent = uiText("Saving…");
            try {
                const result = await request({method:'POST',
                    headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
                if (!valid(result) || result.model !== model) throw Error('readback');
                const actual=await request();
                if(!valid(actual)||actual.model!==model)throw Error('readback');
                if (own === generation) {selected = model;renderHome();}
                if (root.isConnected) message.textContent = uiText("Boiler selection saved. Your boiler appears on the home page.");
            } catch (_) {
                uncertain=true;
                if (own === generation) {selected = null;renderHome();}
                if (root.isConnected) message.textContent = uiText("Saving could not be confirmed. Reload to check the saved selection.");
            } finally {saving=false;if (root.isConnected){select.disabled=false;save.disabled=uncertain;}}
        });
        select.disabled = save.disabled = true;
        try {
            const model = await load();if (!root.isConnected || !Object.hasOwn(models,model)) return;
            select.value = model;picture();select.disabled = save.disabled = false;message.textContent = '';
        } catch (_) {if (root.isConnected) message.textContent = uiText("The boiler selection could not be loaded. Open My boiler again to retry.");}
    }
    const style = document.createElement('style');
    style.textContent = '.boiler-summary{overflow-wrap:anywhere;display:flex;align-items:center;gap:24px;background:#f3f7f7;border:1px solid #d9e5e3;border-radius:14px;padding:20px;margin:0 0 20px;max-width:100%;box-sizing:border-box}.boiler-summary img{object-fit:contain;flex:none}.boiler-summary h2{font-size:1.3rem;margin:0 0 8px}.boiler-summary p{margin:0 0 10px;color:#526a70;overflow-wrap:anywhere}.boiler-summary a{color:#076b60}.boiler-summary>div{min-width:0}@media(max-width:400px){.boiler-summary{gap:14px;padding:14px}.boiler-summary img{width:66px;height:100px}.boiler-summary h2{font-size:1.1rem}}';
    document.head.append(style);
    window.BoilerDisplay = {load,mountHome,settings};
    document.addEventListener('DOMContentLoaded', () => {void load().catch(()=>{});});
})();
