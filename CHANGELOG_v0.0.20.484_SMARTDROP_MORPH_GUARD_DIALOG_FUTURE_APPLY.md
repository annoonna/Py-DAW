## v0.0.20.484 — SmartDrop: Guard-Dialog auf spätere Apply-Phase vorbereitet

- `pydaw/ui/main_window.py`: Der Morphing-Guard-Dialog liefert jetzt ein Ergebnisobjekt (`shown / accepted / can_apply / requires_confirmation`) statt nur `True/False`.
- Derselbe Dialog kann spaeter bereits als echte Bestaetigungsstelle dienen, sobald `can_apply` im Guard-Vertrag freigeschaltet wird.
- Der zentrale Guard-Handler respektiert diese spaetere Struktur schon jetzt, bleibt aktuell aber bewusst **nicht-mutierend**.
- Safety first: weiterhin kein echtes Audio->Instrument-Morphing, kein Routing-Umbau, keine Projektmutation.
