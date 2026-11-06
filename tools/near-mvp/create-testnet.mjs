/* Creates one fresh dedicated TESTNET account. Never reads existing wallets. */
import {KeyPair} from 'near-api-js';
import {mkdir,writeFile} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import path from 'node:path';
const folder=process.argv[2];
if(!folder)throw new Error('Explicit new private output folder required');
const root=path.resolve(folder);await mkdir(root,{mode:0o700});
const accountId=`csl-registry-${randomBytes(6).toString('hex')}.testnet`;
const key=KeyPair.fromRandom('ed25519');
await writeFile(path.join(root,'credential.private.json'),JSON.stringify({network:'testnet',account_id:accountId,
 public_key:key.getPublicKey().toString(),private_key:key.toString()},null,2),{mode:0o600,flag:'wx'});
const receipt={schema_version:'near-faucet-attempt.v1',network:'testnet',account_id:accountId,
 endpoint:'https://helper.testnet.near.org/account',status:'dispatching',automatic_retry:false};
await writeFile(path.join(root,'faucet-receipt.json'),JSON.stringify(receipt,null,2),{mode:0o600,flag:'wx'});
try{
 const response=await fetch(receipt.endpoint,{method:'POST',redirect:'error',signal:AbortSignal.timeout(30000),
  headers:{'Content-Type':'application/json'},body:JSON.stringify({newAccountId:accountId,newAccountPublicKey:key.getPublicKey().toString()})});
 receipt.http_status=response.status;
 if(!response.ok){receipt.status='failed';receipt.error='faucet_rejected';process.exitCode=2;}
 else{const text=await response.text();if(text.length>1048576)throw new Error('bounded helper response required');
  const data=JSON.parse(text);receipt.status='response_received';receipt.transaction_hash=data?.transaction?.hash||data?.transaction_outcome?.id||null;}
}catch{receipt.status='unknown';receipt.error='faucet_transport_or_response';process.exitCode=2;}
await writeFile(path.join(root,'faucet-receipt.json'),JSON.stringify(receipt,null,2),{mode:0o600});
console.log(JSON.stringify(receipt,null,2));
