import test from 'node:test';
import assert from 'node:assert/strict';
import {parseScriptImport, projectFromScript} from '../src/scriptImport.js';
const fixture = () => ({type:'breeze-studio-script', version:1, name:'教程', defaults:{cfg:4,seed:42}, segments:[
 {title:'开场',text:'你好。',instruction:'欢快自然。'},
 {title:'提醒',text:'注意数值。',instruction:'稍慢，清晰。',cfg:3,seed:43},
]});

test('imports titles, narration, per-segment direction and parameters with local voice', () => {
 const input=fixture(); input.voice_id='foreign'; input.segments[0].voice_id='foreign'; input.segments[0].file='/outside/audio.wav';
 const script=parseScriptImport('\uFEFF'+JSON.stringify(input));
 let id=0; const p=projectFromScript(script,'local-voice',()=>String(++id));
 assert.equal(p.mode,'segments'); assert.equal(p.segments.length,2);
 assert.deepEqual(p.segments.map(s=>s.text),['你好。','注意数值。']);
 assert.deepEqual(p.segments[0].settings,{voice_id:'local-voice',instruction:'欢快自然。',cfg:4,seed:42});
 assert.deepEqual(p.segments[1].settings,{voice_id:'local-voice',instruction:'稍慢，清晰。',cfg:3,seed:43});
 assert.equal(p.segments[0].title,'开场'); assert.equal(p.segments[0].file,undefined);
 assert.equal(new Set([p.id,...p.segments.map(s=>s.id)]).size,3);
 assert.notStrictEqual(p.segments[0].settings,p.segments[1].settings);
 assert.deepEqual(input, {...fixture(),voice_id:'foreign',segments:[{...fixture().segments[0],voice_id:'foreign',file:'/outside/audio.wav'},fixture().segments[1]]});
});

test('empty direction defaults to clone parameters; directed speech defaults to CFG 4', () => {
 const input=fixture(); delete input.defaults; delete input.segments[0].instruction;
 delete input.segments[1].cfg; delete input.segments[1].seed;
 const p=projectFromScript(parseScriptImport(JSON.stringify(input)),'local');
 assert.equal(p.segments[0].settings.cfg,1); assert.equal(p.segments[1].settings.cfg,4);
 assert.equal(p.segments[1].settings.seed,42);
 assert.throws(()=>projectFromScript(parseScriptImport(JSON.stringify(input)),''),/参考音色/);
});

test('rejects malformed or unsupported files and invalid generation values', () => {
 for (const source of ['bad','null','[]','{}',JSON.stringify({...fixture(),version:2})]) assert.throws(()=>parseScriptImport(source));
 for (const patch of [{cfg:0},{cfg:21},{cfg:'4'},{seed:-1},{seed:1.5},{seed:4294967296},{text:''},{text:'文'.repeat(801)},{instruction:'文'.repeat(2001)}]) {
  const input=fixture();Object.assign(input.segments[0],patch);assert.throws(()=>parseScriptImport(JSON.stringify(input)));
 }
 for (const segments of [[],Array(201).fill(fixture().segments[0]),[null]]) assert.throws(()=>parseScriptImport(JSON.stringify({...fixture(),segments})));
});
