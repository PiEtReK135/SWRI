import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { ScanStatus, request } from './reel-api';
import { ReelReports } from './reports';

@Component({
  selector: 'app-root',
  imports: [ReelReports],
  templateUrl: './scan.html',
  styleUrl: './scan.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScanPage {
  protected readonly state = signal<ScanStatus | null>(null);
  protected readonly waiting = signal(false);
  protected readonly error = signal('');
  protected readonly active = new Set(['STARTING', 'SCANNING', 'WAITING', 'STOPPING']);
  protected readonly labels: Record<string, string> = {
    IDLE: 'Gotowy', STARTING: 'Uruchamianie', SCANNING: 'Analizuje rolkę',
    WAITING: 'Czeka na kolejne rolki', STOPPING: 'Kończy bieżącą analizę',
    COMPLETED: 'Zakończono', STOPPED: 'Zatrzymano', INTERRUPTED: 'Przerwano', FAILED: 'Błąd sesji',
  };

  constructor() {
    document.title = 'Skaner rolek | SWRI';
    const url = new URL(location.href);
    if (url.searchParams.get('start') === '1') {
      void this.action('start').then(ok => {
        if (ok) {
          url.searchParams.delete('start');
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
    } catch (error) {
      this.report(error);
    }
  }

  protected async action(action: 'start' | 'stop'): Promise<boolean> {
    this.waiting.set(true);
    this.error.set('');
    try {
      this.state.set(await request<ScanStatus>('/api/scan/' + action, { method: 'POST' }));
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
