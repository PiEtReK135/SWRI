import { bootstrapApplication } from '@angular/platform-browser';
import { Type } from '@angular/core';
import { App } from './app/app';
import { Login } from './app/login/login';
import { ReelFeed } from './app/reels/feed';
import { ScanPage } from './app/reels/scan';

const pathname = window.location.pathname.replace(/\/$/, '');
const pages = new Map<string, Type<unknown>>([['/admin/login', Login], ['/rolki', ReelFeed], ['/skanowanie', ScanPage]]);
const page = pages.get(pathname) ?? App;

bootstrapApplication(page).catch((error: unknown) => console.error(error));
