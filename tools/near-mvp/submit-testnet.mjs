/* Explicit, single-attempt TESTNET deployment/registry relay. No existing wallets. */
import {Account,JsonRpcProvider,KeyPairSigner,actions,baseEncode} from 'near-api-js';
import {open,readFile,mkdir,writeFile} from 'node:fs/promises';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';
import path from 'node:path';
const [mode,credentialFile,folder,value,expectedCodeHash]=process.argv.slice(2);
if(!['deploy','register'].includes(mode)||!credentialFile||!folder||!value)throw new Error('Explicit testnet operation required');
const fd=await open(credentialFile,constants.O_RDONLY|constants.O_NOFOLLOW);
let credential;
try{const s=await fd.stat();if(!s.isFile()||(s.mode&0o077)!==0||s.size>8192)throw new Error('Private regular credential required');credential=JSON.parse(await fd.readFile('utf8'));}finally{await fd.close();}
if(credential.network!=='testnet'||!/^csl-registry-[0-9a-f]{12}\.testnet$/.test(credential.account_id))throw new Error('Fresh dedicated demo testnet account required');
const root=path.resolve(folder);await mkdir(root,{mode:0o700});
const receipt={schema_version:'near-testnet-submission.v1',network:'testnet',mode,signer_id:credential.account_id,
 receiver_id:credential.account_id,status:'preparing',automatic_retry:false,transaction_hash:null};
const save=()=>writeFile(path.join(root,'submission.json'),JSON.stringify(receipt,null,2),{mode:0o600});
await save();
class SingleAttemptProvider extends JsonRpcProvider {
 async sendJsonRpc(method,params){
  const response=await fetch('https://rpc.testnet.near.org',{method:'POST',redirect:'error',signal:AbortSignal.timeout(60000),
   headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:'decision-lab-testnet',method,params})});
  if(!response.ok)throw new Error('RPC HTTP failure');const text=await response.text();if(text.length>1048576)throw new Error('RPC response too large');
  const result=JSON.parse(text);if(result.error||!Object.hasOwn(result,'result'))throw new Error('RPC request failed');return result.result;
 }
}
try{
 const provider=new SingleAttemptProvider({url:'https://rpc.testnet.near.org'});
 const status=await provider.sendJsonRpc('status',[]);if(status.chain_id!=='testnet')throw new Error('Wrong network');
 const account=new Account(credential.account_id,provider,KeyPairSigner.fromSecretKey(credential.private_key));
 let txActions;
 if(mode==='deploy'){
  const code=await readFile(value);if(code.length>1048576||!code.subarray(0,4).equals(Buffer.from([0,97,115,109])))throw new Error('Bounded Wasm required');
  receipt.wasm_sha256=createHash('sha256').update(code).digest('hex');receipt.code_hash=baseEncode(createHash('sha256').update(code).digest());
  txActions=[actions.deployContract(code),actions.functionCall('new',{},30000000000000n,0n)];
 }else{
  if(!/^[0-9a-f]{64}$/.test(value)||!expectedCodeHash)throw new Error('Commitment and pinned code required');
  const state=await provider.sendJsonRpc('query',{request_type:'view_account',finality:'final',account_id:credential.account_id});
  if(state.code_hash!==expectedCodeHash)throw new Error('Deployed code changed');
  const version=await provider.sendJsonRpc('query',{request_type:'call_function',block_id:state.block_hash,account_id:credential.account_id,
   method_name:'contract_version',args_base64:Buffer.from('{}').toString('base64')});
  if(JSON.parse(Buffer.from(version.result).toString())!=='decision-lab-commitment-registry.v1')throw new Error('Wrong contract version');
  receipt.commitment=value;receipt.code_hash=expectedCodeHash;receipt.deposit_yocto='10000000000000000000000';
  txActions=[actions.functionCall('register_commitment',{commitment:value},30000000000000n,10000000000000000000000n)];
 }
 const signed=await account.createSignedTransaction({receiverId:credential.account_id,actions:txActions});
 receipt.transaction_hash=baseEncode(createHash('sha256').update(signed.transaction.encode()).digest());
 receipt.status='dispatching';await save();
 await writeFile(path.join(root,'signed-transaction.private.base64'),Buffer.from(signed.encode()).toString('base64'),{mode:0o600,flag:'wx'});
 const result=await provider.sendTransactionUntil(signed,'FINAL');
 await writeFile(path.join(root,'rpc-result.private.json'),JSON.stringify(result,null,2),{mode:0o600,flag:'wx'});
 receipt.status=typeof result.status==='object'&&Object.hasOwn(result.status,'SuccessValue')&&result.final_execution_status==='FINAL'?'final_response_received':'failed_or_nonfinal';
 receipt.final_execution_status=result.final_execution_status||null;await save();
 if(receipt.status!=='final_response_received')process.exitCode=2;
}catch{receipt.status=receipt.transaction_hash?'submission_unknown':'not_dispatched';receipt.error='testnet_operation_failed';await save();process.exitCode=2;}
console.log(JSON.stringify(receipt,null,2));
