import {sweetVoice} from './voicePresets';
export async function api(path, body) {
  const r = await fetch('/api/' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d = await r.json(); if (!r.ok) throw new Error(d.error || '请求失败'); return d;
}
export const id = () => crypto.randomUUID().replaceAll('-','');
export const active = j => j && ['queued','loading','running'].includes(j.status);
export const labels = {queued:'等待生成',loading:'加载模型',running:'正在生成',completed:'完成',failed:'失败',cancelled:'已取消'};
export const engineLabels = {unloaded:'模型未加载',loading:'模型加载中',ready:'模型已加载',running:'正在配音',error:'模型需要检查'};
export function signature(s, defaults) { const p = s.settings || defaults; return JSON.stringify([s.text.trim(),p.voice_id,p.instruction.trim(),Number(p.cfg),Number(p.seed)]); }
export const latest = (jobs,p,s) => [...jobs].reverse().find(j=>j.project_id===p.id&&j.segment_id===s.id&&j.signature===signature(s,p.settings));
export const time = (s=0) => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
export function newProject() {
  const pid=id(); return {id:pid,name:'AI 工具教程 · 文件整理',mode:'single',pause_ms:300,
    settings:{voice_id:'',instruction:sweetVoice,cfg:4,seed:42},
    single:{id:'single-'+pid,title:'自由配音',text:'今天教你把一份资料整理成对比表。先上传文件，再输入提示词，最后检查结果。',settings:null},
    segments:[['开场','今天教你把一份资料整理成对比表。'],['上传文件','点击上传按钮，选择准备好的文件。'],['输入提示词','在输入框里写下你的整理要求。'],['检查结果','核对表格内容，确认后导出。']].map(([title,text])=>({id:id(),title,text,settings:null}))};
}
export const base64 = file => new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});
export function download(blob,name) {const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
