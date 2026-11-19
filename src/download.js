// Keep the URL alive while the browser or its save dialog takes over the file.
export function download(blob, name) {
 if (!blob || blob.size === 0) throw new Error('下载文件为空，请重试。');
 const url = URL.createObjectURL(blob), a = document.createElement('a');
 a.href = url; a.download = name; a.hidden = true;
 document.body.appendChild(a);
 try { a.click(); }
 catch (error) { a.remove(); URL.revokeObjectURL(url); throw error; }
 setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 5 * 60 * 1000);
}

export async function exportBlob(response, format) {
 if (!response.ok) {
  let message = '导出失败，请重试。';
  try { message = (await response.json()).error || message; } catch { /* non-JSON proxy error */ }
  throw new Error(message);
 }
 const blob = await response.blob();
 if (!blob.size) throw new Error('导出返回了空文件，未开始下载。请重试并检查服务终端。');
 const length = response.headers.get('Content-Length');
 if (length !== null && !response.headers.get('Content-Encoding') && Number(length) !== blob.size)
  throw new Error('导出文件传输不完整，未开始下载。请重试。');
 const bytes = new Uint8Array(await blob.slice(0, 12).arrayBuffer());
 const valid = format === 'zip'
  ? bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 3 && bytes[3] === 4
  : String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WAVE';
 if (!valid) throw new Error('服务未返回有效的音频文件或 ZIP，未开始下载。请刷新页面后重试。');
 return blob;
}
