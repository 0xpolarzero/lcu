const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('lcuHost', {
 subscribe(listener) { ipcRenderer.on('lcu-iab:message', (_event, message) => listener(message)); },
 ready() { return ipcRenderer.invoke('lcu-iab:ready'); },
 permission(message) { return ipcRenderer.invoke('lcu-iab:permission',message); },
 persisted(message) {return ipcRenderer.invoke('lcu-iab:persisted',message);},
 account() {return ipcRenderer.invoke('lcu-iab:account');},
 accountInfo() {return ipcRenderer.invoke('lcu-iab:account-info');},
 oauthReply(message) {return ipcRenderer.invoke('lcu-iab:oauth-reply',message);},
 intl() {return ipcRenderer.invoke('lcu-iab:intl');},
 httpFetch(message) {return ipcRenderer.invoke('lcu-iab:http-fetch',message);},
 httpCancel(requestId) {return ipcRenderer.invoke('lcu-iab:http-cancel',requestId);},
 httpPull(requestId) {return ipcRenderer.invoke('lcu-iab:http-pull',requestId);},
 httpDispose(requestId) {return ipcRenderer.invoke('lcu-iab:http-dispose',requestId);},
 annotation(message) {return ipcRenderer.invoke('lcu-iab:annotation',message);},
 browserHost(message) {return ipcRenderer.invoke('lcu-iab:browser-host',message);},
 command(message) {return ipcRenderer.invoke('lcu-iab:command',message);},
 shortcutState(state) {return ipcRenderer.invoke('lcu-iab:shortcut-state',state);},
 pageCommand(message) {return ipcRenderer.invoke('lcu-iab:page-command',message);},
 settings(message) {return ipcRenderer.invoke('lcu-iab:settings',message);},
 assets() { return ipcRenderer.invoke('lcu-iab:assets'); },
 view(message) { return ipcRenderer.invoke('lcu-iab:view', message); }
});
