import { CUSTOM_ELEMENTS_SCHEMA, ChangeDetectionStrategy, Component } from '@angular/core';
import { projectModules } from './project-modules';
import { reviewAreas } from './review-criteria';
import { ReelReports } from './reels/reports';
import { published } from './published';
import { workspaceLink } from './site-links';

@Component({
  selector: 'app-root',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './app.html',
  styleUrl: './app.css',
  imports: [ReelReports],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly published = published;
  protected readonly workspaceLink = workspaceLink;
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
