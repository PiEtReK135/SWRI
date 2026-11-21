import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { Login } from './app/login/login';

const pathname = window.location.pathname.replace(/\/$/, '');
const page = pathname === '/admin/login' ? Login : App;

bootstrapApplication(page).catch((error: unknown) => console.error(error));
