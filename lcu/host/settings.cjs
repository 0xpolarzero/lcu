// Paths and RPC wiring for the unchanged original desktop settings store.
const path = require('node:path');
const {app} = require('electron');
module.exports = function createSettings(generatedDirectory, request) {
 const {DesktopSettingsStore, createGlobalState} = require(path.join(generatedDirectory, 'bootstrap-provider.cjs'));
 const original = require(path.join(process.env.LCU_APPLICATION_PATH, 'resources/app.asar/.vite/build/src-C3YaUE83.js'));
 const {getFeatures} = require(path.join(generatedDirectory, 'provider.cjs'));
 const codexHome = original.yi();
 const globalState = createGlobalState(codexHome);
 const store = new DesktopSettingsStore(path.join(codexHome, 'config.toml'), globalState);
 const isDefaultBrowser = app.isDefaultProtocolClient('https');
 const subscriptions = [];
 return {
  store,
  globalState,
  options: {
   settingsStore: store,
   isDefaultBrowser: () => isDefaultBrowser,
   getCommandKeymapState: () => ({...original.Ct(), primaryNumberShortcutTarget: getFeatures().unifiedTabStrip ? store.getEffective(original.Ta.primaryNumberShortcutTarget.key) : undefined}),
   getDownloadDirectory: () => store.getEffective(original.ka.downloadDirectory.key) ?? app.getPath('downloads'),
   getPromptForUserDownloads: () => store.getEffective(original.ka.promptForDownloadLocation.key) ?? false,
  },
  async initialize() {
   const response = await request('config/read', {includeLayers: false, cwd: null});
   await store.initialize({config: response.config, batchWriteConfigValues: params => request('config/batchWrite', params)});
  },
  connectHost(host) {
   subscriptions.push(store.onDidChange(original.ka.disabledSiteAnnotationHostnames.key, () => host.refreshSiteAnnotationFeatures()));
  },
  async dispose() {
   for (const unsubscribe of subscriptions.splice(0)) unsubscribe();
   await store.flush();
   await globalState.flush();
  },
 };
};
