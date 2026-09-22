// Original settings store and native CLI persistence; isolated fixture state only.
const assert=require('node:assert/strict');
const path=require('node:path');
const readline=require('node:readline');
const {app}=require('electron');
const pending=new Map();let sequence=0;
const input=readline.createInterface({input:process.stdin});
input.on('line',line=>{const reply=JSON.parse(line),entry=pending.get(reply.id);if(!entry)return;pending.delete(reply.id);reply.error?entry.reject(Error(reply.error)):entry.resolve(reply.result);});
function request(method,params){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});process.stdout.write(JSON.stringify({fixtureRequest:id,method,params})+'\n');});}
app.whenReady().then(async()=>{
 let settings;
 try {
  const createSettings=require(process.env.LCU_SETTINGS_MODULE);
  const generated=path.dirname(process.env.LCU_IAB_PROVIDER_PATH);
  settings=createSettings(generated,request);
  assert.equal(settings.options.getDownloadDirectory(),'/fixture-downloads-before');
  assert.equal(settings.options.getPromptForUserDownloads(),true);
  assert.equal(settings.options.isDefaultBrowser(),app.isDefaultProtocolClient('https'));
  assert.deepEqual(settings.options.getCommandKeymapState().bindings,[{command:'closeTab',key:'Ctrl+Alt+W'}]);
  let refreshed=0;
  settings.connectHost({refreshSiteAnnotationFeatures(){refreshed++;}});
  await settings.initialize();
  assert.throws(()=>settings.store.set('browser-download-prompt-enabled','invalid'));
  settings.store.set('browser-download-directory','/fixture-downloads-after');
  settings.store.set('browser-download-prompt-enabled',false);
  settings.store.set('browser-disabled-site-annotation-hostnames',['example.test']);
  await settings.store.flush();
  assert.equal(refreshed,1);
  const reopened=createSettings(generated,request);
  assert.equal(reopened.options.getDownloadDirectory(),'/fixture-downloads-after');
  assert.equal(reopened.options.getPromptForUserDownloads(),false);
  assert.deepEqual(reopened.store.getEffective('browser-disabled-site-annotation-hostnames'),['example.test']);
  await reopened.dispose();
  await settings.dispose();settings=null;
  process.stdout.write(JSON.stringify({fixtureResult:{persistedSettings:'PASS',keymap:'PASS',schemaValidation:'PASS',annotationSettingNotification:'PASS',defaultBrowserRead:'PASS'}})+'\n');
 }catch(error){console.error(error.stack);process.exitCode=1;}
 finally{if(settings)await settings.dispose();input.close();app.exit(process.exitCode||0);}
});
