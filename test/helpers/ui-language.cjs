// Load the shipped message runtime (Home and page catalogues) with explicit DOM boundaries for unit fixtures.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
module.exports=function(language='en'){
 const context={window:{},document:{cookie:'ot_ui_lang='+language,documentElement:{},addEventListener(){}}};
 vm.createContext(context);
 for(const file of ['ui-messages.js','ui-messages-pages.js','ui-language.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../data/html',file),'utf8'),context,{filename:file});
 return {uiText:context.window.uiText,uiHtml:context.window.uiHtml};
};
