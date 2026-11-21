export interface Reel {
  id: string;
  title: string;
  creator: string;
  description: string;
  topic: string;
  kind: 'image' | 'video';
  duration: number;
  credit: string;
  source: string;
}

export interface Engagement {
  counts: Record<string, number>;
  mine: string[];
  comments: string[];
}

export interface Evidence {
  kind: string;
  quote: string;
  start_ms: number | null;
  artifact?: string;
}

export interface Reason {
  text: string;
  evidence: Evidence[];
}

export interface Review {
  run: string;
  reel: string;
  title: string;
  creator: string;
  role: string;
  decision: string;
  risk: string | null;
  modules: string[];
  companies: string[];
  reasons: Reason[];
  seconds: number;
  url: string;
}

export interface ReviewDetail extends Review {
  unverified_companies?: string[];
  coverage: Record<string, string>;
  timeline: Evidence[];
  limitations: string[];
  feedback: string;
  rules: { rule_id: string; title: string; status: string; why: string }[];
}

export interface Rating {
  name: string;
  role: string;
  count: number;
  priority: number;
  levels: Record<string, number>;
}

export interface ScanStatus {
  id?: string;
  status: string;
  scanned: number;
  decisions?: Record<string, number>;
  average_seconds?: number;
  current?: string;
  error?: string;
  strategies: { name: string; trials: number; hits: number }[];
}

export const topics = [
  'Rynek i inwestycje', 'Technologia', 'Kultura', 'Podróże i natura', 'Sport', 'Kuchnia', 'Inne',
];

export const decisions: Record<string, string> = {
  REVIEW: 'Do sprawdzenia', FINANCE_NEUTRAL: 'Finanse bez promocji',
  OUT_OF_SCOPE: 'Odrzucona', UNRESOLVED: 'Do ponownej analizy',
};

export const risks: Record<string, string> = { HIGH: 'Wysoki', MEDIUM: 'Średni', LOW: 'Niski' };

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new Error(typeof failure?.detail === 'string' ? failure.detail : 'Operacja nie powiodła się.');
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export function jsonPost(value: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) };
}

export const mediaUrl = (id: string) => '/api/reels/posts/' + encodeURIComponent(id) + '/media';

export function secondsLabel(ms: number): string {
  return new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 }).format(ms / 1000) + ' s';
}
