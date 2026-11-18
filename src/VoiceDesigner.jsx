import React, {useEffect, useState} from 'react';
import {Sparkle, Stop, DownloadSimple, ArrowClockwise, GearSix, ClockCounterClockwise, CaretDown, CheckCircle} from '@phosphor-icons/react';
import {api, active, labels} from './api';
import {Player, Modal} from './components';
import {voicePresets, sweetVoice, auditionText} from './voicePresets';

const storageKey = 'breeze-studio-voice-design-v1';
const initial = {name:'甜妹教程女声', instruction:sweetVoice, text:auditionText, cfg:4, seed:42, count:3};
function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && typeof saved.draft?.instruction === 'string' && typeof saved.draft?.text === 'string') {
      return {draft:{...initial, ...saved.draft}, batchId:saved.batchId || ''};
    }
  } catch { /* Draft persistence is optional in private browsing. */ }
  return {draft:initial, batchId:''};
}

export function VoiceDesigner({server, connected, refresh, notify, saveVoice, openLibrary, openSettings, cancel}) {
  const [saved] = useState(restore);
  const [draft, setDraft] = useState(saved.draft);
  const [batchId, setBatchId] = useState(saved.batchId);
  const [selectedId, setSelectedId] = useState('');
  const [voiceName, setVoiceName] = useState(saved.draft.name);
  const [transcript, setTranscript] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const batches = server.designs || [];
  const batch = batches.find(d => d.id === batchId) || batches.at(-1);
  const jobs = (batch?.job_ids || []).map(id => server.jobs.find(j => j.id === id)).filter(Boolean);
  const waiting = jobs.filter(active);
  const selected = jobs.find(j => j.id === selectedId && j.status === 'completed');
  const existing = selected && server.voices.find(v => v.source_job_id === selected.id && v.name === voiceName.trim() && v.transcript === transcript.trim());
  const ready = server.config.repo && server.config.model && server.config.python;
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify({draft, batchId})); } catch {}
  }, [draft, batchId]);
  useEffect(() => { setSelectedId(''); setTranscript(''); setVoiceName(batch?.name || draft.name); }, [batch?.id]);
  function edit(patch) { setDraft(d => ({...d, ...patch})); }
  async function run(action) {
    setSubmitting(true);
    try { await action(); await refresh(); }
    catch (e) { notify(e.message); }
    finally { setSubmitting(false); }
  }
  function generate(e) {
    e.preventDefault();
    if (submitting || saving) return;
    run(async () => {
      const result = await api('designs', draft);
      setBatchId(result.id);
      notify(`已加入 ${result.count} 个音色候选，将逐个生成。`);
    });
  }
  function select(job) { setSelectedId(job.id); setTranscript(job.text); }
  async function save(e) {
    e.preventDefault();
    if (!selected || saving || existing) return;
    setSaving(true);
    try { await saveVoice(selected, {name:voiceName.trim(), transcript:transcript.trim()}); }
    catch (e) { notify(e.message); }
    finally { setSaving(false); }
  }
  function reuseBatch() {
    edit({name:batch.name, text:batch.text, instruction:batch.settings.instruction, cfg:batch.settings.cfg, seed:batch.settings.seed, count:batch.count});
    notify('已将这批候选的描述、文案和参数填入左侧。');
  }
  return <>
    <div className="page-title voice-design-title"><div><h1>音色设计</h1><p className="muted">写下想要的声音，试听后保存为专属音色。</p></div><button className="link design-history-button" disabled={saving} onClick={() => setShowHistory(true)}><ClockCounterClockwise/>历史方案</button></div>
    <div className="voice-design-layout">
      <form className="design-form" onSubmit={generate} onInvalid={e=>{const details=e.target.closest('details');if(details)details.open=true;}}>
        <h2 className="design-section-title">描述声音</h2>
        <div className="design-template-label" id="template-label">描述模板</div>
        <div className="voice-presets" role="group" aria-labelledby="template-label">
          {voicePresets.map(preset => <button key={preset.id} type="button" className={'voice-preset '+(draft.instruction===preset.instruction?'chosen':'')} aria-pressed={draft.instruction===preset.instruction} title={preset.note} onClick={() => edit({name:preset.voiceName, instruction:preset.instruction})}>{preset.name}</button>)}
        </div>
        <p className="design-template-help">点击只会填入描述，不代表固定音色。</p>
        <label className="design-description">声音描述<textarea required rows={4} maxLength={2000} value={draft.instruction} onChange={e => edit({instruction:e.target.value})}/></label>
        <label className="design-script">试听文案<textarea required rows={2} maxLength={800} value={draft.text} onChange={e => edit({text:e.target.value})}/></label>
        <div className="design-options">
          <div className="design-count" role="group" aria-label="生成数量"><span>生成数量</span>{[1,3,5].map(n => <button type="button" key={n} aria-pressed={draft.count===n} className={draft.count===n?'chosen':''} onClick={() => edit({count:n})}>{n}</button>)}</div>
          <details className="design-advanced">
            <summary>高级设置 <CaretDown/></summary>
            <div className="design-advanced-fields"><label>起始种子<input type="number" min="0" max={4294967296-draft.count} step="1" required value={draft.seed} onChange={e => edit({seed:e.target.value===''?'':Number(e.target.value)})}/></label><label>CFG<input type="number" min="0.1" max="20" step="0.1" required value={draft.cfg} onChange={e => edit({cfg:e.target.value===''?'':Number(e.target.value)})}/></label><p className="help">候选仅改变随机种子。建议从 CFG 4 开始，数值越高不代表音质越好。</p></div>
          </details>
        </div>
        {!ready&&<div className="notice design-model-notice"><span>连接本地模型后即可生成。</span><button type="button" className="link" onClick={openSettings}><GearSix/>连接模型</button></div>}
        <button className="primary design-submit" disabled={submitting||saving||!connected||!ready}><Sparkle/>{submitting?'正在提交…':`生成 ${draft.count} 个候选`}</button>
      </form>
      <section className="design-results" aria-label="试听候选">
        <h2 className="design-section-title">试听候选</h2>
        <p className="design-results-help">同一描述，不同声音；先听再选。</p>
        {waiting.length>0&&<div className="design-queue" role="status"><span>{waiting.length} 个候选待完成</span><button className="plain danger" disabled={submitting} onClick={()=>run(()=>cancel(waiting.map(j=>j.id)))}><Stop/>取消未完成任务</button></div>}
        {!batch?<div className="design-empty"><Sparkle size={34}/><h3>你的声音，从一句描述开始</h3><p>在左侧填写描述和试听文案，<br/>生成后在这里试听、比较。</p></div>:<div className="candidate-list" role="group" aria-label="选择一个候选声音">{jobs.map((job,i)=>{
          const voices=server.voices.filter(v=>v.source_job_id===job.id);
          const letter=String.fromCharCode(65+i);
          return <article className={'voice-candidate '+(selectedId===job.id?'selected':'')} key={job.id}>
            <div className="candidate-main"><label className="candidate-select"><input type="radio" name="voice-candidate" aria-label={`选择候选 ${letter}`} checked={selectedId===job.id} disabled={job.status!=='completed'||saving} onChange={()=>select(job)}/><span>候选 {letter}</span></label>
              {job.status==='completed'?<Player src={`/api/audio/job/${job.id}`} peaks={job.peaks} duration={job.duration} notify={notify} compact exclusiveGroup="voice-design"/>:<span className={'candidate-status '+job.status} role="status">{labels[job.status]}{job.status==='running'&&job.seconds?` · ${job.seconds.toFixed(1)} 秒`:''}</span>}
            </div>
            {job.status==='completed'?<div className="candidate-tools"><span>{voices.length?`已保存为「${voices[0].name}」`:''}</span><details><summary>参数</summary><span>种子 {job.settings.seed} · CFG {job.settings.cfg}</span></details><a className="link" href={`/api/audio/job/${job.id}?download=1`} aria-label={`下载候选 ${letter}`}><DownloadSimple/>WAV</a></div>:<div className="candidate-feedback">
              {job.error&&<details className="error-detail"><summary>查看失败原因</summary><pre>{job.error}</pre></details>}
              {['failed','cancelled'].includes(job.status)&&<button disabled={submitting||!connected} onClick={()=>run(()=>api('designs/retry',{id:batch.id,job_id:job.id}))}><ArrowClockwise/>重试这个候选</button>}
            </div>}
          </article>;
        })}</div>}
        <form className="design-save" onSubmit={save}>
          <label htmlFor="design-voice-name">音色名称</label>
          <div className="design-save-row"><input id="design-voice-name" required maxLength={100} value={voiceName} disabled={saving} onChange={e=>setVoiceName(e.target.value)} placeholder="例如：甜妹教程女声"/><button className="primary" disabled={!selected||saving||!connected||!voiceName.trim()||!transcript.trim()||!!existing}>{saving?'正在保存…':existing?<><CheckCircle/>已保存</>:'保存选中音色'}</button></div>
          <p className="help">{selected?'保存后可在配音工作台反复使用。':'先试听并选中一个候选，再保存音色。'}{existing&&<button type="button" className="link" onClick={openLibrary}>查看音色库</button>}</p>
          {selected&&<details className="design-transcript" key={selected.id}><summary>核对参考文字</summary><p className="help">听完录音后核对下方文字；如有漏字或重复，请按实际录音修正。</p><label><span className="sr-only">参考文字</span><textarea rows={3} maxLength={10000} required disabled={saving} value={transcript} onChange={e=>setTranscript(e.target.value)}/></label></details>}
        </form>
        {batch&&<details className="batch-description"><summary>本批描述与文案</summary><p>{batch.settings.instruction}</p><p>{batch.text}</p><button className="link" onClick={reuseBatch}>复用这组设置</button></details>}
      </section>
    </div>
    {showHistory&&<Modal title="历史方案" close={()=>setShowHistory(false)}>{!batches.length?<p className="muted">生成第一批候选后，方案会自动保存在这里。</p>:<div className="design-history-list">{[...batches].reverse().map(b=><button key={b.id} className={batch?.id===b.id?'chosen':''} onClick={()=>{setBatchId(b.id);setShowHistory(false);}}><span><strong>{b.name}</strong><small>{b.created.replace('T',' ').slice(0,19)} · {b.count} 个候选</small></span><span>{batch?.id===b.id?'当前查看':'查看候选'}</span></button>)}</div>}</Modal>}
  </>;
}
