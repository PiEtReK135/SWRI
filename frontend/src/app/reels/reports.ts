import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { Rating, Review, ReviewDetail, ScanStatus, dateLabel, decisions, request, risks, secondsLabel } from './reel-api';
import { criteriaShare } from '../review-criteria';

interface ReportPage { total: number; items: Review[] }
type Tab = 'summary' | 'details' | 'ratings';

@Component({
  selector: 'reel-reports',
  templateUrl: './reports.html',
  styleUrl: './reports.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReelReports {
  protected readonly tab = signal<Tab>('summary');
  protected readonly filter = signal('');
  protected readonly riskFilter = signal('');
  protected readonly offset = signal(0);
  protected readonly pageSize = 12;
  protected readonly reviews = signal<ReportPage>({ total: 0, items: [] });
  protected readonly ratings = signal<Rating[]>([]);
  protected readonly detail = signal<ReviewDetail | null>(null);
  protected readonly selected = signal('');
  protected readonly status = signal<ScanStatus | null>(null);
  protected readonly error = signal('');
  protected readonly decisions = decisions;
  protected readonly risks = risks;
  protected readonly criteriaShare = criteriaShare;
  protected readonly contentTypes: Record<string, string> = {
    PROMOTION: 'Promocja inwestycyjna', RECOMMENDATION: 'Rekomendacja inwestycyjna',
    FORECAST: 'Prognoza inwestycyjna', INVESTMENT_ANALYSIS: 'Analiza inwestycyjna',
    FINANCE_INFORMATION: 'Informacja lub edukacja finansowa', OTHER: 'Inna tematyka',
    UNCLEAR: 'Temat nieustalony',
  };
  protected readonly inferenceLabels: Record<string, string> = {
    REGUŁY: 'Reguły lokalne', UNAVAILABLE: 'Model niedostępny', REGUŁY_AWARYJNIE: 'Reguły lokalne po błędzie modelu',
    MODEL_PARTIAL: 'Reguły lokalne i część odpowiedzi modelu',
  };
  protected readonly ruleStatuses: Record<string, string> = {
    POTENTIAL_ISSUE: 'Potencjalny problem', NEEDS_REVIEW: 'Do weryfikacji', PASS: 'Dowód spełnienia',
    NOT_APPLICABLE: 'Brak przesłanki', UNASSESSED: 'Brak danych do oceny',
  };
  protected readonly label = secondsLabel;
  protected readonly date = dateLabel;
  protected readonly channel: Record<string, string> = {
    ASR: 'Mowa', OCR: 'Tekst na ekranie', DESCRIPTION: 'Opis',
  };
  protected readonly coverageLabels: Record<string, string> = {
    CHECKED: 'Sprawdzono', ERROR: 'Błąd analizy', NOT_APPLICABLE: 'Brak ścieżki',
  };
  protected readonly keys = Object.keys;
  protected readonly channels = ['ASR', 'OCR', 'DESCRIPTION'];

  constructor() {
    void this.refresh();
    const timer = window.setInterval(() => void this.refresh(), 2500);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  private async refresh(): Promise<void> {
    const tab = this.tab();
    const offset = this.offset();
    const filter = tab === 'summary' ? 'REVIEW' : this.filter();
    const risk = tab === 'summary' ? this.riskFilter() : '';
    try {
      const status = await request<ScanStatus>('/api/scan/status');
      this.status.set(status);
      if (tab === 'ratings') {
        this.ratings.set(await request<Rating[]>('/api/scan/ratings'));
      } else {
        const query = new URLSearchParams({ offset: String(offset), limit: String(this.pageSize) });
        if (filter) query.set('decision', filter);
        if (risk) query.set('risk', risk);
        const reviews = await request<ReportPage>('/api/scan/reports?' + query);
        if (tab === this.tab() && offset === this.offset()
          && (tab === 'summary' ? risk === this.riskFilter() : filter === this.filter())) {
          this.reviews.set(reviews);
        }
      }
      this.error.set('');
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Nie udało się wczytać wyników.');
    }
  }

  protected show(tab: Tab, filter = ''): void {
    this.tab.set(tab);
    this.filter.set(filter);
    this.offset.set(0);
    this.reviews.set({ total: 0, items: [] });
    this.selected.set('');
    this.detail.set(null);
    void this.refresh();
  }

  protected page(direction: number): void {
    this.offset.update(value => Math.max(0, value + direction * this.pageSize));
    this.selected.set('');
    this.detail.set(null);
    void this.refresh();
  }

  protected chooseRisk(event: Event): void {
    this.riskFilter.set((event.target as HTMLSelectElement).value);
    this.show('summary');
  }

  protected async inspect(item: Review): Promise<void> {
    const selected = item.run + '/' + item.reel;
    if (this.selected() === selected) {
      this.selected.set('');
      this.detail.set(null);
      return;
    }
    this.selected.set(selected);
    this.detail.set(null);
    try {
      const detail = await request<ReviewDetail>('/api/scan/reports/' + selected);
      if (this.selected() === selected) this.detail.set(detail);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Brak raportu.');
    }
  }

  protected evidence(item: Review, artifact: string): string {
    return `/api/scan/evidence/${item.run}/${item.reel}/${encodeURIComponent(artifact)}`;
  }

  protected lines(report: ReviewDetail, channel: string) {
    return report.timeline.filter(line => line.kind === channel);
  }
}
