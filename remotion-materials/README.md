# 雏龙娘 Remotion 全动作角色包

按用户选择的二维关键帧方式制作独立角色「雏龙娘」。提示词目录实际含 109 条，全部制作。每项使用新绘雏龙娘关键姿势、双向光流补间和呼吸运动，Remotion 导出 640×360、30 fps、10 秒 MP4，并提供透明 VP9 WebM。

动作名称和原始提示词记录在 `actions.json`，沿用提示词名称以便逐项对照。人物和道具采用插画关键姿势切换，复杂动作是二维概括表现。第一帧和普通动作末帧共用雏龙娘标准站姿，睡觉三段使用同一张睡姿。

生成的新图集在 `public/atlas-0.png` 至 `public/atlas-18.png`，拆分结果在 `public/poses`。成品保存在 `D:\Desktop\素材库\雏龙娘`，分绿幕 MP4、透明 WebM 和制作源文件。工作环境依赖和中间帧保存在项目本地。

仓库包含图集、全部姿势图和制作源文件。[绿幕成品与索引](../materials/雏龙娘/README.md) 和 [透明桌宠动画](../codex-adapter/plugins/dsh-dragon/assets/characters/雏龙娘/videos) 可直接使用。`node_modules`、光流数据和数万张中间帧由制作步骤重建。

## 制作

安装 Node.js 和 pnpm 后，在本目录执行：

```powershell
pnpm install --config.node-linker=hoisted
python -m pip install -r requirements.txt
python prepare.py
python flow.py
python bake.py
python composite.py
pnpm studio
pnpm render
python transparent.py
python verify_alpha.py
python verify.py
```

批量导出使用 Remotion 的 `stitchFramesToVideo` 将预计算画面编码为视频。`pnpm render:browser` 则使用完整浏览器合成流程，默认使用 Windows 本机 Edge。修改 `browserExecutable` 可以使用其他 Chromium。`ACTIONS=Action01` 可只渲染某个动作，`STILLS=1` 渲染抽样静帧。

透明导出和验证默认使用本机桌宠环境中的 FFmpeg。其他电脑需先设置 `PET_FFMPEG` 为支持 `libvpx-vp9` 的 FFmpeg 完整路径。透明视频直接从 RGBA 中间帧编码，避免抠绿损失道具颜色。`requirements.txt` 固定素材制作时的版本；桌宠插件安装依赖以 `../codex-adapter/requirements.txt` 为准。

视频绘制背景为纯 `#00FF00`，有损编码后使用颜色容差验证。插件使用配套透明 VP9 WebM，保留角色道具中的绿色。

雏龙娘以本仓库的白龙娘透明待机为外观参考，新关键姿势使用内置图像工具生成。角色独立于默认白龙。原有角色美术来源和许可说明见 `../codex-adapter/plugins/bailong-pet/ASSETS.md`。

## 验证记录（2026-11-21）

- 109 段 MP4 全量解码，共 32,700 帧；全部为 640×360、30 fps、10 秒，检查画面安全边距与循环边界。
- 109 段透明 WebM 分别解码第 0、149、299 帧，检查透明边缘及非透明角色区域；`manifest.json` 记录逐文件哈希与采样范围。
- 同一 Qt 播放器读取透明待机 12.317 秒，观察到 371 帧，约 30.04 fps；跨越 10 秒循环边界只启动一次解码，最大帧间隔 40.86 ms。这是播放器路径测量，不代表所有电脑的桌面绘制帧率。
- 播放帧率、无损缓存、缓存额度释放、睡觉衔接及设置窗口的 7 项相关测试通过。
- 提交前补齐仓库要求的 Pillow 13 独立测试依赖，完整 26 项测试通过；修复了此前两项通信测试的运行环境限制，未改动正在运行的插件依赖。
