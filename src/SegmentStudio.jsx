import React,{useLayoutEffect,useRef,useState} from 'react';
import {Play,Plus,UploadSimple,ListBullets,ArrowClockwise,DotsThree,ArrowUp,ArrowDown,Scissors,Trash,ArrowsMerge,GearSix,PencilSimple,Stop,Microphone} from '@phosphor-icons/react';
import {active,id,labels,latest,time} from './api';
import {Wave,Modal} from './components';
import {AudioDock,effectiveOutput,outputLabel} from './AudioDock';
import {sweetVoice} from './voicePresets';

function ScriptText({value,...props}){
 const ref=useRef();
 useLayoutEffect(()=>{const el=ref.current;el.style.height='auto';el.style.height=el.scrollHeight+2+'px';},[value]);
 useLayoutEffect(()=>{const el=ref.current;let width=0;const observer=new ResizeObserver(()=>{if(el.clientWidth!==width){width=el.clientWidth;el.style.height='auto';el.style.height=el.scrollHeight+2+'px';}});observer.observe(el);return()=>observer.disconnect();},[]);
 return <textarea ref={ref} rows={1} value={value} {...props}/>;
}

export function SegmentStudio({p,server,update,edit,selected,setSelected,persist,notify,choose,create,generate,cancel,busy,connected,setModal,act}){
 const [scope,setScope]=useState('global'),[playRequest,setPlayRequest]=useState(0),[paramScope,setParamScope]=useState(null);
 const file=useRef();
 const current=p.segments.find(s=>s.id===selected),parameterRow=p.segments.find(s=>s.id===paramScope);
 const params=parameterRow?.settings||p.settings;
 const complete=p.segments.filter(s=>latest(server.jobs,p,s)?.status==='completed').length;
 const pending=server.jobs.filter(j=>active(j)&&j.project_id===p.id);
 function changeParams(patch){if(parameterRow)edit(parameterRow.id,{settings:{...params,...patch}});else update({settings:{...p.settings,...patch}});}
 function selectVoice(value){return {voice_id:value,cfg:value?1:4,instruction:value?'':sweetVoice};}
 function move(i,delta){const rows=[...p.segments];[rows[i],rows[i+delta]]=[rows[i+delta],rows[i]];update({segments:rows});}
 function listen(s){setSelected(s.id);setScope('segment');setPlayRequest(v=>v+1);}
 function action(e,fn){e.stopPropagation();e.currentTarget.closest('details')?.removeAttribute('open');fn();}
 return <div className="segment-studio">
  <header className="segment-page-head"><div><h1>分段配音</h1><div className="segment-project"><select aria-label="当前项目" value={p.id} onChange={e=>choose(e.target.value)}>{[...server.projects.filter(x=>x.id!==p.id),p].map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select><button className="icon-button" aria-label="重命名项目" onClick={()=>setModal({type:'rename',text:p.name})}><PencilSimple/></button><button className="icon-button" aria-label="新建项目" onClick={create}><Plus/></button></div></div><div className="segment-voice"><select aria-label="全篇音色" value={p.settings.voice_id} onChange={e=>update({settings:{...p.settings,...selectVoice(e.target.value)}})}><option value="">文字设计声音</option>{server.voices.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select><button className="icon-button" aria-label="全篇生成设置" onClick={()=>setParamScope('global')}><GearSix/></button></div></header>
  <div className="manuscript-tools"><button className="link" onClick={()=>update({mode:'single'})}>自由配音</button><span>共 {p.segments.length} 段 · 已完成 {complete} 段</span><div className="manuscript-actions"><button className="plain" onClick={()=>file.current.click()}><UploadSimple/>导入文案</button><button className="plain" onClick={()=>setModal({type:'split',text:p.segments.map(s=>s.text).join('\n\n')})}><ListBullets/>自动分段</button><button className="plain" onClick={()=>{const row={id:id(),title:`第 ${p.segments.length+1} 段`,text:'',settings:null,output:null};update({segments:[...p.segments,row]});setSelected(row.id);}}><Plus/>添加段落</button><button className={complete===p.segments.length?'plain':'teal'} disabled={busy||!connected} onClick={()=>{const rows=p.segments.filter(s=>latest(server.jobs,p,s)?.status!=='completed');generate((rows.length?rows:p.segments).map(s=>s.id));}}><Microphone/>{complete===p.segments.length?'重新生成全部':'生成配音'}</button>{pending.length>0&&<button className="plain danger" onClick={()=>act(()=>cancel(pending.map(j=>j.id)))}><Stop/>取消 {pending.length} 项</button>}</div></div>
  <input hidden ref={file} type="file" accept=".txt,.md" onChange={e=>{const f=e.target.files[0];if(f)act(async()=>{if(f.size>500000)throw new Error('文本文件过大。');setModal({type:'split',text:await f.text()});});e.target.value='';}}/>
  <div className="manuscript-list">{p.segments.map((s,i)=>{
   const job=latest(server.jobs,p,s),done=job?.status==='completed',old=server.jobs.some(j=>j.project_id===p.id&&j.segment_id===s.id&&j.status==='completed');
   const values=effectiveOutput(p,s);
   return <article key={s.id} className={'manuscript-row '+(selected===s.id?'is-selected':'')} onClick={()=>{setSelected(s.id);setScope('segment');}}>
    <span className="manuscript-number">{String(i+1).padStart(2,'0')}</span>
    <div className="manuscript-copy"><input className="manuscript-title" aria-label={`第 ${i+1} 段标题`} value={s.title} onChange={e=>edit(s.id,{title:e.target.value})}/><ScriptText aria-label={`第 ${i+1} 段文案`} value={s.text} onChange={e=>edit(s.id,{text:e.target.value})}/>{s.settings&&<button className="link" onClick={e=>{e.stopPropagation();setParamScope(s.id);}}>已单独设置音色 / 生成参数</button>}{job?.error&&<details className="error-detail"><summary>查看生成错误</summary><pre>{job.error}</pre></details>}</div>
    <div className="manuscript-audio"><button className="play-round" disabled={!done} aria-label={`试听第 ${i+1} 段`} onClick={e=>{e.stopPropagation();listen(s);}}><Play weight="fill"/></button><Wave peaks={done?job.peaks:[]}/><span className="time">{done?`≈ ${time(job.duration/values.speed)}`:job?labels[job.status]:old?'需重新生成':'未生成'}</span></div>
    <span className="manuscript-output" title={s.output?'此段输出设置独立于全篇':'跟随全篇：'+outputLabel(values)}>{s.output?<>单独设置<br/><small>{outputLabel(values)}</small></>:'跟随全篇'}</span>
    <details className="row-menu" onClick={e=>e.stopPropagation()}><summary aria-label={`第 ${i+1} 段更多操作`}><DotsThree/></summary><div className="dropdown">
     <button disabled={active(job)||busy} onClick={e=>action(e,()=>generate([s.id]))}><ArrowClockwise/>{done?'重新生成本段':'生成本段'}</button>
     <button onClick={e=>action(e,()=>setParamScope(s.id))}><GearSix/>本段生成设置</button>
     <button disabled={i===0} onClick={e=>action(e,()=>move(i,-1))}><ArrowUp/>上移</button><button disabled={i===p.segments.length-1} onClick={e=>action(e,()=>move(i,1))}><ArrowDown/>下移</button>
     <button onClick={e=>action(e,()=>setModal({type:'split-one',id:s.id,text:s.text.replace(/([。！？])/g,'$1\n')}))}><Scissors/>拆分段落</button>
     <button disabled={i===p.segments.length-1} onClick={e=>action(e,()=>{const next=p.segments[i+1];update({segments:p.segments.filter(x=>x.id!==next.id).map(x=>x.id===s.id?{...x,text:x.text+next.text}:x)});})}><ArrowsMerge/>合并下一段</button>
     <button className="danger" disabled={p.segments.length===1||active(job)} onClick={e=>action(e,()=>{if(confirm('删除此段文案？已生成录音保留在历史记录。')){update({segments:p.segments.filter(x=>x.id!==s.id)});if(selected===s.id)setSelected(p.segments.find(x=>x.id!==s.id).id);}})}><Trash/>删除段落</button>
    </div></details>
   </article>;
  })}</div>
  <AudioDock p={p} server={server} update={update} edit={edit} selected={current?.id} scope={scope} setScope={setScope} persist={persist} notify={notify} playRequest={playRequest}/>
  {paramScope&&<Modal title={parameterRow?`${parameterRow.title} · 生成设置`:'全篇生成设置'} close={()=>setParamScope(null)}><p className="muted">修改这些参数需要重新生成配音。语速、音量请在底部调节。</p><label>音色<select value={params.voice_id} onChange={e=>changeParams(selectVoice(e.target.value))}><option value="">通过文字设计声音</option>{server.voices.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select></label><label>{params.voice_id?'表达要求':'声音描述'}<textarea value={params.instruction} rows={4} onChange={e=>changeParams({instruction:e.target.value})}/></label><details className="advanced"><summary>高级生成参数</summary><label>CFG 引导强度<input type="number" min="0.1" max="20" step="0.1" value={params.cfg} onChange={e=>{if(e.target.validity.valid&&e.target.value)changeParams({cfg:Number(e.target.value)});}}/></label><label>随机种子<input type="number" min="0" max="4294967295" step="1" value={params.seed} onChange={e=>{if(e.target.validity.valid&&e.target.value)changeParams({seed:Number(e.target.value)});}}/></label></details><div className="modal-actions">{parameterRow?.settings&&<button onClick={()=>edit(parameterRow.id,{settings:null})}>恢复跟随全篇</button>}<button className="primary" onClick={()=>setParamScope(null)}>完成</button></div></Modal>}
 </div>;
}
