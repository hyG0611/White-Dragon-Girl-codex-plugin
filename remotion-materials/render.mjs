import {bundle} from '@remotion/bundler';
import {getCompositions, openBrowser, renderMedia, renderStill} from '@remotion/renderer';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const root = process.cwd();
const config = JSON.parse(await fs.readFile('src/render-config.json', 'utf8'));
const output = path.join(root, config.outputFolder);
await fs.mkdir(output, {recursive: true});
const records = JSON.parse(await fs.readFile('src/actions.json', 'utf8'));
const selected = process.env.ACTIONS?.split(',');
// Avoid copying neural data and every historical render cache into a browser bundle.
const publicDir = path.join(root, '.cache', 'render-public');
for (const record of records.filter((item) => !selected || selected.includes(item.id))) {
  const destination = path.join(publicDir, config.preparedFolder, record.id);
  await fs.mkdir(destination, {recursive: true});
  await fs.cp(path.join(root, 'public', config.preparedFolder, record.id), destination, {recursive: true});
}
const serveUrl = process.env.USE_EXISTING_BUNDLE === '1' ? path.join(root, '.cache', 'render-bundle')
  : await bundle({entryPoint: path.join(root, 'src/index.tsx'), publicDir, outDir: path.join(root, '.cache', 'render-bundle')});
const browserExecutable = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const browser = await openBrowser('chrome', {browserExecutable, chromiumOptions: {disableWebSecurity: false}});
try {
  const compositions = await getCompositions(serveUrl, {puppeteerInstance: browser});
  for (const composition of compositions) {
    if (selected && !selected.includes(composition.id)) continue;
    const name = records.find((item) => item.id === composition.id)?.name ?? '待机呼吸休闲';
    const file = path.join(output, `${name}.mp4`);
    if (process.env.STILLS === '1') {
      await renderStill({composition, serveUrl, output: path.join(output, `${name}.png`),
        frame: Math.round(composition.fps * (composition.id === 'Action47' ? 3.3 : 4.67)), puppeteerInstance: browser});
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
