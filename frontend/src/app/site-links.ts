import { published } from './published';

export function workspaceLink(simulation = false, module = ''): string {
  const query = new URLSearchParams();
  if (published) query.set('widok', 'analiza');
  if (simulation) query.set('tryb', 'symulacja');
  if (module) query.set('modul', module);
  return (published ? './' : '/analiza') + (query.size ? '?' + query : '');
}
