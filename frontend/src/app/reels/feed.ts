import { ChangeDetectionStrategy, Component, ElementRef, signal, viewChild } from '@angular/core';
import { Engagement, Reel, jsonPost, mediaUrl, request, topics } from './reel-api';

@Component({
  selector: 'app-root',
  templateUrl: './feed.html',
  styleUrl: './feed.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(window:pagehide)': 'recordWatch()' },
})
export class ReelFeed {
  protected readonly current = signal<Reel | null>(null);
  protected readonly engagement = signal<Engagement>({ counts: {}, mine: [], comments: [] });
  protected readonly waiting = signal(false);
  protected readonly exhausted = signal(false);
  protected readonly error = signal('');
  protected readonly notice = signal('');
  protected readonly sound = signal(false);
  protected readonly showComments = signal(false);
  private readonly publisher = viewChild<ElementRef<HTMLDialogElement>>('publisher');
  protected readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');
  protected readonly topics = topics;
  protected readonly mediaUrl = mediaUrl;
  protected readonly encodeCreator = encodeURIComponent;
  private readonly items: Reel[] = [];
  private readonly seen = new Set<string>();
  private readonly viewer = localStorage.getItem('swri-viewer') || crypto.randomUUID();
  private readonly query = new URLSearchParams(location.search);
  protected readonly profile = this.query.get('autor');
  protected readonly publishing = signal(false);
  protected readonly index = signal(-1);
  private shownAt = 0;
  private wheelTime = 0;
  private touchY = 0;

  constructor() {
    localStorage.setItem('swri-viewer', this.viewer);
    document.title = 'Rolki | SWRI';
    const post = this.query.get('post');
    if (post) void this.open(post);
    else void this.next();
  }

  private endpoint(id: string, suffix: string): string {
    return `/api/reels/posts/${encodeURIComponent(id)}/${suffix}?viewer=${encodeURIComponent(this.viewer)}`;
  }

  private async open(id: string): Promise<void> {
    try {
      this.add(await request<Reel>('/api/reels/posts/' + encodeURIComponent(id)));
    } catch {
      await this.next();
    }
  }

  private add(item: Reel): void {
    this.items.splice(this.index() + 1);
    this.items.push(item);
    this.show(this.items.length - 1);
  }

  private show(index: number): void {
    const item = this.items[index];
    this.index.set(index);
    this.current.set(item);
    this.seen.add(item.id);
    this.shownAt = performance.now();
    this.notice.set('');
    this.exhausted.set(false);
    this.showComments.set(false);
    this.engagement.set({ counts: {}, mine: [], comments: [] });
    const url = new URL(location.href);
    url.searchParams.set('post', item.id);
    history.replaceState(null, '', url);
    void this.loadEngagement(item.id).catch(error => this.showError(error));
  }

  protected async next(): Promise<void> {
    if (this.waiting()) return;
    this.waiting.set(true);
    this.error.set('');
    try {
      await this.recordWatch();
      if (this.index() + 1 < this.items.length) {
        this.show(this.index() + 1);
        return;
      }
      const query = new URLSearchParams({ viewer: this.viewer, limit: '1' });
      if (this.profile) query.set('creator', this.profile);
      Array.from(this.seen).slice(-200).forEach(id => query.append('seen', id));
      const [item] = await request<Reel[]>('/api/reels/feed?' + query);
      if (item) this.add(item);
      else this.exhausted.set(true);
    } catch (error) {
      this.showError(error);
    } finally {
      this.waiting.set(false);
    }
  }

  protected previous(): void {
    if (this.waiting() || this.index() <= 0) return;
    void this.recordWatch();
    this.show(this.index() - 1);
  }

