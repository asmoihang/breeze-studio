import React,{useEffect,useRef,useState} from 'react';
import {ArrowCounterClockwise,DownloadSimple} from '@phosphor-icons/react';
import {api,download,latest} from './api';
import {Player} from './components';

export const defaultOutput={speed:1,volume:1};
export const effectiveOutput=(p,s)=>s?.output||p.output||defaultOutput;
export const outputLabel=v=>`${Number(v.speed).toFixed(2)}× · ${Math.round(v.volume*100)}%`;

function OutputNumber({value,min,max,step,label,onCommit,disabled,decimals=0}){
 const [draft,setDraft]=useState(Number(value).toFixed(decimals));
 useEffect(()=>setDraft(Number(value).toFixed(decimals)),[value,decimals]);
 function commit(){
  const n=Number(draft);
  if(draft!==''&&Number.isFinite(n)&&n>=min&&n<=max)onCommit(n);
  else setDraft(Number(value).toFixed(decimals));
 }
 return <input aria-label={label} type="number" min={min} max={max} step={step} value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}}/>;
}

export function AudioDock({p,server,update,edit,selected,scope,setScope,persist,notify,playRequest=0}){
 const [variant,setVariant]=useState('adjusted'),[preview,setPreview]=useState(null),[failure,setFailure]=useState(null),[exporting,setExporting]=useState(false),[retry,setRetry]=useState(0);
 const segmented=p.mode==='segments',row=segmented?p.segments.find(s=>s.id===selected):p.single;
 const local=segmented&&scope==='segment'&&!!row;
 const rows=segmented?p.segments:[p.single],target=local?[row]:rows;
 const ready=target.length>0&&target.every(s=>latest(server.jobs,p,s)?.status==='completed');
 const allReady=rows.length>0&&rows.every(s=>latest(server.jobs,p,s)?.status==='completed');
 const values=effectiveOutput(p,local?row:null),index=p.segments.findIndex(s=>s.id===row?.id);
 const key=JSON.stringify([p.id,variant,local?row.id:null,p.pause_ms,target.map(s=>[latest(server.jobs,p,s)?.id,latest(server.jobs,p,s)?.status,effectiveOutput(p,s)])]);
 const context=useRef();context.current={p,persist,local,row,variant};
 useEffect(()=>{
  if(!ready)return;
  let stale=false;
  const timer=setTimeout(async()=>{
   const c=context.current;
   try{
    await c.persist(c.p);
    if(stale)return;
    const audio=await api('render',{project_id:c.p.id,segment_id:c.local?c.row.id:undefined,variant:c.variant});
    if(!stale){setPreview({key,...audio});setFailure(null);}
   }catch(e){if(!stale)setFailure({key,message:e.message});}
  },450);
  return()=>{stale=true;clearTimeout(timer);};
 },[key,ready,retry]);
 const audio=ready&&preview?.key===key?preview:null,error=ready&&failure?.key===key?failure.message:'';
 function change(patch){
  const output={...values,...patch};
  if(local)edit(row.id,{output});else update({output});
 }
 async function exportAudio(format,segmentOnly=false){
  setExporting(true);
  try{
   await persist(p);
   const response=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:p.id,format,variant,segment_id:segmentOnly?row.id:undefined})});
   if(!response.ok)throw new Error((await response.json()).error);
   download(await response.blob(),`${p.name}${segmentOnly?'-'+row.title:''}-${variant==='original'?'原始':'调整后'}.${format==='zip'?'zip':'wav'}`);
   notify('已导出'+(variant==='original'?'原始':'调整后')+'音频。');
  }catch(e){notify(e.message);}finally{setExporting(false);}
 }
 return <section className="audio-dock" aria-label="试听与调节">
  <div className="dock-heading"><h2>试听与调节</h2>{!segmented&&<span className="dock-current">当前配音</span>}{segmented&&<div className="dock-scope"><span>范围：</span><div className="segmented-control"><button className={!local?'selected':''} onClick={()=>setScope('global')}>全篇</button><button disabled={!row} className={local?'selected':''} onClick={()=>setScope('segment')}>第 {String(index+1).padStart(2,'0')} 段</button></div></div>}<button className="link dock-reset" disabled={exporting} onClick={()=>local?edit(row.id,{output:null}):update({output:{...defaultOutput}})}><ArrowCounterClockwise/>{local?'恢复跟随全篇':'恢复默认'}</button></div>
  <p className="dock-hint">{local?`当前仅调整第 ${String(index+1).padStart(2,'0')} 段${row.output?'。':'，正在跟随全篇。'}`:segmented?'调整所有跟随全篇的段落，单独设置的段落保持原样。':'调整当前配音的语速和音量。'}</p>
  <div className="dock-controls">
   <div className="output-control"><label htmlFor="output-speed">语速</label><input id="output-speed" type="range" min="0.5" max="2" step="0.01" value={values.speed} disabled={exporting} onChange={e=>change({speed:Number(e.target.value)})}/><div className="number-unit"><OutputNumber key={local?row.id:'global'} label="语速倍数" min={.5} max={2} step={.01} decimals={2} value={values.speed} disabled={exporting} onCommit={speed=>change({speed})}/><span>×</span></div></div>
   <div className="output-control"><label htmlFor="output-volume">音量</label><input id="output-volume" type="range" min="0" max="200" step="1" value={Math.round(values.volume*100)} disabled={exporting} onChange={e=>change({volume:Number(e.target.value)/100})}/><div className="number-unit"><OutputNumber key={local?row.id:'global'} label="音量百分比" min={0} max={200} step={1} value={Math.round(values.volume*100)} disabled={exporting} onCommit={volume=>change({volume:volume/100})}/><span>%</span></div></div>
  </div>
  {server.audio_output?.speed_available===false&&values.speed!==1&&variant==='adjusted'&&<p className="dock-warning">变速需安装 FFmpeg：在 WSL 运行 <code>sudo apt install ffmpeg</code>。原始音频和音量调整仍可使用。</p>}
  <div className="dock-playback">
   <div className="dock-player"><Player src={audio?.url} duration={audio?.duration||0} peaks={audio?.peaks||[]} notify={notify} disabled={!audio||exporting} playRequest={playRequest} exclusiveGroup="workbench"/>{!audio&&<span className="dock-loading" role="status">{error?'试听未就绪':ready?'正在准备试听…':'生成后可试听'}</span>}</div>
   <div className="segmented-control comparison" aria-label="试听版本"><button className={variant==='original'?'selected':''} onClick={()=>setVariant('original')}>原始</button><button className={variant==='adjusted'?'selected':''} onClick={()=>setVariant('adjusted')}>调整后</button></div>
   <select aria-label="试听和导出版本" value={variant} onChange={e=>setVariant(e.target.value)}><option value="adjusted">调整后音频</option><option value="original">原始音频</option></select>
   <button className="primary dock-export" disabled={!allReady||exporting} onClick={()=>exportAudio('wav')}><DownloadSimple/>{exporting?'正在导出…':segmented?'导出全篇':'导出配音'}</button>
  </div>
  {error&&<div className="dock-error" role="alert">{error}<button className="link" onClick={()=>{setFailure(null);setRetry(n=>n+1);}}>重试</button></div>}
  <div className="dock-foot"><p>原始音频已保留；试听效果同步用于导出。</p>{segmented&&<details className="export-options"><summary>更多导出选项</summary><label>段间停顿 <input type="number" min="0" max="10000" step="100" value={p.pause_ms} onChange={e=>{if(e.target.validity.valid)update({pause_ms:Number(e.target.value)});}}/> ms</label><div className="button-row"><button disabled={!row||latest(server.jobs,p,row)?.status!=='completed'||exporting} onClick={()=>exportAudio('wav',true)}>导出当前段</button><button disabled={!allReady||exporting} onClick={()=>exportAudio('zip')}>分段打包下载</button></div></details>}</div>
 </section>;
}
