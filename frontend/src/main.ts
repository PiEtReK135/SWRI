import { bootstrapApplication } from '@angular/platform-browser';
import { Type } from '@angular/core';
import { App } from './app/app';
import { Login } from './app/login/login';
import { ReelFeed } from './app/reels/feed';
import { ScanPage } from './app/reels/scan';
import { Workspace } from './app/workspace/workspace';
import { published } from './app/published';

const pathname = window.location.pathname.replace(/\/$/, '');
let page: Type<unknown> = App;
if (published) {
  if (new URLSearchParams(location.search).get('widok') === 'analiza') page = Workspace;
} else {
  const pages = new Map<string, Type<unknown>>([
    ['/admin/login', Login], ['/rolki', ReelFeed], ['/skanowanie', ScanPage], ['/analiza', Workspace],
  ]);
  page = pages.get(pathname) ?? App;
}

bootstrapApplication(page).catch((error: unknown) => console.error(error));
