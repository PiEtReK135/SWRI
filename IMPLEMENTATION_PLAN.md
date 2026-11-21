# Implementacja

1. P0. Import lokalnego klipu i napisów, trwałe zadanie, ASR/OCR, dowody, klasyfikacja, raport i widok operatora.
2. P1. Import list URL, plan zapytań i listy obserwacyjne, rejestr firm, reguły UKNF, ponowne skany i alerty.
3. P2. Integracje platform zależne od zatwierdzonej metody dostępu.

Import zwraca `{id,status}`. Raport zawiera `modules`, `evidence` (cytat i pozycja), `rule_evaluations`, `coverage` i `priority_score`. Zadanie przechowuje status i przyczynę w SQLite.
