import { mkdir, rename, stat } from 'node:fs/promises';
import { openAsBlob } from 'node:fs';
import { execFile } from 'node:child_process';
import { join } from 'node:path';
import { promisify } from 'node:util';

const run = promisify(execFile);

const finance = 'https://zpe.gov.pl/a/kapital-czyli-jak-inwestowac-oszczednosci-na-rynku-gieldowym/D18cI6Uz2';
const videoBase = 'https://static.zpe.gov.pl/portal/hls/v/1/';
const samples = [
  {
    file: 'gielda-w-polsce.mp4',
    asset: 'R13AvlfeC4AYR/1699607305/N3CHx4y3Y0ZCAOnpIgF9IufL1Ae3LP9O/',
    source: finance + '#tIjqgRBjWv_0000003F', title: 'Początki giełdy. Giełda w Polsce',
    description: 'Fragment wypowiedzi Mirosława Szczepańskiego o historii giełdy w Polsce.',
    credit: 'Contentplus.pl · ZPE · CC BY 3.0 https://creativecommons.org/licenses/by/3.0/ · fragment 00:05–00:47',
  },
  {
    file: 'inwestor-gieldowy.mp4',
    asset: 'R5SU25JRetqj6/1699607357/1athq9MItQJHEF6AEf8bRNRI8XTyObkl/',
    source: finance + '#tIjqgRBjWv_0000006N', title: 'Jak zostać inwestorem giełdowym?',
    description: 'Fragment wypowiedzi Mirosława Szczepańskiego o podstawach poznawania rynku giełdowego.',
    credit: 'Contentplus.pl · ZPE · CC BY 3.0 https://creativecommons.org/licenses/by/3.0/ · fragment 00:05–00:47',
  },
  {
    file: 'ochrona-przyrody.mp4',
    asset: 'RTw7o51JUHZIu/1713268363/1ynRVXXCYqzNSkfhqISvPXIOSCSdInM9/',
    source: 'https://zpe.gov.pl/a/dlaczego-nalezy-chronic-przyrode/DRatgwFy',
    title: 'Dlaczego należy chronić przyrodę?',
    description: 'Polski film o wpływie człowieka na przyrodę i sposobach jej ochrony.',
    credit: 'GroMar · ZPE · CC BY-SA 3.0 https://creativecommons.org/licenses/by-sa/3.0/ · fragment 00:05–00:47',
  },
];

const base = 'http://127.0.0.1:8000/api/reels';
const cache = join('data', 'sample-reels');
await mkdir(cache, { recursive: true });
const creator = 'zpe_materialy';
const feed = await fetch(base + '/feed?viewer=sample-import&limit=20&creator=' + creator);
if (!feed.ok) throw Error('Nie można odczytać lokalnego feedu');
const existing = new Set((await feed.json()).map(post => post.source));
let failed = false;
for (const { file, asset, ...metadata } of samples) {
  if (existing.has(metadata.source)) continue;
  try {
    const upload = join(cache, file);
    if (!(await stat(upload).catch(() => null))?.size) {
      const variant = videoBase + asset;
      const temporary = upload + '.part.mp4';
      await run('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-i', variant + '360p.m3u8',
        '-i', variant + 'audio/audio_1.m3u8', '-ss', '5', '-t', '42', '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-threads', '2', temporary], { timeout: 120000 });
      await rename(temporary, upload);
    }
    const form = new FormData();
    form.set('file', await openAsBlob(upload), file);
    form.set('creator', creator);
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
