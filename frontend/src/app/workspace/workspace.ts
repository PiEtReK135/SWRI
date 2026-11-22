import { CUSTOM_ELEMENTS_SCHEMA, ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { jsonPost, request } from '../reels/reel-api';
import { published } from '../published';
import { criteriaShare, reviewAreas } from '../review-criteria';
import { realModeParam } from '../site-links';
import type { WorkspaceMode } from '../site-links';

interface Finding { module: string | null; text: string; points: number; rule_id?: string; quotes: string[] }
interface Company { name: string; registry_url?: string; registry_checked_at?: string }
interface RegistryCompany extends Company {
  in_scope: boolean; is_demo: boolean; advisory_authorized: boolean | null;
}
interface Proof { kind: string; quote: string; start_ms: number | null; artifact?: string }
interface Rule { rule_id: string; title: string; status: string; why: string; points: number }
interface Material {
  id: string; source: string; kind: string; actor: string; title: string; url: string; published: string;
  first_seen?: string; last_seen: string; modules: string[]; review: string; operator?: string; note?: string;
  analyzed_at?: string;
  score: number; risk: string | null; findings: Finding[]; companies: Company[]; platforms?: string[];
  label?: string; payer?: string; authorization?: string; language?: string; inference?: { qualification: string; uknf: string };
  limits?: string[]; limitations?: string[]; timeline?: Proof[]; rules?: Rule[];
  coverage: Record<string, string>; report_url?: string; landing_url?: string; has_media?: boolean; seconds?: number;
  related?: { id: string; source: string; url: string; title: string; actor: string; similarity: number }[];
  review_history?: { created: string; status: string; operator: string; note: string }[];
}
interface CasePage {
  items: Material[]; total: number; threshold: number; above_threshold: number; groups: Record<string, number>;
  trend: { date: string; count: number }[]; calibration: { tp: number; fp: number; fn: number; tn: number };
}
interface Queue {
  scheduled: boolean; interval_minutes: number; settings: { next_run: string; threshold: number };
  sources: { id: string; name: string; status: string; ready: boolean }[];
  jobs: { id: number; source: string; target: string; status: string; records: number; error: string | null }[];
}
interface PublishedSnapshot {
  generated_at: string;
  records: (Material & { mode: WorkspaceMode })[];
}

@Component({
  selector: 'app-root', schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './workspace.html', styleUrl: './workspace.css', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Workspace {
  protected readonly published = published;
  private readonly catalogSize = reviewAreas.reduce((total, area) => total + area.criteria.length, 0);
  protected readonly snapshotTime = signal('');
  protected readonly modules = [
    { id: '', title: 'Przegląd', detail: 'Wszystkie materiały' },
    { id: 'M1', title: 'Monitoring reklam', detail: 'Finfluencerzy i podmioty trzecie' },
    { id: 'M2', title: 'Informacje o ryzyku', detail: 'Materiały własne firm inwestycyjnych' },
    { id: 'M3', title: 'Shadow Advisory', detail: 'Oferty indywidualnego doradztwa' },
  ];
  protected readonly kinds: Record<string, string> = {
    PAID_AD: 'Kampania płatna', DISCLOSED_POST: 'Oznaczona współpraca', WEB_PAGE: 'Publiczna strona WWW',
    SIMULATED_POST: 'Rolka z lokalnego feedu',
  };
  protected readonly sources: Record<string, string> = {
    META: 'Meta', FACEBOOK: 'Facebook', INSTAGRAM: 'Instagram', TIKTOK: 'TikTok', WEB: 'Witryny WWW',
    LOCAL_FEED: 'Lokalny feed', TIKTOK_ADS: 'TikTok Ads', TIKTOK_POSTS: 'TikTok — współprace',
  };
  protected readonly risks: Record<string, string> = { HIGH: 'Wysoki', MEDIUM: 'Średni', LOW: 'Niski' };
  protected readonly reviews: Record<string, string> = {
    NEW: 'Nowe', IN_REVIEW: 'W analizie', CONFIRMED_EVIDENCE: 'Potwierdzono sygnał', DISMISSED: 'Odrzucone',
  };
  protected readonly labels: Record<string, string> = {
    READY: 'Skonfigurowane', ACCESS_REQUIRED: 'Wymaga dostępu do API', SETUP_REQUIRED: 'Wymaga konfiguracji witryn',
    QUEUED: 'W kolejce', RUNNING: 'W trakcie', DONE: 'Zakończone', BLOCKED: 'Wstrzymane', FAILED: 'Błąd',
    CHECKED: 'Sprawdzono', UNAVAILABLE: 'Brak materiału', NOT_APPLICABLE: 'Nie dotyczy', ERROR: 'Błąd',
    DESCRIPTION: 'Tekst / opis', ASR: 'Mowa', OCR: 'Tekst na ekranie', ASR_SUBTITLE: 'Napisy', CAPTION: 'Napisy',
    PASS: 'Spełnione', UNASSESSED: 'Nieocenione', NEEDS_REVIEW: 'Do weryfikacji', POSSIBLE_GAP: 'Możliwy brak',
  };

  private readonly query = new URLSearchParams(location.search);
  protected readonly mode = signal<WorkspaceMode>(this.query.get('tryb') === realModeParam ? 'REAL' : 'SIMULATION');
  protected readonly module = signal(this.modules.some(item => item.id === this.query.get('modul')) ? this.query.get('modul')! : '');
  protected readonly source = signal('');
  protected readonly risk = signal('');
  protected readonly since = signal('');
  protected readonly until = signal('');
  protected readonly onlyAbove = signal(false);
  protected readonly page = signal<CasePage | null>(null);
  protected readonly queue = signal<Queue | null>(null);
  protected readonly registry = signal<RegistryCompany[]>([]);
  protected readonly selected = signal<Material | null>(null);
  protected readonly loading = signal(true);
  protected readonly pending = signal(false);
  protected readonly live = signal(false);
  protected readonly alert = signal('');
  protected readonly notice = signal('');
  protected readonly error = signal('');
  protected readonly threshold = signal(55);
  protected readonly pageSize = 20;
  protected readonly offset = signal(0);
  protected readonly date = new Intl.DateTimeFormat('pl', {
    dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Europe/Warsaw',
  });
  private snapshot?: PublishedSnapshot;
  private generation = 0;
  private detailGeneration = 0;
  private socket?: WebSocket;
  private retry?: number;
  private cursor?: number;
  private closed = false;

  constructor() {
    document.title = 'Analiza rynku | SWRI';
    void this.refresh();
    if (published) return;
    void this.loadRegistry();
    this.connect();
    const timer = window.setInterval(() => {
      const jobs = this.queue()?.jobs || [];
      if (this.mode() === 'SIMULATION' || this.queue()?.scheduled || jobs.some(job => ['RUNNING', 'QUEUED'].includes(job.status))) {
        void this.refresh(true);
      }
    }, 5000);
    inject(DestroyRef).onDestroy(() => {
      this.closed = true;
      clearInterval(timer);
      clearTimeout(this.retry);
      this.socket?.close();
    });
  }

  protected switchMode(mode: WorkspaceMode): void {
    if (this.mode() === mode) return;
    this.mode.set(mode);
    this.source.set('');
    this.filter();
  }

  protected switchModule(module: string): void {
    this.module.set(module);
    this.filter();
  }

  protected filter(): void {
    this.offset.set(0);
    this.closeDetail();
    const url = new URL(location.href);
    if (this.mode() === 'REAL') {
      url.searchParams.set('tryb', realModeParam);
    } else {
      url.searchParams.delete('tryb');
    }
    this.module() ? url.searchParams.set('modul', this.module()) : url.searchParams.delete('modul');
    history.replaceState(null, '', url);
    void this.refresh();
  }

  protected async refresh(quiet = false): Promise<void> {
    if (quiet && this.loading()) return;
    const generation = ++this.generation;
    if (!quiet) {
      this.error.set('');
      this.loading.set(true);
    }
    const query = this.filters();
    query.set('offset', String(this.offset()));
    query.set('limit', String(this.pageSize));
    try {
      if (published) {
        this.snapshot ??= await request<PublishedSnapshot>('snapshot.json');
        if (generation === this.generation) this.showSnapshot(this.snapshot);
        return;
      }
      const [page, queue] = await Promise.all([
        request<CasePage>('/api/workspace/cases?' + query), request<Queue>('/api/workspace/sources'),
      ]);
      if (generation !== this.generation) return;
      if (this.offset() >= page.total && this.offset() > 0) {
        this.offset.set(Math.max(0, Math.floor((page.total - 1) / this.pageSize) * this.pageSize));
        void this.refresh();
        return;
      }
      this.page.set(page);
      this.queue.set(queue);
      if (!quiet) this.threshold.set(page.threshold);
    } catch (error) {
      if (generation === this.generation) this.report(error);
    } finally {
      if (generation === this.generation) this.loading.set(false);
    }
  }

  private showSnapshot(snapshot: PublishedSnapshot): void {
    this.snapshotTime.set(snapshot.generated_at);
    const items = snapshot.records.filter(item => {
      const day = (item.published || item.first_seen || item.last_seen).slice(0, 10);
      return item.mode === this.mode() &&
        (!this.module() || item.modules.includes(this.module())) &&
        (!this.source() || item.source === this.source()) &&
        (!this.risk() || item.risk === this.risk()) &&
        (!this.since() || day >= this.since()) &&
        (!this.until() || day <= this.until());
    }).sort((left, right) => right.score - left.score || right.last_seen.localeCompare(left.last_seen));
    this.page.set({
      items: items.slice(this.offset(), this.offset() + this.pageSize), total: items.length,
      threshold: 0, above_threshold: 0, groups: {}, trend: [], calibration: { tp: 0, fp: 0, fn: 0, tn: 0 },
    });
  }

  private filters(): URLSearchParams {
    const query = new URLSearchParams({ mode: this.mode(), above_threshold: String(this.onlyAbove()) });
    for (const [key, value] of Object.entries({
      module: this.module(), source: this.source(), risk: this.risk(), since: this.since(), until: this.until(),
    })) {
      if (value) query.set(key, value);
    }
    return query;
  }

  protected exportUrl(): string { return '/api/workspace/cases.csv?' + this.filters(); }

  protected paginate(offset: number): void {
    this.offset.set(offset);
    this.closeDetail();
    void this.refresh();
  }

  protected async run(source = ''): Promise<void> {
    this.pending.set(true);
    this.error.set('');
    this.notice.set('');
    try {
      const result = await request<{ queued: number }>('/api/workspace/collect' +
        (source ? '?source=' + encodeURIComponent(source) : ''), { method: 'POST' });
      this.notice.set(result.queued ? 'Dodano zadania do kolejki: ' + result.queued : 'Brak nowych zadań do dodania.');
      await this.refresh();
    } catch (error) { this.report(error); }
    finally { this.pending.set(false); }
  }

  protected async saveThreshold(): Promise<void> {
    this.pending.set(true);
    try {
      await request('/api/workspace/threshold', { ...jsonPost({ threshold: this.threshold() }), method: 'PATCH' });
      this.notice.set('Zapisano próg selekcji.');
      this.offset.set(0);
      await this.refresh();
    } catch (error) { this.report(error); }
    finally { this.pending.set(false); }
  }

  protected async open(item: Material): Promise<void> {
    const generation = ++this.detailGeneration;
    this.detailBusy(item);
    if (published) return;
    try {
      const detail = await request<Material>(this.endpoint(item));
      if (generation === this.detailGeneration) this.selected.set(detail);
    } catch (error) {
      if (generation === this.detailGeneration) this.report(error);
    }
  }

  private detailBusy(item: Material): void {
    this.selected.set(item);
    this.error.set('');
  }

  protected closeDetail(): void { this.detailGeneration++; this.selected.set(null); }

  protected async review(event: SubmitEvent, item: Material): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.target as HTMLFormElement);
    await this.update(item, this.endpoint(item), {
      ...jsonPost({ review: form.get('review'), operator: form.get('operator'), note: form.get('note') }), method: 'PATCH',
    }, 'Zapisano decyzję analityka.');
  }

  protected async upload(event: SubmitEvent, item: Material): Promise<void> {
    event.preventDefault();
    await this.update(item, this.endpoint(item) + '/media', {
      method: 'POST', body: new FormData(event.target as HTMLFormElement),
    }, 'Zakończono analizę dołączonego materiału.');
  }

  protected async register(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.target as HTMLFormElement);
    const parts = (key: string) => String(form.get(key) || '').split(',').map(value => value.trim()).filter(Boolean);
    this.pending.set(true);
    this.error.set('');
    try {
      const advisory = form.get('advisory');
      await request('/entities', jsonPost({
        name: form.get('name'), registry_url: form.get('registry_url'), registry_checked_at: form.get('registry_checked_at'),
        publisher_url: form.get('publisher_url'), publisher_ids: parts('publisher_ids'), aliases: parts('aliases'), in_scope: true,
        advisory_authorized: advisory === '' ? null : advisory === 'true',
        market_presence: form.get('market_presence'),
      }));
      this.notice.set('Zapisano zweryfikowany podmiot w kartotece.');
      (event.target as HTMLFormElement).reset();
      await this.loadRegistry();
    } catch (error) { this.report(error); }
    finally { this.pending.set(false); }
  }

  private async loadRegistry(): Promise<void> {
    try {
      const entries = await request<RegistryCompany[]>('/entities');
      this.registry.set(entries.filter(entry => entry.in_scope && !entry.is_demo)
        .sort((left, right) => left.name.localeCompare(right.name, 'pl')));
    } catch (error) { this.report(error); }
  }

  protected jobError(code: string): string {
    if (/^META_(190|102)(_|$)/.test(code)) return code + ' · Meta odrzuciła token dostępu';
    if (/^META_(10|200)(_|$)/.test(code)) return code + ' · Brak uprawnienia do odczytu w Meta';
    if (code === 'META_613' || code === 'HTTP_429') return code + ' · Limit żądań';
    return code;
  }

  protected providerState(provider: Queue['sources'][number], state: Queue): string {
    if (provider.id === 'META' && provider.ready) {
      const last = state.jobs.find(job => job.source === 'META' && ['BLOCKED', 'DONE', 'FAILED'].includes(job.status));
      if (/^META_(190|102)(_|$)/.test(last?.error || '')) return 'Token odrzucony przez Meta';
      if (/^META_(10|200)(_|$)/.test(last?.error || '')) return 'Brak uprawnienia do Ad Library API';
    }
    return this.labels[provider.status];
  }

  private async update(item: Material, url: string, options: RequestInit, notice: string): Promise<void> {
    this.pending.set(true);
    this.error.set('');
    try {
      const updated = await request<Material>(url, options);
      if (this.selected()?.id === item.id) this.selected.set(updated);
      this.notice.set(notice);
      await this.refresh();
    } catch (error) { this.report(error); }
    finally { this.pending.set(false); }
  }

  private endpoint(item: Material): string {
    return '/api/workspace/' + (item.source === 'LOCAL_FEED' ? 'simulation/' : 'cases/') +
      item.id.split('/').map(encodeURIComponent).join('/');
  }

  protected timestamp(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : this.date.format(date);
  }

  protected proofUrl(item: Material, artifact: string): string {
    return (item.source === 'LOCAL_FEED' ? '/api/scan/evidence/' : '/api/workspace/evidence/') +
      item.id + '/' + encodeURIComponent(artifact);
  }

  protected chartHeight(count: number, trend: CasePage['trend']): number {
    return 100 * count / Math.max(1, ...trend.map(point => point.count));
  }

  protected criteriaResult(item: Material): string | null {
    const evaluated = item.rules?.length ? item.rules : null;
    const flagged = new Set((evaluated ?? item.findings)
      .filter(entry => entry.rule_id && entry.points > 0).map(entry => entry.rule_id)).size;
    const hasAssessment = evaluated || flagged || (item.source !== 'LOCAL_FEED' && item.modules.includes('M2'));
    return hasAssessment ? criteriaShare(flagged, evaluated?.length ?? this.catalogSize) : null;
  }
  protected canRun(queue: Queue): boolean { return queue.sources.some(source => source.ready); }
  protected coverage(item: Material): [string, string][] { return Object.entries(item.coverage || {}); }

  private report(error: unknown): void {
    this.error.set(error instanceof Error ? error.message : 'Nie udało się zaktualizować panelu.');
  }

  private connect(): void {
    if (this.closed) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const suffix = this.cursor === undefined ? '' : '?after=' + this.cursor;
    this.socket = new WebSocket(protocol + '//' + location.host + '/api/workspace/alerts' + suffix);
    this.socket.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.type === 'ready') {
        this.cursor = data.cursor;
        this.live.set(true);
      }
      if (data.type === 'high_risk') {
        this.cursor = data.sequence;
        this.alert.set('Wysoki priorytet · ' + (data.title || 'Nowy materiał') + ' · ' + data.modules.join(', '));
        if (this.mode() === 'REAL') void this.refresh(true);
      }
    };
    this.socket.onclose = () => {
      this.live.set(false);
      if (!this.closed) this.retry = window.setTimeout(() => this.connect(), 5000);
    };
  }
}
