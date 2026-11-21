import {bundle} from '@remotion/bundler';
import {getCompositions, openBrowser, renderMedia, renderStill} from '@remotion/renderer';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const root = process.cwd();
const output = path.join(root, 'out-chulong');
await fs.mkdir(output, {recursive: true});
const records = JSON.parse(await fs.readFile('src/actions.json', 'utf8'));
const serveUrl = process.env.USE_EXISTING_BUNDLE === '1' ? path.join(root, 'dist')
  : await bundle({entryPoint: path.join(root, 'src/index.tsx'), outDir: path.join(root, 'dist')});
const browserExecutable = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const browser = await openBrowser('chrome', {browserExecutable, chromiumOptions: {disableWebSecurity: false}});
try {
  const compositions = await getCompositions(serveUrl, {puppeteerInstance: browser});
  const selected = process.env.ACTIONS?.split(',');
  for (const composition of compositions) {
    if (selected && !selected.includes(composition.id)) continue;
    const name = records.find((item) => item.id === composition.id)?.name ?? '待机呼吸休闲';
    const file = path.join(output, `${name}.mp4`);
    if (process.env.STILLS === '1') {
      await renderStill({composition, serveUrl, output: path.join(output, `${name}.png`),
        frame: composition.id === 'Action47' ? 100 : 140, puppeteerInstance: browser});
      console.log(`Still ${composition.id} ${name}`);
      continue;
    }
    try { if ((await fs.stat(file)).size > 1000 && process.env.RENDER_AGAIN !== '1') continue; } catch {}
    await renderMedia({composition, serveUrl, outputLocation: file, codec: 'h264', crf: 13,
      pixelFormat: 'yuv444p', concurrency: Math.min(12, os.availableParallelism()), puppeteerInstance: browser,
      x264Preset: 'veryfast', overwrite: true, muted: true});
    console.log(`Rendered ${composition.id} ${name}`);
  }
} finally {
  await browser.close({silent: true});
}
