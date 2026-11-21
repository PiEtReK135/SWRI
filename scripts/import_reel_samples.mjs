import { mkdir, rename, stat } from 'node:fs/promises';
import { createWriteStream, openAsBlob } from 'node:fs';
import { execFile } from 'node:child_process';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { promisify } from 'node:util';

const run = promisify(execFile);

// Authentic Polish audio. The local waveform is added to make each sample playable as a reel.
const samples = [
  {
    file: 'Stepy-akermanskie.mp3',
    asset: 'https://wolnelektury.pl/media/book/mp3/adam-mickiewicz-sonety-krymskie-stepy-akermanskie.mp3',
    source: 'https://wolnelektury.pl/katalog/lektura/sonety-krymskie-stepy-akermanskie/',
    title: 'Stepy akermańskie', creator: 'wolne_lektury',
    description: 'Fragment literatury polskiej z audiobiblioteki Wolne Lektury. Obraz przedstawia przebieg dźwięku.',
    credit: 'Adam Mickiewicz · czyta Jan Dravnel · reż. Sebastian Buttny · Wolne Lektury · fragment z wizualizacją',
  },
  {
    file: 'Ptasie-radio.mp3',
    asset: 'https://wolnelektury.pl/media/book/mp3/tuwim-ptasie-radio.mp3',
    source: 'https://wolnelektury.pl/katalog/lektura/tuwim-ptasie-radio/',
    title: 'Ptasie radio', creator: 'wolne_lektury',
    description: 'Fragment literatury polskiej z audiobiblioteki Wolne Lektury. Obraz przedstawia przebieg dźwięku.',
    credit: 'Julian Tuwim · czyta Diana Giurow · reż. Studio Postęp · Wolne Lektury · fragment z wizualizacją',
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
    const reelName = file.replace(/\.mp3$/, '.mp4');
    const upload = join(cache, reelName);
    if (!(await stat(upload).catch(() => null))?.size) {
      await run('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x111727:s=360x640:r=24',
        '-i', saved, '-filter_complex',
        '[1:a]showwaves=s=300x112:mode=cline:colors=0x71d3c3:r=24[wave];[0:v][wave]overlay=(W-w)/2:(H-h)/2[out]',
        '-map', '[out]', '-map', '1:a', '-t', '35', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-threads', '2', upload]);
    }
    const form = new FormData();
    form.set('file', await openAsBlob(upload), reelName);
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
