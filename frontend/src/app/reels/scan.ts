import { CUSTOM_ELEMENTS_SCHEMA, ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { ScanSession, ScanStatus, dateLabel, request } from './reel-api';
import { ReelReports } from './reports';

@Component({
  selector: 'app-root',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [ReelReports],
  templateUrl: './scan.html',
  styleUrl: './scan.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScanPage {
  protected readonly state = signal<ScanStatus | null>(null);
  protected readonly waiting = signal(false);
  protected readonly error = signal('');
  protected readonly sessions = signal<ScanSession[]>([]);
  protected readonly confirming = signal(false);
  protected readonly date = dateLabel;
  protected readonly active = new Set(['STARTING', 'SCANNING', 'WAITING', 'STOPPING']);
  protected readonly labels: Record<string, string> = {
    IDLE: 'Gotowy', STARTING: 'Uruchamianie', SCANNING: 'Analizuje rolkę',
    WAITING: 'Czeka na kolejne rolki', STOPPING: 'Kończy bieżącą analizę',
    COMPLETED: 'Zakończono', STOPPED: 'Zatrzymano', INTERRUPTED: 'Przerwano', FAILED: 'Błąd sesji',
  };
  protected readonly stages: Record<string, string> = {
    FETCH: 'Pobieranie rolki', ASR: 'Transkrypcja mowy',
    OCR: 'Tekst na ekranie', CONTEXT: 'Łączenie mowy, tekstu na ekranie i opisu',
    QUALIFY: 'Kwalifikacja do testów', UKNF: 'Ocena według kryteriów UKNF',
    SAVE: 'Zapis wyniku', DONE: 'Analiza zapisana',
  };

  constructor() {
    document.title = 'Skaner rolek | SWRI';
    const url = new URL(location.href);
    const reel = url.searchParams.get('rolka');
    if (url.searchParams.get('start') === '1' || reel) {
      void this.action('start', reel).then(ok => {
        if (ok) {
          url.searchParams.delete('start');
          url.searchParams.delete('rolka');
          history.replaceState(null, '', url);
        }
      });
    } else {
      void this.refresh();
    }
    const timer = window.setInterval(() => void this.refresh(), 1300);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  private async refresh(): Promise<void> {
    if (this.waiting()) return;
    try {
      this.state.set(await request<ScanStatus>('/api/scan/status'));
      this.sessions.set(await request<ScanSession[]>('/api/scan/sessions'));
    } catch (error) {
      this.report(error);
    }
  }

  protected async action(action: 'start' | 'stop' | 'reset', reel: string | null = null): Promise<boolean> {
    this.waiting.set(true);
    this.error.set('');
    try {
      const query = reel ? '?reel=' + encodeURIComponent(reel) : '';
      this.state.set(await request<ScanStatus>('/api/scan/' + action + query, { method: 'POST' }));
      this.sessions.set(await request<ScanSession[]>('/api/scan/sessions'));
      this.confirming.set(false);
      return true;
    } catch (error) {
      this.report(error);
      return false;
    } finally {
      this.waiting.set(false);
    }
  }

  private report(error: unknown): void {
    this.error.set(error instanceof Error ? error.message : 'Nie udało się połączyć ze skanerem.');
  }
}
