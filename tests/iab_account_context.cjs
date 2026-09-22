// Credential-free comparison against the pinned original renderer mapper and
// Linux capability service. The account adapter only transports their inputs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const release = process.env.LCU_TEST_RELEASE || path.resolve(__dirname, '..');
const createAccountContext = require(path.join(release, 'lcu/host/account-context.cjs'));

const archive = fs.readFileSync(path.join(process.argv[2], 'resources/app.asar'));
const tree = JSON.parse(archive.subarray(16, 16 + archive.readUInt32LE(12)).toString());
const base = 8 + archive.readUInt32LE(4);
function original(folder, name) {
 let entry = tree;
 for (const part of folder.concat(name)) entry = entry.files[part];
 return archive.subarray(base + Number(entry.offset), base + Number(entry.offset) + entry.size).toString();
}
const renderer = original(['webview', 'assets'], 'app-initial-430deae5a13a.js');
const start = renderer.indexOf('function pHn()');
const end = renderer.indexOf('var gHn', start);
assert(start >= 0 && end > start, 'Pinned original account mapper is missing');
const {pHn, hHn} = vm.runInNewContext(renderer.slice(start, end) + ';({pHn,hHn})');
const main = original(['.vite', 'build'], 'main-DUHZj4_w.js');
const match = main.match(/"is-copilot-api-available":(async\(\)=>\(\{available:!1\}\))/);
assert(match, 'Pinned original Linux capability service is missing');
const isCopilotApiAvailable = vm.runInNewContext(match[1]);
const infoStart = main.indexOf('async function pT(');
const infoEnd = main.indexOf('var mT=', infoStart);
assert(infoStart >= 0 && infoEnd > infoStart, 'Pinned original account-info producer is missing');
const readOriginalAccountInfo = vm.runInNewContext(main.slice(infoStart, infoEnd) + ';pT', {
 Buffer, q: 'local', iEe: () => ({error() {}}),
});

async function run() {
 let metadataReads = 0;
 const noAccount = createAccountContext({
  authClient: {getAccount: async () => ({account: null}), getAuthMethod: async () => null},
  globalState: {get: () => false},
  isCopilotApiAvailable,
  readOriginalAccountInfo: async () => {metadataReads++; return null;},
 });
 const empty = await noAccount.readAuthInputs();
 assert.deepEqual(hHn(empty.response, {isPersonalAccessTokenAuth: empty.authMethod === 'personalAccessToken', useCopilotAuthIfAvailable: empty.useCopilotAuthIfAvailable, isCopilotApiAvailable: empty.isCopilotApiAvailable}), pHn());
 assert.equal(empty.isCopilotApiAvailable, false);
 assert.equal(metadataReads, 0);

 const account = {account: {type: 'chatgpt', email: 'fixture@example.invalid', planType: 'plus'}};
 const pat = createAccountContext({
  authClient: {getAccount: async () => account, getAuthMethod: async () => 'personalAccessToken'},
  globalState: {get: () => true},
  isCopilotApiAvailable,
  readOriginalAccountInfo: async () => {metadataReads++; throw Error('PAT must not read ChatGPT metadata');},
 });
 const patInputs = await pat.readAuthInputs();
 const patMap = hHn(patInputs.response, {isPersonalAccessTokenAuth: patInputs.authMethod === 'personalAccessToken', useCopilotAuthIfAvailable: patInputs.useCopilotAuthIfAvailable, isCopilotApiAvailable: patInputs.isCopilotApiAvailable});
 assert.equal(patMap.authMethod, 'personalAccessToken');
 assert.equal(patInputs.useCopilotAuthIfAvailable, true);
 assert.equal(patInputs.isCopilotApiAvailable, false);
 assert.equal(metadataReads, 0);

 const claims = {'https://api.openai.com/auth': {chatgpt_account_id: 'fixture-account', chatgpt_user_id: 'fixture-user', chatgpt_compute_residency: 'eu'}, 'https://api.openai.com/profile': {email: 'fixture@example.invalid'}};
 const syntheticToken = 'fixture.' + Buffer.from(JSON.stringify(claims)).toString('base64url') + '.fixture';
 const chatgpt = createAccountContext({
  authClient: {getAccount: async () => account, getAuthMethod: async () => 'chatgpt'},
  globalState: {get: () => false},
  isCopilotApiAvailable,
  readOriginalAccountInfo: () => readOriginalAccountInfo({getConnection(hostId) {
   assert.equal(hostId, 'local');
   return {getAuthToken: async () => syntheticToken};
  }}),
 });
 const chatgptInputs = await chatgpt.readAuthInputs();
 const chatgptMap = hHn(chatgptInputs.response, {isPersonalAccessTokenAuth: chatgptInputs.authMethod === 'personalAccessToken', useCopilotAuthIfAvailable: chatgptInputs.useCopilotAuthIfAvailable, isCopilotApiAvailable: chatgptInputs.isCopilotApiAvailable});
 assert.equal(chatgptMap.authMethod, 'chatgpt');
 const info = await chatgpt.readAccountInfo();
 assert.equal(info.computeResidency, 'eu');
 assert.equal(info.accountId, 'fixture-account');
 assert.equal(info.hasChatGptToken, true);
 const noTokenInfo = await readOriginalAccountInfo({getConnection: () => ({getAuthToken: async () => null})});
 assert.equal(noTokenInfo.computeResidency, null);
 assert.equal(noTokenInfo.hasChatGptToken, false);

 const failedAccount = createAccountContext({
  authClient: {getAccount: async () => {throw Error('fixture account failure');}, getAuthMethod: async () => 'personalAccessToken'},
  globalState: {get: () => false}, isCopilotApiAvailable,
  readOriginalAccountInfo: async () => {throw Error('unexpected metadata request');},
 });
 const failedInputs = await failedAccount.readAuthInputs();
 assert.equal(failedInputs.response, null);
 assert.equal(failedInputs.authMethod, null);
 assert.equal(pHn().authMethod, null, 'Original uHn uses pHn when account read fails');

 const failedMethod = createAccountContext({
  authClient: {getAccount: async () => account, getAuthMethod: async () => {throw Error('fixture auth status failure');}},
  globalState: {get: () => false}, isCopilotApiAvailable,
  readOriginalAccountInfo: async () => null,
 });
 assert.equal((await failedMethod.readAuthInputs()).authMethod, null, 'Original fHn treats auth method read failure as null');
 console.log(JSON.stringify({originalLinuxCopilotService: 'PASS', absentAccount: 'PASS', personalAccessToken: 'PASS', chatgptResidencyTransport: 'PASS', accountFailure: 'PASS', authMethodFailure: 'PASS', authenticatedRun: 'NOT EXERCISED'}));
}
run().catch(error => {console.error(error.stack); process.exitCode = 1;});
