# 雏龙娘 Remotion 全动作角色包

按用户选择的二维关键帧方式制作独立角色「雏龙娘」。提示词目录实际含 109 条，全部制作。新版使用新绘雏龙娘主要姿势、RIFE v4.6 神经中间姿势和连续次级运动，Remotion 导出 640×360、60 fps、10 秒、600 帧 MP4，并提供透明 VP9 WebM。

动作名称和原始提示词记录在 `actions.json`，沿用提示词名称以便逐项对照。人物和道具采用插画关键姿势切换，复杂动作是二维概括表现。第一帧和普通动作末帧共用雏龙娘标准站姿，睡觉三段使用同一张睡姿。

生成的新图集在 `public/atlas-0.png` 至 `public/atlas-18.png`，拆分结果在 `public/poses`。成品保存在 `D:\Desktop\素材库\雏龙娘`，分绿幕 MP4、透明 WebM 和制作源文件。工作环境依赖和中间帧保存在项目本地。

仓库包含图集、全部姿势图和制作源文件。[绿幕成品与索引](../materials/雏龙娘/README.md) 和 [透明桌宠动画](../codex-adapter/plugins/dsh-dragon/assets/characters/雏龙娘/videos) 可直接使用。`node_modules`、光流数据和数万张中间帧由制作步骤重建。

## 制作

安装 Node.js 和 pnpm 后，在本目录执行：

```powershell
pnpm install --config.node-linker=hoisted
python -m pip install -r requirements.txt
python prepare.py
python build_smooth.py
python composite.py
pnpm studio
pnpm render
python transparent.py
python verify_alpha.py
python verify.py
```

先从 [RIFE 官方发布](https://github.com/nihui/rife-ncnn-vulkan/releases/tag/20221029) 下载 Windows 工具，设置 `PET_RIFE` 为 `rife-ncnn-vulkan.exe` 的完整路径，同级需有 `rife-v4.6` 模型目录。补帧在本机显卡运行，不上传图像；默认 GPU 编号 0，可用 `PET_RIFE_GPU` 修改。`build_smooth.py` 同时编排 GPU 中间姿势计算与 CPU 600 帧制作，原始插画数量仍为每动作四张，常规动作有 161 个密集姿势样本。相关算法来源与用法见 [RIFE ncnn Vulkan](https://github.com/nihui/rife-ncnn-vulkan)。

所有制作和验证脚本共用 `src/render-config.json` 的帧率、总时长和版本目录。新版输出到 `out-smooth-v1`，准备帧在 `public/frames-smooth-v1`，神经样本在 `public/neural-v1`；旧缓存不会冒充新结果。

这些目录只支持同一版本的断点续跑。修改插画、时间线或运动算法后，必须同时递增配置中的 `preparedFolder`、`compositedFolder`、`neuralFolder` 和 `outputFolder` 版本，再制作与验证；已有成品不会仅因源码变更而自动重建。本次在新建的 `smooth-v1` 目录中完整生成，未沿用 30 帧缓存。

批量导出使用 Remotion 的 `stitchFramesToVideo` 将预计算画面编码为视频。`pnpm render:browser` 则使用完整浏览器合成流程，仅打包当前选择动作的最终帧，默认使用 Windows 本机 Edge。修改 `browserExecutable` 可以使用其他 Chromium。PowerShell 中设置 `$env:ACTIONS='Action01'` 可只制作和渲染某个动作，`$env:STILLS='1'` 通过浏览器渲染抽样静帧。

透明导出和验证默认使用本机桌宠环境中的 FFmpeg。其他电脑需先设置 `PET_FFMPEG` 为支持 `libvpx-vp9` 的 FFmpeg 完整路径。透明视频直接从 RGBA 中间帧编码，避免抠绿损失道具颜色。`requirements.txt` 固定素材制作时的版本；桌宠插件安装依赖以 `../codex-adapter/requirements.txt` 为准。

视频绘制背景为纯 `#00FF00`，有损编码后使用颜色容差验证。插件使用配套透明 VP9 WebM，保留角色道具中的绿色。

雏龙娘以本仓库的白龙娘透明待机为外观参考，新关键姿势使用内置图像工具生成。角色独立于默认白龙。原有角色美术来源和许可说明见 `../codex-adapter/plugins/bailong-pet/ASSETS.md`。

## 验证记录（2026-11-21）

- 初版问题：尽管文件标为 30 fps，挥手、转身、写代码中有 49 组相邻重复帧，待机有 59 组；末尾呼吸突然归零，引起画面跳变。上版只测播放速度，不能证明动作本身连贯。
- 新版去掉长静帧，采用每段 600 帧的 60 fps 制作。`verify.py` 检查视频帧数、画面安全边距、循环边界及实际准备帧的唯一性；`verify_alpha.py` 每半秒及最终帧采样透明度，每段共 21 帧。详细结果记录在成品 `manifest.json`。
- 挥手与转身样片的相邻重复帧均从 49 降至 0，待机从 59 降至 0。正常眨眼时画面变化较快，因此不把整段最大像素差单独当作质量结论。
- 同一 Qt 播放器读取透明待机 12.310 秒，观察到 740 帧，约 60.03 fps；跨越循环边界只启动一次解码，最大帧间隔 24.72 ms。这是播放器路径测量，不代表所有电脑的桌面绘制帧率。
- 连续性回归检查在旧代码上出现停帧和跳变两个失败项，在新版上均通过；完整插件 26 项测试通过。
- 提交前补齐仓库要求的 Pillow 13 独立测试依赖，完整 26 项测试通过；修复了此前两项通信测试的运行环境限制，未改动正在运行的插件依赖。
