# Breeze 配音工作台

为 **已经安装的官方 Breeze TTS 2** 增加本地网页，提供音色设计、参考音色库和分段配音。此项目是独立的网页接入层，并非模型官方网页。程序不含模型，不修改官方源码，不安装/升级 PyTorch，不量化、不转换模型。

当前版本：**0.2.0**。需要 Python 3.10+；生成语音使用现有官方虚拟环境。

## 音色设计：先挑声音，再做教程

1. 打开左侧“音色设计”，选择“甜妹 · 教程”“甜妹 · 温柔”或“甜妹 · 元气”，也可以自己修改描述。
2. 填写一段约 50～180 字的试听文案。默认生成 3 个候选，CFG 4，种子分别为 42、43、44；也可以选择 1 或 5 个。
3. 所有候选使用相同描述、文案和 CFG，仅改变随机种子；在同一 GPU 队列中依次生成。设计记录单独保存，不占用教程项目的段落。
4. 试听完整录音，选“保存为音色”。核对实际说出的参考文字后保存，参考 WAV 原样保留；同时保留生成种子、描述和来源记录。
5. 保存后会设为当前项目的全局参考音色（表达要求留空、CFG 1），已有的单段覆盖设置仍保留。后续也可从音色库选择。

生成失败或取消后可只重试那个候选。设计表单草稿保存在当前浏览器，已提交的设计记录和音频保存在服务端 `data/`，更新不会清空它们。

文字描述是生成条件，不是精确的声学控制器；固定种子也不等于固定音色。候选的甜美程度、自然感和参考克隆效果需实际试听确认。

## 用 Git 安装和更新

仓库包含已构建的 `dist/client/`，目标电脑不需要 Node.js。第一次安装可克隆本仓库，然后运行 `bash start.sh`。

已经用 ZIP 安装的用户：先关闭旧服务，在另一个新目录克隆仓库，再复制旧程序的 **data 文件夹**。例如（把仓库地址替换成实际地址）：

```bash
git clone "https://github.com/你的账号/breeze-studio.git" ~/breeze-studio-git
cp -a ~/breeze-studio/data ~/breeze-studio-git/data
cd ~/breeze-studio-git
bash start.sh
```

保留旧目录，确认新程序能读取项目和音色后再自行整理。模型和官方虚拟环境仍在原位置，绝对路径配置随 data 一起迁移。

以后更新：先在启动服务的终端按 **Ctrl+C**，然后执行：

```bash
cd ~/breeze-studio-git
bash update.sh
bash start.sh
```

更新仅允许 Git 快进合并，有本地代码修改或历史分叉会停止。合并前备份 `config.json` 和 `state.json` 到 `data/backups/`；不会重新安装依赖或下载模型。远程版本若包含 `data/` 等本地数据目录会拒绝合并。`data/`、录音、模型权重、虚拟环境和 `.env` 都已加入 Git 忽略规则。

维护者修改前端后应运行 `npm ci`、`npm run build`，将源码和 `dist/client/` 一起提交。验证命令：`python3 -m unittest discover -s tests -p 'test_*.py' -v`。

## 在装有 Breeze 的那台电脑上启动

1. 将 `Breeze-Studio-WSL2.zip` 复制到那台电脑，解压得到 `breeze-studio` 文件夹。
2. 在 Ubuntu/WSL 终端中，把文件夹复制到 Linux 主目录。例如解压在 Windows 下载文件夹时（用户名按实际修改）：

   ```bash
   cp -r /mnt/c/Users/16572/Downloads/breeze-studio ~/breeze-studio
   cd ~/breeze-studio
   bash start.sh
   ```

3. 在 **那台 Windows 电脑** 的浏览器打开 `http://localhost:7860`。
4. 打开“设置”，检查路径，点击“加载模型”。首次加载需要一些时间；可在终端或 `data/worker.log` 查看进度。
5. 在“自由配音”输入一小段文案，填写声音描述或选择参考音色，生成、试听并下载 WAV。

