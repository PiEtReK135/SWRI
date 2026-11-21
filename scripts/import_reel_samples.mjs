import { mkdir, rename, stat } from 'node:fs/promises';
import { createWriteStream, openAsBlob } from 'node:fs';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

// Independently published material. The scanner receives the same post as any viewer.
const samples = [
  {
    file: 'Apollo11.jpg',
    asset: 'https://images-assets.nasa.gov/image/as11-40-5903/as11-40-5903~orig.jpg',
    source: 'https://images.nasa.gov/details/as11-40-5903',
    title: 'Apollo 11 na Księżycu', creator: 'nasa', topic: 'Technologia',
    description: 'Zdjęcie z archiwum fotograficznego misji Apollo 11.',
    credit: 'NASA · materiał archiwalny · przetworzenie formatu',
  },
  {
    file: 'ETF.mp4',
    asset: 'https://download.media.tagesschau.de/video/2020/0930/TV-20200930-1644-3300.webxxl.h264.mp4',
    source: 'https://commons.wikimedia.org/wiki/File:Gut_zu_wissen,_Wie_funktionieren_ETFs%3F_-_Tagesschau.webm',
    title: 'Jak działają ETF-y?', creator: 'tagesschau_ard', topic: 'Rynek i inwestycje',
    description: 'Materiał Tagesschau z serii „Gut zu wissen” wyjaśnia, jak działają fundusze ETF. Język niemiecki.',
    credit: 'Tagesschau (ARD) · CC BY-SA 4.0 · przetworzenie formatu',
  },
  {
    file: 'BigBuckBunny.mp4',
    asset: 'https://media.w3.org/2010/05/bunny/trailer.mp4',
    source: 'https://peach.blender.org/about/',
    title: 'Big Buck Bunny', creator: 'blender_foundation', topic: 'Kultura',
    description: 'Zwiastun animacji projektu Peach z 2008 roku.',
    credit: 'Blender Foundation · CC BY 3.0 · przetworzenie formatu',
  },
];

const base = 'http://127.0.0.1:8000/api/reels';
const cache = join('data', 'sample-reels');
await mkdir(cache, { recursive: true });
const feed = await fetch(base + '/feed?viewer=sample-import&limit=20');
if (!feed.ok) throw Error('Nie można odczytać lokalnego feedu');
const existing = new Set((await feed.json()).map(post => post.source));
let failed = false;
for (const { file, asset, ...metadata } of samples) {
  if (existing.has(metadata.source)) continue;
  const saved = join(cache, file);
  try {
    if (!(await stat(saved).catch(() => null))?.size) {
      const response = await fetch(asset, { headers: { 'User-Agent': 'SWRI local sample importer/1.0' },
                                            signal: AbortSignal.timeout(60000) });
      if (!response.ok || !response.body) throw Error('źródło HTTP ' + response.status);
      const temporary = saved + '.part';
      await pipeline(Readable.fromWeb(response.body), createWriteStream(temporary));
      await rename(temporary, saved);
    }
    const form = new FormData();
    form.set('file', await openAsBlob(saved), file);
    form.set('rights_confirmed', 'true');
    for (const [key, value] of Object.entries(metadata)) form.set(key, value);
    const published = await fetch(base + '/posts', { method: 'POST', body: form });
    if (!published.ok) throw Error(await published.text());
    const item = await published.json();
    console.log(item.title + ' — ' + item.id);
  } catch (error) {
    failed = true;
    console.error(metadata.title + ': ' + error.message);
  }
}
if (failed) process.exitCode = 1;
