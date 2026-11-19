import test from 'node:test';
import assert from 'node:assert/strict';
import {download, exportBlob} from '../src/download.js';

test('download keeps a mounted link alive for a delayed browser handoff', t => {
 let attached = false, removed = false, revoked = false, cleanup, delay;
 const a = {click() { assert.equal(attached, true); }, remove() { removed = true; }};
 t.mock.method(URL, 'createObjectURL', () => 'blob:download-test');
 t.mock.method(URL, 'revokeObjectURL', () => { revoked = true; });
 t.mock.method(globalThis, 'setTimeout', (callback, ms) => { cleanup = callback; delay = ms; });
 const previous = Object.getOwnPropertyDescriptor(globalThis, 'document');
 Object.defineProperty(globalThis, 'document', {configurable: true, value: {
  createElement: () => a, body: {appendChild: () => { attached = true; }},
 }});
 t.after(() => { if (previous) Object.defineProperty(globalThis, 'document', previous); else delete globalThis.document; });
 download(new Blob(['archive data']), '分段配音.zip');
 assert.equal(a.download, '分段配音.zip');
 assert.equal(revoked, false); assert.equal(removed, false);
 assert.ok(delay >= 300000);
 cleanup(); assert.equal(revoked, true); assert.equal(removed, true);
});

test('empty files, server errors, wrong content and incomplete bodies cannot download', async () => {
 assert.throws(() => download(new Blob([]), 'empty.zip'), /为空/);
 await assert.rejects(exportBlob(new Response(null), 'zip'), /空文件/);
 await assert.rejects(exportBlob(new Response('{"error":"请先生成"}', {status:400}), 'zip'), /请先生成/);
 await assert.rejects(exportBlob(new Response('<html>proxy</html>'), 'zip'), /有效/);
 await assert.rejects(exportBlob(new Response('PK\x03\x04payload', {headers:{'Content-Length':'100'}}), 'zip'), /不完整/);
});

test('valid ZIP and WAV payloads pass through byte-for-byte', async () => {
 for (const [format, data] of [['zip', 'PK\x03\x04payload'], ['wav', 'RIFF0000WAVEpayload']]) {
  const response = new Response(data, {headers:{'Content-Length':String(data.length)}});
  assert.equal(await (await exportBlob(response, format)).text(), data);
 }
});
