// Only transport/lifetime wiring is local. Cache, expiry, principal checks,
// workspace discovery and request aborts use unchanged original declarations.
const path = require('node:path');
module.exports = function createAuthClient(generatedDirectory, request, publish) {
 const {AuthTokenCache} = require(path.join(generatedDirectory, 'auth-provider.cjs'));
 return new class extends AuthTokenCache {
  constructor() {
   super();
   this.options={hostId:'local',hostConfig:{kind:'local'},transport:{kind:'stdio'}};
   this.initialized=false;this.connection=null;this.disposed=false;this.appServerVersion=null;
   this.messageDelivery={
    broadcastToWindows:message=>publish(message),
    // This adapter exposes no user-verification RPC. An unexpected response must
    // never manufacture or approve a request absent from the parent CLI stream.
    sendMessage(){throw Error('Original user-verification response transport is not connected');}
   };
  }
  connect(version) {this.appServerVersion=version;this.initialized=true;this.connection=this;}
  invalidate() {this.backendAuth.reset();this.clearAuthTokenCache();this.initialized=false;this.connection=null;}
  async ensureReady() {if(!this.initialized||this.disposed)throw Error('Original app-server bridge is not connected');}
  async sendInternalRequest(message,options) {
   await this.ensureReady();
   try {return {id:message.id,result:await request(message.method,message.params,options?.timeoutMs)};}
   catch(error) {return {id:message.id,error:{message:error.message}};}
  }
  async sendAppServerExtensionRequest(method,params) {await this.ensureReady();return request(method,params);}
  notify(message) {
   if(message.method==='account/updated'||message.method==='account/login/completed')this.clearAuthTokenCache();
  }
 };
};
