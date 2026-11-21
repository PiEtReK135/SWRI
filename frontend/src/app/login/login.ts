import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';

@Component({
  selector: 'app-root',
  templateUrl: './login.html',
  styleUrl: './login.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Login {
  protected readonly submitted = signal(false);

  constructor() {
    inject(Title).setTitle('Logowanie administratora — XYZ');
  }

  protected submit(event: SubmitEvent): void {
    event.preventDefault();
    this.submitted.set(true);
  }
}
