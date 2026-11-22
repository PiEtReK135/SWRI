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
  luminance_span?: number | null;
  relative_text_height?: number;
  responsive_css_px?: Record<string, number>;
}

export interface Reason {
  text: string;
  evidence: Evidence[];
  rule_id?: string | null;
  points?: number;
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
  saved: string;
  category: string;
  content_type?: string;
  priority_count?: number | null;
  priority_percent?: number | null;
  uknf_status?: string;
  criteria_count?: number;
  finding_count?: number;
  market_language?: string;
  url: string;
}

export interface ReviewDetail extends Review {
  unverified_companies?: string[];
  coverage: Record<string, string>;
  timeline: Evidence[];
  limitations: string[];
  feedback: string;
  inference?: { qualification: string; uknf: string; reason?: string; timeline_rows?: number;
                context_pages?: number; semantic_checks?: number };
  rules: { rule_id: string; title: string; status: string; why: string; points?: number;
           legal_basis: string; evidence?: Evidence[]; counter_evidence?: Evidence[];
           semantic_status?: string; method?: string }[];
}

export interface Rating {
  name: string;
  role: string;
  count: number;
  priority: number;
  criteria_count: number;
  levels: Record<string, number>;
}

export interface ScanStatus {
  id?: string;
  status: string;
  started?: string;
  ended?: string | null;
  scanned: number;
  rejected?: number;
  stage?: string;
  models?: Record<string, string>;
  progress_percent?: number | null;
  decisions?: Record<string, number>;
  average_seconds?: number;
  current?: string;
  error?: string;
  strategies: { name: string; trials: number; hits: number }[];
}

export interface ScanSession {
  id: string;
  started: string;
  ended: string | null;
  status: string;
  scanned: number;
}

export const decisions: Record<string, string> = {
  REVIEW: 'Do sprawdzenia', FINANCE_NEUTRAL: 'Edukacja lub informacja',
  OUT_OF_SCOPE: 'Poza finansami', UNRESOLVED: 'Do ponownej analizy',
  OUT_OF_MARKET: 'Poza polskim rynkiem', SCREENED_CLEAR: 'Bez sygnału UKNF',
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

export function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value));
}
