// Transport for the inputs used by the original wC(bp)/GYc account producer.
// Authentication, account metadata, and the Linux capability result remain in
// their extracted original implementations. The original renderer decides when
// to read account info. No token crosses to the renderer.
module.exports = function createAccountContext({authClient, globalState, readOriginalAccountInfo, isCopilotApiAvailable}) {
 if (typeof readOriginalAccountInfo !== 'function' || typeof isCopilotApiAvailable !== 'function') {
  throw Error('Original account host services are required');
 }
 return {
  async readAuthInputs() {
   // uHn pairs these original methods. Its failure state stays in the renderer.
   const [response, authMethod, capability] = await Promise.all([
    authClient.getAccount().catch(() => null),
    authClient.getAuthMethod().catch(() => null),
    Promise.resolve().then(isCopilotApiAvailable).catch(() => ({available: false})),
   ]);
   const useCopilotAuthIfAvailable = globalState.get('use-copilot-auth-if-available') === true;
   return {
    response,
    authMethod: response == null ? null : authMethod,
    useCopilotAuthIfAvailable,
    isCopilotApiAvailable: capability?.available === true,
   };
  },
  readAccountInfo() { return readOriginalAccountInfo(); },
 };
};
