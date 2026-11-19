const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function text(value, label, max, empty = false) {
 if (typeof value !== 'string' || value.length > max || (!empty && !value.trim())) throw new Error(`${label}格式错误或超过 ${max} 字。`);
 return value.trim();
}
function params(value = {}) {
 if (!object(value)) throw new Error('生成参数格式错误。');
 const result = {};
 if (value.cfg !== undefined) {
  if (typeof value.cfg !== 'number' || !Number.isFinite(value.cfg) || value.cfg <= 0 || value.cfg > 20) throw new Error('CFG 必须大于 0 且不超过 20。');
  result.cfg = value.cfg;
 }
 if (value.seed !== undefined) {
  if (!Number.isInteger(value.seed) || value.seed < 0 || value.seed > 4294967295) throw new Error('随机种子必须是 0～4294967295 的整数。');
  result.seed = value.seed;
 }
 return result;
}

export function parseScriptImport(source) {
 let value;
 try { value = JSON.parse(source.replace(/^\uFEFF/, '')); } catch { throw new Error('文案 JSON 格式错误，请选择完整的导入文件。'); }
 if (!object(value) || value.type !== 'breeze-studio-script' || value.version !== 1) throw new Error('不支持此文件，请使用 Breeze Studio 文案导入格式 v1。');
 if (!Array.isArray(value.segments) || value.segments.length < 1 || value.segments.length > 200) throw new Error('导入文件需要包含 1～200 个段落。');
 const defaults = params(value.defaults);
 const segments = value.segments.map((s, i) => {
  if (!object(s)) throw new Error(`第 ${i+1} 段格式错误。`);
  return {title: text(s.title ?? `第 ${i+1} 段`, '段落标题', 100),
   text: text(s.text, `第 ${i+1} 段文案`, 800),
   instruction: text(s.instruction ?? '', `第 ${i+1} 段表达要求`, 2000, true), ...defaults, ...params(s)};
 });
 if (segments.reduce((n, s) => n+s.text.length, 0) > 100000) throw new Error('项目文案超过 100000 字。');
 return {name: text(value.name ?? '导入配音项目', '项目名称', 100), segments};
}

// A portable script never imports machine-specific voice IDs, paths or recordings.
export function projectFromScript(script, voiceId, makeId = () => crypto.randomUUID().replaceAll('-', '')) {
 if (!voiceId) throw new Error('请先选择一个已保存的参考音色。');
 const pid = makeId();
 return {id: pid, name: script.name, mode: 'segments', pause_ms: 300,
  settings: {voice_id: voiceId, instruction: '', cfg: 1, seed: 42},
  output: {speed: 1, volume: 1},
  single: {id: 'single-'+pid, title: '自由配音', text: '', settings: null},
  segments: script.segments.map(s => ({id: makeId(), title: s.title, text: s.text, output: null,
   settings: {voice_id: voiceId, instruction: s.instruction, cfg: s.cfg ?? (s.instruction ? 4 : 1), seed: s.seed ?? 42}}))};
}