默认检测：

```text
~/breeze-work/breeze-tts
~/breeze-work/models/Breeze-TTS-2
~/breeze-work/breeze-tts/.venv/bin/python
```

路径不同时可在网页设置中修改，或启动时明确指定：

```bash
bash start.sh \
  --repo "$HOME/breeze-work/breeze-tts" \
  --model "$HOME/breeze-work/models/Breeze-TTS-2" \
  --python "$HOME/breeze-work/breeze-tts/.venv/bin/python"
```

前端已经打包，**目标电脑不需要安装 Node.js，也不需要运行 npm 或 pip**。网页服务仅使用 Python 标准库。生成语音时单独调用你原来虚拟环境中的 Python。

关闭：在启动终端按 Ctrl+C；子推理进程随服务关闭。下次仍运行 `bash start.sh`。7860 被占用时用 `BREEZE_STUDIO_PORT=7862 bash start.sh`，浏览器改为对应端口。不要同时启动两个服务共用同一个 data 目录。

## 已实现

- 独立音色设计：甜美女声预设、1/3/5 个候选、同条件不同种子对比、批次记录、单个重试、一键保存为参考音色。
- 自由配音：声音描述、参考音色克隆、参考音色加语气引导；CFG、种子、预设；可选实时试听。
- 音色库：上传参考音频与完整文字；试听、选择、移除；把已生成结果保存为新的参考音色。上传文件逐字节保存，SHA256 记录在本地。
- 分段配音：导入 TXT/Markdown，按空行和标点自动分段；手动增删、编辑标题、拖动/按钮排序、拆分、合并；全局设置和单段覆盖。
- 单 GPU 串行任务队列：单段/全部/未完成生成，取消当前与等待任务，失败后继续后续任务；界面关闭后任务仍继续。
- 自动保存项目；历史记录包含每次文案、音色、CFG、seed；复用文案参数、试听和下载。
- 下载单段 WAV、按当前段落顺序 ZIP 打包、无重采样拼接 WAV，段间停顿可调。
- 检测文字或参数修改后将旧结果视为过期；导出时再次检查，不把旧录音当作新结果。
- 常驻加载/卸载官方模型，显示 nvidia-smi 整卡显存读数，诊断日志。
- 本机 HTTP API，便于以后接入教程生产脚本。
- 可选参考音频转写：配置本机兼容 OpenAI `/audio/transcriptions` 协议的识别服务。未配置时手填文字；本包不安装识别模型。

## 模型和音质约束

`backend/worker.py` 从你的官方仓库导入 `infer.py`，调用它暴露的 `load_runtime`、`update_generation_config_for_breeze`、`prepare_inputs`、模板选择、随机种子函数和 `FastBreezeStreamingRuntime`。沿用该版本的 `MAX_NEW_TOKENS`、`MAX_SEQ_LEN` 和重复惩罚。

- `attn_implementation="eager"`，所有 fast 开关关闭，对应之前的 `--no-fast-all` 用法。
- 不传入任何额外 dtype、量化、模型转换或音频增强参数；精度由官方 `load_runtime` 决定。核查的官方版本使用 BF16。
- 下载文件与官方命令同样使用 `soundfile` 写 PCM16 单声道 WAV。合并仅复制 PCM 帧并插入零值静音，不归一化、不重采样、不压缩。
- 各段独立生成并重置随机种子，复用同一参考素材；没有引入社区版跨请求连续生成算法。独立段落的语气仍可能不同。
- 浏览器实时试听会经过浏览器音频设备采样率，下载 WAV 保持原始采样率。实时试听是轮询获取音频块，不承诺与官方云服务相同延迟。
- 不同模型版本、文案、参考音频、种子或硬件可能导致输出不同。“保持原模型”不等于保证每次生成同一波形。真实 GPU 验收还需在目标电脑执行。
- 800 字是界面的单段上限，不是模型保证可完整生成的长度；建议教程按步骤分成约 50～180 字一段。音频过长仍受官方上下文和输出长度限制。

