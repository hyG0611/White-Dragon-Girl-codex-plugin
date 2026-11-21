# 雏龙娘素材包

雏龙娘是 Windows DSH 白龙插件中的独立角色。按提示词实际数量制作 109 个动作，包含「是啊，吃什么」，覆盖原先提到的 108 套。动作名称保留提示词命名，角色使用新绘的雏龙娘形象。

![雏龙娘标准站姿](../../remotion-materials/public/poses/idle.png)

| 内容 | 路径 | 规格 |
| --- | --- | --- |
| 绿幕视频 | [绿幕MP4](绿幕MP4) | 109 段，640×360，30 fps，每段 10 秒 |
| 透明桌宠视频 | [角色 videos 目录](../../codex-adapter/plugins/dsh-dragon/assets/characters/雏龙娘/videos) | 109 段 VP9 WebM，保留透明通道 |
| 全动作预览 | [动作总览](动作总览.jpg) | 每项一张抽样画面 |
| 文件清单 | [manifest.json](manifest.json) | 时长、帧数、尺寸、SHA-256 及透明采样检查记录 |
| 播放实测 | [playback-report.json](playback-report.json) | 约 30 fps，包含循环边界 |
| 制作工程 | [Remotion 源文件](../../remotion-materials/README.md) | 19 张插画图集、438 张姿势图、提示词和重建步骤 |

安装插件后，右键选择「切换角色 → 雏龙娘」，从「播放动作（全部素材）」选动作。「睡觉-开始」会衔接「睡觉-循环」，播放「睡觉-起来」即可唤醒。桌宠使用透明视频，绿幕视频用于剪辑。

动画采用二维插画关键姿势与双向光流补间，复杂动作做了概括，过渡可能出现形变。人物参考、素材来源及使用说明见 [ASSETS.md](ASSETS.md)。本机另存于 `D:\Desktop\素材库\雏龙娘`，按绿幕 MP4、透明 WebM 和制作源文件分文件夹。
