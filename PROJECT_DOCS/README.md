# 📋 PyDAW Projekt-Dokumentation

**Willkommen im Dokumentations-Verzeichnis!**

Hier findest du ALLE Informationen zum Projekt.

---

## 🗂️ STRUKTUR

```
PROJECT_DOCS/
├── README.md                    # ← Du bist hier
│
├── plans/                       # Langfristige Pläne
│   ├── MASTER_PLAN.md          # ★ LIES DAS ZUERST!
│   ├── ROADMAP.md              # Version Roadmap
│   ├── AUDIO_SYSTEM.md         # ★ Audio/MIDI Routing + VU + Plugins (lies bei Audio-Fragen)
│   └── ARCHITECTURE.md         # System-Architektur
│
├── progress/                    # Aktueller Stand
│   ├── TODO.md                 # ★ Was zu tun ist
│   ├── DONE.md                 # Was erledigt ist
│   └── BUGS.md                 # Bug-Tracking
│
└── sessions/                    # Session-Logs
    ├── 2026-01-31_SESSION_1.md # ★ Neuester Stand
    ├── 2026-02-01_SESSION_2.md
    └── ...
```

---

## 🚀 SCHNELLSTART

### Als neuer Entwickler:

**1. Projekt verstehen (15min):**
```bash
# Lies diese Files in Reihenfolge:
cat plans/MASTER_PLAN.md      # Projekt-Übersicht
cat progress/TODO.md           # Was zu tun ist
cat sessions/2026-*_SESSION_*.md | tail -n 50  # Letzter Stand
```

**2. Task auswählen (5min):**
```bash
# Öffne TODO-Liste
cat progress/TODO.md

# Suche [ ] AVAILABLE Task
# Markiere ihn in TODO.md: [x] (Dein Name, Datum)
```

**3. Session starten:**
```bash
# Erstelle Session-Log
touch sessions/$(date +%Y-%m-%d)_SESSION_X.md

# Arbeite am Task
# Dokumentiere Fortschritt im Session-Log
```

**4. Session beenden:**
```bash
# Update TODO.md - Task als [x] DONE markieren
# Update DONE.md - Task eintragen
# Session-Log vervollständigen
# Commit (falls Git)
```

---

## 📚 WICHTIGSTE FILES

### ★ MASTER_PLAN.md
**Wann lesen:** Beim ersten Mal + bei Fragen zur Architektur  
**Inhalt:**
- Projekt-Übersicht
- System-Architektur
- Arbeitsablauf
- Team-Guidelines

### ★ TODO.md
**Wann lesen:** VOR JEDER SESSION  
**Inhalt:**
- Alle offenen Tasks
- Priorität (Critical/High/Medium/Low)
- Aufwands-Schätzungen
- Abhängigkeiten

### ★ Neueste SESSION_X.md
**Wann lesen:** VOR JEDER SESSION  
**Inhalt:**
- Was wurde zuletzt gemacht?
- Welche Probleme gab es?
- Was kommt als nächstes?

---

## 🔧 WORKFLOW

```
START SESSION
    ↓
Lies TODO.md
    ↓
Wähle Task
    ↓
Erstelle Session-Log
    ↓
Code schreiben
    ↓
Dokumentiere im Session-Log
    ↓
Update TODO.md & DONE.md
    ↓
Commit (optional)
    ↓
END SESSION
```

---

## 📝 TEMPLATES

### Session-Log Template
```markdown
# SESSION LOG: DATUM

## ERLEDIGTE TASKS
- [x] Task 1
- [x] Task 2

## PROBLEME & LÖSUNGEN
- Problem A → Lösung B

## NÄCHSTE SCHRITTE
- Task C steht an
```

### Git Commit Message
```
feat(component): Was wurde implementiert
fix(component): Was wurde repariert
docs: Dokumentations-Update
```

---

## 🐛 BUG-TRACKING

**Siehe:** `progress/BUGS.md`

Bug melden:
1. Erstelle Eintrag in `BUGS.md`
2. Erwähne im Session-Log
3. Markiere als Critical/High/Medium/Low

---

## 💬 HILFE

### Fragen zur Architektur?
→ Lies `plans/ARCHITECTURE.md`

### API-Fragen?
→ Siehe Code-Docstrings oder erstelle `plans/API_REFERENCE.md`

### Was kommt als nächstes?
→ Siehe `progress/TODO.md`

### Letzter Stand?
→ Siehe neueste `sessions/2026-*_SESSION_*.md`

---

**Viel Erfolg!** 🚀

