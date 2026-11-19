import React,{useLayoutEffect,useRef,useState} from 'react';
import {Play,Plus,UploadSimple,ArrowClockwise,DotsThree,DotsSixVertical,ArrowUp,ArrowDown,Scissors,Trash,ArrowsMerge,PencilSimple,Stop,ArrowRight} from '@phosphor-icons/react';
import {active,id,labels,latest,time} from './api';
import {Wave} from './components';
import {AudioDock,effectiveOutput,outputLabel} from './AudioDock';
import {sweetVoice} from './voicePresets';
import {parseScriptImport} from './scriptImport';

function ScriptText({value,...props}){
 const ref=useRef();
 useLayoutEffect(()=>{const el=ref.current;el.style.height='auto';el.style.height=el.scrollHeight+2+'px';},[value]);
 useLayoutEffect(()=>{const el=ref.current;let width=0;const observer=new ResizeObserver(()=>{if(el.clientWidth!==width){width=el.clientWidth;el.style.height='auto';el.style.height=el.scrollHeight+2+'px';}});observer.observe(el);return()=>observer.disconnect();},[]);
 return <textarea ref={ref} rows={1} value={value} {...props}/>;
}

export function Workbench({p,server,update,edit,selected,setSelected,scope,setScope,persist,notify,choose,create,generate,cancel,busy,connected,setModal,act,saveState,live,setLive,stopLive,voiceModal}){
 const [playRequest,setPlayRequest]=useState(0);
 const file=useRef(),drag=useRef();
 const segmented=p.mode==='segments',current=p.segments.find(s=>s.id===selected);
 const local=segmented&&scope==='segment'&&!!current,inherit=local&&!current.settings;
 const params=(local&&current.settings)||p.settings;
 const index=p.segments.findIndex(s=>s.id===selected),number=String(index+1).padStart(2,'0');
 const rows=segmented?p.segments:[p.single],result=latest(server.jobs,p,p.single);
 const pending=server.jobs.filter(j=>active(j)&&j.project_id===p.id);
 const todo=rows.filter(s=>!active(latest(server.jobs,p,s))&&latest(server.jobs,p,s)?.status!=='completed');
 function changeParams(patch){if(local)edit(current.id,{settings:{...params,...patch}});else update({settings:{...p.settings,...patch}});}
 function selectVoice(value){changeParams({voice_id:value,cfg:value?1:4,instruction:value?'':sweetVoice});}
 function switchMode(mode){if(p.mode===mode)return;stopLive();setPlayRequest(0);update({mode});setScope('global');}
 function select(s){setSelected(s.id);setScope('segment');}
 function move(from,to){if(from===to)return;const next=[...p.segments],a=next.findIndex(s=>s.id===from),b=next.findIndex(s=>s.id===to);if(a<0||b<0)return;next.splice(b,0,next.splice(a,1)[0]);update({segments:next});}
 function action(e,fn){e.stopPropagation();e.currentTarget.closest('details')?.removeAttribute('open');fn();}
 const scopeButtons=<div className="segmented-control work-scope" aria-label="设置范围"><button className={!local?'selected':''} aria-pressed={!local} onClick={()=>setScope('global')}>全篇</button><button disabled={!current} className={local?'selected':''} aria-pressed={local} onClick={()=>setScope('segment')}>第 {number} 段</button></div>;
 return <div className={"workbench "+(segmented?"is-segmented":"is-free")}>
  <header className="work-head"><div className="work-title"><h1>配音工作台</h1><div className="mode-switch" aria-label="配音模式"><button aria-pressed={!segmented} className={!segmented?'selected':''} onClick={()=>switchMode('single')}>自由配音</button><button aria-pressed={segmented} className={segmented?'selected':''} onClick={()=>switchMode('segments')}>分段配音</button></div></div><div className="work-project"><span>项目：</span><select aria-label="当前项目" value={p.id} onChange={e=>{stopLive();setScope('global');choose(e.target.value);}}>{[...server.projects.filter(x=>x.id!==p.id),p].map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select><button className="icon-button" aria-label="重命名项目" onClick={()=>setModal({type:'rename',text:p.name})}><PencilSimple/></button><button className="icon-button" aria-label="新建项目" onClick={()=>{stopLive();create();}}><Plus/></button><span className="work-saved" role="status">{saveState}</span></div></header>
  <div className="work-columns">
   <section className="work-editor" aria-label={segmented?'段落文案':'配音文案'}>
    <div className="work-editor-head"><h2>{segmented?'段落文案':'配音文案'}</h2>{segmented&&<span className="segment-count">{p.segments.length} 段</span>}<button className="link import-script" onClick={()=>file.current.click()}><UploadSimple/>{segmented?'导入文案':'导入文本'}</button>{segmented&&<button onClick={()=>{const row={id:id(),title:`第 ${p.segments.length+1} 段`,text:'',settings:null,output:null};update({segments:[...p.segments,row]});select(row);}} disabled={p.segments.length>=200}><Plus/>添加</button>}</div>
    <input hidden ref={file} type="file" accept=".txt,.md,.json" onChange={e=>{const f=e.target.files[0];if(f)act(async()=>{if(f.size>500000)throw new Error('文本文件过大。');const value=await f.text();if(/\.json$/i.test(f.name)){const script=parseScriptImport(value);setModal({type:'import-script',script,voice_id:p.settings.voice_id});}else if(segmented)setModal({type:'split',text:value});else update({single:{...p.single,text:value}});});e.target.value='';}}/>
    {!segmented?<><textarea className="free-script" aria-label="配音文案" value={p.single.text} onChange={e=>update({single:{...p.single,text:e.target.value}})} placeholder="输入要朗读的教程文案…"/><div className="free-status"><label className="check"><input type="checkbox" checked={live} onChange={e=>{setLive(e.target.checked);if(!e.target.checked)stopLive();}}/>生成时试听</label><span>{p.single.text.length} / 800 字</span>{result&&<span role="status">{labels[result.status]}</span>}{result?.status==='completed'&&<button className="link" onClick={()=>voiceModal(result)}>保存为音色</button>}</div>{result?.error&&<details className="error-detail"><summary>查看生成错误</summary><pre>{result.error}</pre></details>}</>:<div className="work-rows">{p.segments.map((s,i)=>{
     const job=latest(server.jobs,p,s),done=job?.status==='completed',old=server.jobs.some(j=>j.project_id===p.id&&j.segment_id===s.id&&j.status==='completed');
     const values=effectiveOutput(p,s);
     return <article key={s.id} className={'work-row '+(selected===s.id?'is-selected':'')} onClick={()=>select(s)} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();move(drag.current,s.id);drag.current=null;}}>
      <span className="work-drag" draggable onDragStart={e=>{drag.current=s.id;e.dataTransfer.setData('text/plain',s.id);}} onDragEnd={()=>{drag.current=null;}} title="拖动排序，也可通过更多菜单上移或下移"><DotsSixVertical/></span>
      <div className="work-copy"><input aria-label={`第 ${i+1} 段标题`} className="work-row-title" value={s.title} onChange={e=>edit(s.id,{title:e.target.value})}/><ScriptText aria-label={`第 ${i+1} 段文案`} value={s.text} onChange={e=>edit(s.id,{text:e.target.value})}/>{s.settings&&<small className="row-custom">声音已单独设置</small>}{job?.error&&<details className="error-detail"><summary>查看生成错误</summary><pre>{job.error}</pre></details>}</div>
      <details className="row-menu" onClick={e=>e.stopPropagation()}><summary aria-label={`第 ${i+1} 段更多操作`}><DotsThree/></summary><div className="dropdown">
       <button disabled={active(job)||busy||!connected} onClick={e=>action(e,()=>generate([s.id]))}><ArrowClockwise/>{done?'重新生成本段':'生成本段'}</button>
       {done&&<button onClick={e=>action(e,()=>voiceModal(job))}>保存为音色</button>}
       <button disabled={i===0} onClick={e=>action(e,()=>move(s.id,p.segments[i-1].id))}><ArrowUp/>上移</button><button disabled={i===p.segments.length-1} onClick={e=>action(e,()=>move(s.id,p.segments[i+1].id))}><ArrowDown/>下移</button>
       <button onClick={e=>action(e,()=>setModal({type:'split-one',id:s.id,text:s.text.replace(/([。！？])/g,'$1\n')}))}><Scissors/>拆分段落</button>
       <button disabled={i===p.segments.length-1} onClick={e=>action(e,()=>{const next=p.segments[i+1];update({segments:p.segments.filter(x=>x.id!==next.id).map(x=>x.id===s.id?{...x,text:x.text+next.text}:x)});})}><ArrowsMerge/>合并下一段</button>
       <button className="danger" disabled={p.segments.length===1||active(job)} onClick={e=>action(e,()=>{if(confirm('删除此段文案？已生成录音保留在历史记录。')){update({segments:p.segments.filter(x=>x.id!==s.id)});if(selected===s.id)setSelected(p.segments.find(x=>x.id!==s.id).id);}})}><Trash/>删除段落</button>
      </div></details>
      <div className="work-row-audio"><button className="play-round" disabled={!done} aria-label={`试听第 ${i+1} 段`} onClick={e=>{e.stopPropagation();select(s);setPlayRequest(n=>n+1);}}><Play weight="fill"/></button><Wave peaks={done?job.peaks:[]}/><span className="time">{done?`≈ ${time(job.duration/values.speed)}`:job?labels[job.status]:old?'需重新生成':'未生成'}</span><button className="row-output" aria-label={`调节第 ${i+1} 段语速和音量`} title={s.output?'单独设置：'+outputLabel(values):'跟随全篇：'+outputLabel(values)} onClick={()=>select(s)}>{s.output?outputLabel(values):'跟随全篇'}</button></div>
     </article>;
    })}</div>}
    <div className="work-generate"><span>自由稿与分段稿分别保存。</span><div>{segmented?<button disabled={!current||busy||!connected||active(latest(server.jobs,p,current))} onClick={()=>generate([current.id])}>重新生成第 {number} 段</button>:<button disabled={!p.single.text.trim()} onClick={()=>setModal({type:'split',text:p.single.text})}>复制并分段<ArrowRight/></button>}<button className="primary" disabled={busy||!connected||(!segmented&&(active(result)||!p.single.text.trim()))||(segmented&&!todo.length)} onClick={()=>generate(segmented?todo.map(s=>s.id):[p.single.id])}>{segmented?'生成待配音段落':result?.status==='completed'?'重新生成配音':'生成配音'}</button></div></div>
    {pending.length>0&&<div className="work-queue" role="status"><span>{pending.length} 项任务进行中</span><button className="link danger" onClick={()=>act(()=>cancel(pending.map(j=>j.id)))}><Stop/>取消任务</button></div>}
   </section>
   <aside className="work-settings" aria-label="声音设置"><h2>声音设置</h2>{segmented&&<>{scopeButtons}<div className="voice-inheritance">{local?<><span>{inherit?'当前段声音跟随全篇':'当前段声音已单独设置'}</span><button className="link" onClick={()=>edit(current.id,{settings:inherit?{...p.settings}:null})}>{inherit?'单独设置':'恢复跟随全篇'}</button></>:<span>应用于所有跟随全篇的段落</span>}</div></>}
    <label>音色</label><div className="work-voice"><select aria-label="配音音色" disabled={inherit} value={params.voice_id} onChange={e=>selectVoice(e.target.value)}><option value="">文字设计声音</option>{server.voices.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select>{params.voice_id?<button className="teal" onClick={()=>{const voice=server.voices.find(v=>v.id===params.voice_id);if(voice)setModal({type:'voice-audio',voice});else notify('此音色已不存在，请重新选择。');}}><Play weight="fill"/>试听参考音色</button>:<button className="teal" onClick={()=>voiceModal()}><Plus/>添加音色</button>}</div>
    <label>{params.voice_id?'表达要求':'声音描述'}<textarea aria-label={params.voice_id?'表达要求':'声音描述'} disabled={inherit} value={params.instruction} placeholder={params.voice_id?'留空使用纯音色克隆':'描述想要的声音…'} rows={4} onChange={e=>changeParams({instruction:e.target.value})}/></label>
    <details className="advanced"><summary>高级生成参数</summary><fieldset disabled={inherit}><label>参数预设<select value="" onChange={e=>{if(e.target.value==='sweet')changeParams({cfg:4,instruction:sweetVoice,voice_id:''});if(e.target.value==='clone')changeParams({cfg:1,instruction:''});}}><option value="">自定义设置</option><option value="sweet">甜美女声 · 教程</option><option value="clone" disabled={!params.voice_id}>纯音色克隆</option></select></label><label>CFG 引导强度<input aria-label="CFG 引导强度" type="number" min="0.1" max="20" step="0.1" value={params.cfg} onChange={e=>{if(e.target.validity.valid&&e.target.value)changeParams({cfg:Number(e.target.value)});}}/></label><label>随机种子<input aria-label="随机种子" type="number" min="0" max="4294967295" step="1" value={params.seed} onChange={e=>{if(e.target.validity.valid&&e.target.value)changeParams({seed:Number(e.target.value)});}}/></label></fieldset></details>
    {segmented&&<p className="settings-help">修改声音设置后，需要重新生成{local?'该段':'相关段落'}。</p>}
   </aside>
  </div>
  <AudioDock key={p.mode} {...{p,server,update,edit,selected,scope,setScope,persist,notify,playRequest}}/>
 </div>;
}
