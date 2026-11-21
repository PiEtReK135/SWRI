interface ReviewCriterion {
  readonly id: string;
  readonly title: string;
  readonly description: string;
}

interface ReviewArea {
  readonly name: string;
  readonly criteria: readonly ReviewCriterion[];
}

export const reviewAreas: readonly ReviewArea[] = [
  {
    name: 'Identyfikacja i oznaczenia',
    criteria: [
      { id: '1', title: 'Identyfikacja firmy', description: 'Sprawdza, czy materiał podaje oficjalną nazwę firmy inwestycyjnej.' },
      { id: '2', title: 'Oznaczenie reklamy', description: 'Sprawdza, czy materiał jest jednoznacznie oznaczony jako reklamowy.' },
      { id: '17', title: 'Sugerowanie aprobaty nadzoru', description: 'Wykrywa odwołania do organu nadzoru, które mają sugerować zatwierdzenie produktu lub usługi.' },
      { id: '18', title: 'Nadzór jako argument bezpieczeństwa', description: 'Wykrywa sugestie, że inwestycja jest bezpieczna ze względu na nadzór.' },
    ],
  },
  {
    name: 'Widoczność informacji o ryzyku',
    criteria: [
      { id: '4', title: 'Rozmiar czcionki', description: 'Porównuje rozmiar ostrzeżenia z dominującym rozmiarem tekstu w reklamie.' },
      { id: '5', title: 'Kontrast i ekspozycja', description: 'Sprawdza kontrast, położenie oraz ewentualne przesłonięcie tekstu.' },
      { id: '6', title: 'Ukrywanie informacji', description: 'Sprawdza, czy ostrzeżenie umieszczono w przypisie lub innym mało widocznym miejscu.' },
      { id: '7', title: 'Dostępność ostrzeżenia', description: 'Sprawdza, czy odczytanie ostrzeżenia wymaga dodatkowego kliknięcia lub rozwinięcia treści.' },
      { id: '8', title: 'Czytelność na różnych ekranach', description: 'Sprawdza, czy tekst pozostaje czytelny na telefonie, tablecie i komputerze.' },
    ],
  },
  {
    name: 'Treść i język ostrzeżeń',
    criteria: [
      { id: '3', title: 'Zyski i ryzyko obok siebie', description: 'Sprawdza, czy deklaracji potencjalnych zysków bezpośrednio towarzyszy informacja o istotnym ryzyku.' },
      { id: '9', title: 'Zrozumiałość', description: 'Ocenia, czy język ostrzeżenia jest zrozumiały dla grupy docelowej.' },
      { id: '10', title: 'Spójność językowa', description: 'Sprawdza, czy ostrzeżenie podano w tym samym języku co główny przekaz.' },
      { id: '16', title: 'Informacja podatkowa', description: 'Sprawdza, czy przekaz podatkowy uwzględnia indywidualną sytuację klienta i możliwość zmian.' },
    ],
  },
  {
    name: 'Porównania, wyniki i prognozy',
    criteria: [
      { id: '11', title: 'Porównania produktów i usług', description: 'Weryfikuje źródła i założenia wykorzystane w porównaniu.' },
      { id: '12a', title: 'Okres i źródło wyników historycznych', description: 'Sprawdza okres odniesienia, pełne okresy 12-miesięczne z ostatnich pięciu lat oraz źródło danych.' },
      { id: '12b', title: 'Waluta i koszty', description: 'Sprawdza informacje o wpływie kursów walut, prowizji, opłat i innych obciążeń.' },
      { id: '13', title: 'Dominacja wyników historycznych', description: 'Sprawdza, czy wyniki historyczne nie są najmocniej eksponowaną częścią przekazu.' },
      { id: '14', title: 'Ostrzeżenie przy wynikach historycznych', description: 'Sprawdza obecność wyraźnego zastrzeżenia o niewiarygodności wyników historycznych jako wskaźnika przyszłych wyników.' },
      { id: '15', title: 'Prognozy przyszłych wyników', description: 'Wykrywa prognozę i sprawdza obecność ostrzeżenia o jej ograniczonej wartości jako wskaźnika przyszłych wyników.' },
    ],
  },
];
