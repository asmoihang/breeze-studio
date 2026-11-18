import React, {useEffect, useState} from 'react';
import {Sparkle, Play, Plus, Stop, DownloadSimple, ArrowClockwise, Stack, GearSix} from '@phosphor-icons/react';
import {api, active, labels, time} from './api';
import {Player} from './components';
import {voicePresets, sweetVoice, auditionText} from './voicePresets';

const storageKey = 'breeze-studio-voice-design-v1';
const initial = {name:'甜妹教程女声', instruction:sweetVoice, text:auditionText, cfg:4, seed:42, count:3};
function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && typeof saved.draft?.instruction === 'string' && typeof saved.draft?.text === 'string') {
      return {draft:{...initial, ...saved.draft}, batchId:saved.batchId || ''};
    }
  } catch { /* Private browsing may not permit persistent draft storage. */ }
  return {draft:initial, batchId:''};
}

export function VoiceDesigner({server, connected, refresh, notify, saveVoice, openLibrary, openSettings, cancel}) {
  const [saved] = useState(restore);
  const [draft, setDraft] = useState(saved.draft);
  const [batchId, setBatchId] = useState(saved.batchId);
  const [submitting, setSubmitting] = useState(false);
  const batches = server.designs || [];
  const batch = batches.find(d => d.id === batchId) || batches.at(-1);
  const jobs = (batch?.job_ids || []).map(id => server.jobs.find(j => j.id === id)).filter(Boolean);
  const waiting = jobs.filter(active);
  const completed = jobs.filter(j => j.status === 'completed');
  const ready = server.config.repo && server.config.model && server.config.python;
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify({draft, batchId})); } catch {}
  }, [draft, batchId]);
  function edit(patch) { setDraft(d => ({...d, ...patch})); }
  async function run(action) {
    setSubmitting(true);
    try { await action(); await refresh(); }
    catch (e) { notify(e.message); }
    finally { setSubmitting(false); }
  }
  function generate(e) {
    e.preventDefault();
    run(async () => {
      const result = await api('designs', draft);
      setBatchId(result.id);
      notify(`已加入 ${result.count} 个音色候选，将逐个生成。`);
    });
  }
  return <>
    <div className="page-title"><div><h1>音色设计</h1><p className="muted">描述你想要的声音，试听不同版本，把喜欢的那个存进音色库。</p></div><button onClick={openLibrary}><Stack/>我的音色库</button></div>
    <div className="voice-design-layout">
      <form className="design-form" onSubmit={generate}>
        <div className="design-section-heading"><span className="design-step">01</span><h2>描述你的声音</h2></div>
        <div className="voice-presets" aria-label="声音风格预设">
          {voicePresets.map(preset => <button key={preset.id} type="button" className={'voice-preset '+(draft.instruction===preset.instruction?'chosen':'')} aria-pressed={draft.instruction===preset.instruction} onClick={() => edit({name:preset.voiceName, instruction:preset.instruction})}><strong>{preset.name}</strong><small>{preset.note}</small></button>)}
        </div>
        <label>音色名称<input required maxLength={100} value={draft.name} onChange={e => edit({name:e.target.value})}/></label>
        <label>声音描述<textarea required rows={5} maxLength={2000} value={draft.instruction} onChange={e => edit({instruction:e.target.value})}/></label>
        <label>试听文案<textarea required rows={4} maxLength={800} value={draft.text} onChange={e => edit({text:e.target.value})}/></label>
        <p className="help">先用相同文案比较音色。建议用 50～180 字的完整句子，涵盖你平时的教程表达。</p>
        <div className="design-numbers">
          <label>候选数量<select value={draft.count} onChange={e => edit({count:Number(e.target.value)})}>{[1,3,5].map(n => <option key={n} value={n}>{n} 个候选</option>)}</select></label>
          <label>起始种子<input type="number" min="0" max={4294967296-draft.count} step="1" required value={draft.seed} onChange={e => edit({seed:e.target.value===''?'':Number(e.target.value)})}/></label>
          <label>CFG<input type="number" min="0.1" max="20" step="0.1" required value={draft.cfg} onChange={e => edit({cfg:e.target.value===''?'':Number(e.target.value)})}/></label>
        </div>
        <p className="help">只改变候选的随机种子，其余参数一致。先从 CFG 4 开始，数值越高不代表音质越好。</p>
        {!ready&&<div className="notice"><span>先连接已有的 Breeze 模型。</span><button type="button" className="link" onClick={openSettings}><GearSix/>连接模型</button></div>}
        <button className="primary design-submit" disabled={submitting||!connected||!ready}><Sparkle/>{submitting?'正在提交…':`生成 ${draft.count} 个候选`}</button>
        <p className="help">每个候选依次生成。选中的录音会成为参考音色，模型权重保持不变。</p>
      </form>
      <section className="design-results" aria-label="音色候选">
        <div className="design-section-heading"><span className="design-step">02</span><h2>试听，选一个喜欢的</h2>{batch&&<span className="muted small">{completed.length} / {jobs.length} 已完成</span>}</div>
        {batches.length>0&&<div className="design-batch-bar"><label>设计记录<select value={batch?.id||''} onChange={e=>setBatchId(e.target.value)}>{[...batches].reverse().map(b=><option key={b.id} value={b.id}>{b.name} · {b.created.replace('T',' ').slice(0,19)}</option>)}</select></label><button type="button" className="plain" onClick={()=>edit({name:batch.name,text:batch.text,instruction:batch.settings.instruction,cfg:batch.settings.cfg,seed:batch.settings.seed,count:batch.count})}>复用这组设置</button></div>}
        {batch&&<details className="batch-description"><summary>查看这批候选的文案与声音描述</summary><p>{batch.text}</p><p className="muted">{batch.settings.instruction}</p></details>}
        {waiting.length>0&&<div className="design-queue"><span>{waiting.length} 个候选在队列中</span><button className="plain danger" disabled={submitting} onClick={()=>run(()=>cancel(waiting.map(j=>j.id)))}><Stop/>取消本批未完成任务</button></div>}
        {!batch?<div className="design-empty"><Sparkle size={38}/><h3>从一组甜美女声开始</h3><p>挑选预设，生成几个候选。<br/>先听清晰度，再听甜美程度和自然感。</p><span>试听满意 → 保存音色 → 用于整篇教程</span></div>:<div className="candidate-list">{jobs.map((job,i)=>{
          const voices=server.voices.filter(v=>v.source_job_id===job.id);
          return <article className="voice-candidate" key={job.id}>
            <div className="candidate-heading"><span className="candidate-number">{String(i+1).padStart(2,'0')}</span><div><h3>候选 {i+1}</h3><small className="muted">种子 {job.settings.seed} · CFG {job.settings.cfg}</small></div><span className={'badge '+job.status}>{labels[job.status]}</span></div>
            {job.status==='completed'?<><Player src={`/api/audio/job/${job.id}`} peaks={job.peaks} duration={job.duration} notify={notify}/><div className="candidate-actions">{voices.length?<span className="saved-voice-note">已保存为「{voices[0].name}」</span>:<span className="muted small">{time(job.duration)} · 试听后选用</span>}<a className="button" href={`/api/audio/job/${job.id}?download=1`}><DownloadSimple/>WAV</a><button className="teal" onClick={()=>saveVoice(job)}><Plus/>{voices.length?'另存音色':'保存为音色'}</button></div></>:<>
              {active(job)?<p className="candidate-progress" role="status">{job.status==='running'?`正在生成${job.seconds?` · 已合成 ${job.seconds.toFixed(1)} 秒`:''}`:job.status==='loading'?'正在加载模型…':'等待前面的任务完成…'}</p>:<p className="muted small">{job.status==='cancelled'?'已取消，可以按原参数重试。':'生成未成功，已保留这次的声音描述和种子。'}</p>}
              {job.error&&<details className="error-detail"><summary>查看失败原因</summary><pre>{job.error}</pre></details>}
              {['failed','cancelled'].includes(job.status)&&<button disabled={submitting||!connected} onClick={()=>run(()=>api('designs/retry',{id:batch.id,job_id:job.id}))}><ArrowClockwise/>重试这个候选</button>}
            </>}
          </article>;
        })}</div>}
        <p className="design-listening-tip"><Play size={17}/>保存前听一遍完整录音，确认没有漏字、重复或异常停顿；参考文字应与实际录音一致。</p>
      </section>
    </div>
  </>;
}
