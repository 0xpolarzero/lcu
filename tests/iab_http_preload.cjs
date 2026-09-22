const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('fixtureHost', {
 subscribe(listener) {ipcRenderer.on('fixture:message', (_event, message) => listener(message));},
 httpFetch(message) {return ipcRenderer.invoke('fixture:http-fetch', message);},
 httpPull(requestId) {return ipcRenderer.invoke('fixture:http-pull', requestId);},
 httpCancel(requestId) {return ipcRenderer.invoke('fixture:http-cancel', requestId);},
 httpDispose(requestId) {return ipcRenderer.invoke('fixture:http-dispose', requestId);},
 report(value) {ipcRenderer.send('fixture:report', value);},
 waitContinue() {return new Promise(resolve => ipcRenderer.once('fixture:continue', resolve));},
});
