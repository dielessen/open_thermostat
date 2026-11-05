// Screenshots in the browser tests are evidence for a look by eye, not the assertion. Chromium now and then answers
// Page.captureScreenshot with "Unable to capture screenshot" while its compositor is still busy (GitHub's Ubuntu 26
// runners under load, 5 Nov 2026), and that one refusal failed a whole shard. shot(target, options) takes the same
// screenshot as target.screenshot(options), for a page or a locator, and tries again twice after a short pause when
// Chromium refuses it; any other error (a missing element, a bad path) still fails at once.
const pause=ms=>new Promise(done=>setTimeout(done,ms));
module.exports=async function shot(target,options){
 for(let attempt=1;;attempt++){
  try{return await target.screenshot(options);}
  catch(error){if(attempt>=3||!/capture screenshot/i.test(String(error&&error.message)))throw error;await pause(400*attempt);}
 }
};
