# 白龙娘素材补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按用户修订制作独立角色雏龙娘的完整 109 段二维关键帧动画，并更新本机 DSH 插件。

**Architecture:** 提示词目录对比生成动作清单。八组插画关键姿势形成统一图集。Remotion 使用相同站立基准和睡姿编排视频，统一导出、验证并安装角色包。

**Tech Stack:** Remotion、React、TypeScript、FFmpeg、Pillow、PySide6。

**Spec:** `docs/superpowers/specs/2026-11-21-bailong-materials-design.md`

**用户修订优先：** 独立角色雏龙娘，完整 109 条提示词，30 fps / 300 帧，光流补间与透明 WebM，成品目录 `D:\Desktop\素材库\雏龙娘`。

## Global Constraints

- 109 个动作，雏龙娘独立角色。
- 每段 10 秒、30 fps、16:9，绿幕 MP4 和直接从 RGBA 编码的透明 WebM。
- 正常动作首尾标准站姿。睡觉开始、循环、起来使用共同睡姿。
- 成品目录为 `D:\Desktop\素材库\雏龙娘`。
- 新角色独立安装，不覆盖原有角色素材。

## Review Focus

- 提示词存在鲸鱼专属特征，替换成白龙娘龙尾和龙角。
- 动作大幅度、道具体积超出安全区时必须缩放组合。
- 插画图集单元格的边界和透明通道应逐格验证。
- 插件使用原生 30 fps 的透明 WebM；循环帧共享 96 MiB 无损压缩缓存。
- 睡觉循环边界与相邻两段共用同一帧。

## Tasks

- [x] 解析提示词和素材库，固定完整动作清单与逐项提示词。
- [x] 准备 Remotion 项目、雏龙娘基准站姿和十九组关键姿势，打开 Studio。
- [x] 完成 109 项编排并渲染抽样画面，检查角色和构图。
- [x] 导出全部成片，验证时长、帧数、边界、首尾和解码。
- [x] 复制到素材库和插件角色目录，重启并用真实播放器读取新角色。
- [x] 更新 README、素材索引和验证记录。

## 验收

MP4 全部解码 32,700 帧；透明 WebM 共 327 个指定帧样本通过。Qt 播放器 12.317 秒观察到 371 帧，约 30.04 fps，跨越循环边界只启动一次解码。7 项相关测试通过。本机插件实际返回「雏龙娘」、109 个动作；「睡觉-开始」后返回「睡觉-循环」，「睡觉-起来」后回到待机。提交前通过独立 Pillow 13 依赖解决两项旧白龙测试的环境限制，完整 26 项测试通过。
