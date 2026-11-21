import {RenderInternals, stitchFramesToVideo} from '@remotion/renderer';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const config = JSON.parse(await fs.readFile('src/render-config.json', 'utf8'));
const frameCount = config.fps * config.durationSeconds;
const out = path.join(root, config.outputFolder);
const actions = JSON.parse(await fs.readFile('src/actions.json', 'utf8'));
const safeActions = JSON.parse(await fs.readFile('src/safe-actions.json', 'utf8'));
await fs.mkdir(out, {recursive: true});
for (const action of actions) {
  if (process.env.ACTIONS && !process.env.ACTIONS.split(',').includes(action.id)) continue;
  const file = path.join(out, `${action.name}.mp4`);
  try { if ((await fs.stat(file)).size > 1000) continue; } catch {}
  const folder = config.compositedFolder;
  while (true) {
    try { await fs.access(path.join(root, 'public', folder, action.id, `${frameCount-1}.png`)); break; }
    catch { await new Promise((resolve) => setTimeout(resolve, 2000)); }
  }
  const downloadMap = RenderInternals.makeDownloadMap(48000);
  const assetsInfo = {
    assets: Array.from({length: frameCount}, (_, frame) => ({frame, audioAndVideoAssets: [], artifactAssets: [], inlineAudioAssets: []})),
    imageSequenceName: path.join(root, 'public', folder, action.id, '%03d.png'),
    firstFrameIndex: 0, downloadMap, chunkLengthInSeconds: 10, trimLeftOffset: 0, trimRightOffset: 0,
    forSeamlessAacConcatenation: false,
  };
  await stitchFramesToVideo({fps: config.fps, width: config.width, height: config.height, codec: 'h264', crf: 13,
    pixelFormat: 'yuv444p', x264Preset: 'veryfast', muted: true, force: false, assetsInfo,
    outputLocation: file, metadata: {title: `雏龙娘 · ${action.name}`,
      comment: 'Remotion 4.0.534 / 60fps RIFE intermediate poses + continuous secondary motion'}});
  console.log(`Stitched ${action.id} ${action.name}`);
}
