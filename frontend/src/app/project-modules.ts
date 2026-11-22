export const projectModules = [
  {
    id: 1,
    shortTitle: 'Monitoring reklam',
    title: 'Monitoring reklam publikowanych przez osoby trzecie',
    description: 'Wyszukiwanie reklam firm inwestycyjnych publikowanych przez finfluencerów, osoby prywatne i inne podmioty. Obejmuje też polskojęzyczne reklamy zagranicznych firm działających w Polsce transgranicznie.',
    result: 'Zestawienie firmy, autora publikacji, treści reklamy i adresu źródłowego.',
  },
  {
    id: 2,
    shortTitle: 'Ocena informacji o ryzyku',
    title: 'Weryfikacja informacji o ryzyku',
    description: 'Ocena materiałów publikowanych bezpośrednio przez firmy inwestycyjne zarejestrowane w Polsce, w tym polskie oddziały firm zagranicznych. Sprawdzamy, czy ostrzeżenia są widoczne, zrozumiałe i odpowiednio wyeksponowane w stosunku do informacji o zyskach.',
    result: 'Lista materiałów i fragmentów wymagających uwagi, ze wskazaniem kryterium oceny.',
  },
  {
    id: 3,
    shortTitle: 'Shadow Advisory',
    title: 'Identyfikacja potencjalnie nieautoryzowanych usług',
    description: 'Wyszukiwanie ofert indywidualnych rekomendacji dotyczących konkretnych instrumentów finansowych. Każdy sygnał trafia do weryfikacji statusu i zakresu zezwoleń.',
    result: 'Zestawienie podmiotów, treści ofert, dowodów i adresów źródłowych.',
  },
] as const;