## 真实 GPU 对照检查

先在网页中卸载模型，避免两份模型同时占显存。然后在本程序目录运行：

```bash
python3 scripts/compare_official.py
```

脚本依次运行原始官方命令、常驻网页接入层两次，用相同文案和种子生成。结果在 `data/comparison/`：

```text
official.wav
adapter-1.wav
adapter-2.wav
report.json
```

`pcm_byte_identical` 是同机逐字节比较；不一致时应试听并检查版本，不能把数值差异直接当作音质下降。可以传入 `--text`、`--instruction`、`--cfg`、`--seed`。纯克隆对比示例：

```bash
python3 scripts/compare_official.py \
  --ref-audio /绝对路径/reference.wav \
  --ref-text '录音中实际说出的完整内容。' \
  --text '这是新的教程文案。' --instruction '' --cfg 1
```

## 排查

网页“设置 → 下载诊断日志”；或运行：

```bash
python3 scripts/diagnose.py
```

诊断文件记录项目路径、官方源码哈希、环境检测、错误日志尾部。可能含本机用户名、路径或报错涉及的文案，分享前可自行查看。

- 路径错误：在设置中填写 Linux 路径，不是 `C:\...`。
- CUDA 不可用：在原来的官方环境中运行 `nvidia-smi` 与官方命令，先确认原环境工作正常。
- 显存不足：关闭其他占显存程序，缩短参考录音与单段文案；取消后重新加载。此程序不会偷偷降低精度。
- `AttributeError` / 接口不匹配：本地官方版本与适配器接口不同。保留现有仓库，不要直接升级覆盖；提供诊断记录后适配。
- Windows 不能访问：先在 WSL 中执行 `curl http://127.0.0.1:7860/api/state`。浏览器需要在运行 WSL 的同一台 Windows 机器上打开。

## API 简例

下列代码在运行服务的电脑上执行，未配置好模型时会记录失败原因：

```python
import json, time, urllib.request

base = 'http://127.0.0.1:7860'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(path, body=None):
    request = urllib.request.Request(base + '/api/' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    return json.load(opener.open(request))

p = call('projects', {
    'name': '自动化教程', 'mode': 'segments',
    'settings': {'voice_id': '', 'instruction': '普通话男声，清晰自然。', 'cfg': 4, 'seed': 42},
    'segments': [{'id': 'intro', 'title': '开场', 'text': '今天介绍一个实用的工具。'}]
})
jobs = call('jobs', {'project_id': p['id']})
job_id = jobs[0]['id']
while True:
    j = next(j for j in call('state')['jobs'] if j['id'] == job_id)
    if j['status'] in ('completed', 'failed', 'cancelled'): break
    time.sleep(1)
if j['status'] == 'completed':
    with opener.open(base + '/api/audio/job/' + job_id) as response:
        open('intro.wav', 'wb').write(response.read())
else:
    raise RuntimeError(j.get('error') or j['status'])
```

其它接口：`POST /api/voices`（base64 音频、filename、name、transcript）、`POST /api/cancel`（ids）、`POST /api/model`（action: load/unload）、`POST /api/export`（project_id、format: wav/zip、pause_ms）、`GET /api/diagnostics`。仅监听本机，不提供互联网托管。

## 数据与开发

`data/` 保存项目、音色、音频和日志，备份整个目录即可。发布包不携带开发测试数据。移除音色仅从可选列表移除，保留参考文件以供历史追溯。

开发前端：`npm ci`、`npm run dev`（代理后端 7860）；生产构建：`npm run build`。后端测试：`python3 -m unittest discover -s tests -p 'test_backend.py' -v`。测试引擎只在测试中注入，不是生产生成方式。

本地开源/开放权重模型的使用仍遵守原模型许可证；网页不改变其授权范围。
