// Real window/service callbacks around the unchanged original dk queue.
const path = require('node:path');
const {app} = require('electron');

module.exports = function createDeepLinks(generatedDirectory, options) {
 const {createDeepLinkQueue} = require(path.join(generatedDirectory, 'bootstrap-provider.cjs'));
 for (const key of ['ensurePrimaryWindowVisible', 'getPrimaryWindow', 'navigateToRoute']) {
  if (typeof options[key] !== 'function') throw Error('Original deep-link host requires ' + key);
 }
 if (typeof options.errorReporter?.reportNonFatal !== 'function') throw Error('Original deep-link host requires an error reporter');
 return createDeepLinkQueue({
  app,
  isMacOS: false,
  platform: process.platform,
  ensurePrimaryWindowVisible: options.ensurePrimaryWindowVisible,
  getPrimaryWindow: options.getPrimaryWindow,
  navigateToRoute: options.navigateToRoute,
  initialArgv: options.initialArgv ?? process.argv,
  errorReporter: options.errorReporter,
  onDeepLinkReceived: options.onDeepLinkReceived,
  openHttpUrl: options.openHttpUrl,
 });
};
