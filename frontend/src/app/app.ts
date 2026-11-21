import { ChangeDetectionStrategy, Component } from '@angular/core';
import { projectModules } from './project-modules';
import { reviewAreas } from './review-criteria';
import { ReelReports } from './reels/reports';

@Component({
  selector: 'app-root',
  templateUrl: './app.html',
  styleUrl: './app.css',
  imports: [ReelReports],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly projectModules = projectModules;
  protected readonly reviewAreas = reviewAreas;

  protected readonly navigation = [
    { id: 'analiza', label: 'Raporty' },
    { id: 'opis', label: 'Opis' },
    { id: 'moduly', label: 'Moduły' },
    { id: 'misja', label: 'Misja' },
    { id: 'agenci', label: 'Agenci' },
    { id: 'kryteria', label: 'Kryteria' },
    { id: 'kontakt', label: 'Kontakt' },
  ] as const;
}
