import { published } from './published';

export type WorkspaceMode = 'REAL' | 'SIMULATION';
export const realModeParam = 'rzeczywiste';

export function workspaceLink(mode: WorkspaceMode = 'SIMULATION', module = ''): string {
  const query = new URLSearchParams();
  if (published) query.set('widok', 'analiza');
  if (mode === 'REAL') query.set('tryb', realModeParam);
  if (module) query.set('modul', module);
  return (published ? './' : '/analiza') + (query.size ? '?' + query : '');
}