  protected recordWatch(): Promise<void> {
    const item = this.current();
    if (!item) return Promise.resolve();
    const player = this.video()?.nativeElement;
    let ratio = Math.min(1, (performance.now() - this.shownAt) / 6000);
    if (item.kind === 'video') {
      let played = 0;
      if (player) {
        for (let i = 0; i < player.played.length; i++) played += player.played.end(i) - player.played.start(i);
      }
      ratio = Math.min(1, played / item.duration);
    }
    if (ratio < 0.05) return Promise.resolve();
    return request(this.endpoint(item.id, 'signals'), {
      ...jsonPost({ action: 'watch', value: ratio }), keepalive: true,
    }).then(() => undefined).catch(() => undefined);
  }

  protected toggleSound(): void {
    const video = this.video()?.nativeElement;
    this.sound.update(value => !value);
    if (video) {
      video.muted = !this.sound();
      if (this.sound()) void video.play().catch(() => undefined);
    }
  }

  protected keyboard(event: KeyboardEvent): void {
    if ((event.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|VIDEO/)) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (event.key === 'ArrowDown') void this.next();
      else this.previous();
    }
  }

  protected wheel(event: WheelEvent): void {
    if (Math.abs(event.deltaY) < 30 || performance.now() - this.wheelTime < 700) return;
    this.wheelTime = performance.now();
    if (event.deltaY > 0) void this.next();
    else this.previous();
  }

  protected touchStart(event: TouchEvent): void {
    this.touchY = event.changedTouches[0]?.clientY ?? 0;
  }

  protected touchEnd(event: TouchEvent): void {
    const distance = this.touchY - (event.changedTouches[0]?.clientY ?? this.touchY);
    if (distance > 60) void this.next();
    if (distance < -60) this.previous();
  }

  protected async react(action: string): Promise<void> {
    const item = this.current();
    if (!item) return;
    try {
      if (action === 'share') {
        const url = new URL('/rolki', location.origin);
        url.searchParams.set('post', item.id);
        await navigator.clipboard.writeText(url.href);
        this.notice.set('Skopiowano link.');
      }
      const value = ['like', 'save'].includes(action) && this.engagement().mine.includes(action) ? 0 : 1;
      await request(this.endpoint(item.id, 'signals'), jsonPost({ action, value }));
      if (action === 'not_interested') {
        this.items.splice(this.index(), 1);
        this.index.update(value => value - 1);
        this.current.set(null);
        const url = new URL(location.href);
        url.searchParams.delete('post');
        history.replaceState(null, '', url);
        await this.next();
        if (!this.current()) this.notice.set('Ukryto rolkę w Twoim feedzie.');
      } else {
        await this.loadEngagement(item.id);
      }
    } catch (error) {
      this.showError(error);
    }
  }

  private async loadEngagement(id: string): Promise<void> {
    const result = await request<Engagement>(this.endpoint(id, 'engagement'));
    if (this.current()?.id === id) this.engagement.set(result);
  }

  protected async comment(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const item = this.current();
    const form = event.currentTarget as HTMLFormElement;
    if (!item) return;
    try {
      await request(this.endpoint(item.id, 'comments'), jsonPost({ text: new FormData(form).get('text') }));
      form.reset();
      await this.loadEngagement(item.id);
    } catch (error) {
      this.showError(error);
    }
  }

  protected async publish(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    this.publishing.set(true);
    this.error.set('');
    try {
      const item = await request<Reel>('/api/reels/posts', { method: 'POST', body: new FormData(form) });
      form.reset();
      this.publisher()?.nativeElement.close();
      this.add(item);
      this.notice.set('Rolka opublikowana.');
    } catch (error) {
      this.showError(error);
    } finally {
      this.publishing.set(false);
    }
  }

  protected openPublisher(): void {
    this.error.set('');
    this.publisher()?.nativeElement.showModal();
  }

  protected closePublisher(): void {
    this.publisher()?.nativeElement.close();
  }

  private showError(error: unknown): void {
    this.error.set(error instanceof Error ? error.message : 'Operacja nie powiodła się.');
  }
}
