// Isolated auth error/cache tests. No credentials or network are used.
const assert=require('node:assert/strict');
const path=require('node:path');
const {app}=require('electron');
const generated=process.env.LCU_IAB_PROVIDER_PATH;
const createAuthClient=require(path.join(process.env.LCU_TEST_RELEASE,'lcu/host/auth.cjs'));
const {readAccountInfo,isCopilotApiAvailable}=require(generated);
app.whenReady().then(async()=>{
 try {
  let calls=0,fail=false;
  const client=createAuthClient(path.dirname(generated),async(method,params)=>{
   assert.equal(method,'getAuthStatus');assert.equal(params.includeToken,true);calls++;
   if(fail)throw Error('fixture request failure');
   return {authMethod:null,authToken:null,requiresOpenaiAuth:true};
  },()=>{throw Error('Unexpected credential publication');});
  client.connect('0.155.0-alpha.9.2');
  assert.equal(await client.getBackendRequestAuth({refreshToken:false}),null);
  assert.equal(await client.getBackendRequestAuth({refreshToken:false}),null);
  assert.equal(calls,1,'Original negative auth result should be cached');
  const previous=client.backendAuth.controller.signal;
  client.notify({method:'account/updated'});
  assert.equal(previous.aborted,true,'Original auth principal signal must abort');
  assert.equal(await client.getBackendRequestAuth({refreshToken:false}),null);
  assert.equal(calls,2,'Account update must clear original token cache');
  client.clearAuthTokenCache();fail=true;
  await assert.rejects(client.getBackendRequestAuth({refreshToken:false}),/fixture request failure/);
  client.invalidate();
  await assert.rejects(client.getBackendRequestAuth({refreshToken:false}),/not connected/);
  assert.deepEqual(await isCopilotApiAvailable(),{available:false},'Use the original pinned Linux capability service');
  const claims={'https://api.openai.com/auth':{chatgpt_account_id:'fixture-account',chatgpt_user_id:'fixture-user',chatgpt_compute_residency:'eu',chatgpt_plan_type:'plus'},'https://api.openai.com/profile':{email:'fixture@example.invalid'}};
  const token='fixture.'+Buffer.from(JSON.stringify(claims)).toString('base64url')+'.fixture';
  const metadataClient=createAuthClient(path.dirname(generated),async method=>{
   assert.equal(method,'getAuthStatus');
   return {authMethod:'chatgpt',authToken:token,requiresOpenaiAuth:true};
  },()=>{});
  metadataClient.connect('0.155.0-alpha.9.2');
  const info=await readAccountInfo({getConnection(hostId){assert.equal(hostId,'local');return metadataClient;}});
  assert.equal(info.accountId,'fixture-account');
  assert.equal(info.userId,'fixture-user');
  assert.equal(info.computeResidency,'eu');
  assert.equal(info.hasChatGptToken,true);
  assert.equal(await metadataClient.getAuthMethod(),'chatgpt');
  metadataClient.invalidate();
  console.log(JSON.stringify({originalAuthCache:'PASS',missingAccount:'PASS',requestError:'PASS',accountInvalidation:'PASS',disconnect:'PASS',originalAccountInfo:'PASS',originalAuthMethod:'PASS',originalLinuxCopilotService:'PASS',authenticatedRouting:'NOT EXERCISED'}));
 }catch(error){console.error(error.stack);process.exitCode=1;}
 finally{app.exit(process.exitCode||0);}
});
