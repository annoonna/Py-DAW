# 🔄 Py_DAW TEAM-RELAY ÜBERGABE-PROTOKOLL

**Dieses Dokument wird JEDEM Kollegen zusammen mit der ZIP gegeben.**
**Es erklärt den kompletten Workflow von Empfang → Arbeit → Rückgabe.**

---

## ⚠️ OBERSTE DIREKTIVE

```
🔴 DU DARFST NICHTS KAPUTT MACHEN.
🔴 Alle bestehenden Features MÜSSEN nach deiner Arbeit funktionieren.
🔴 Im Zweifel: NICHT ändern. Lieber dokumentieren und zurückgeben.
```

---

## 📥 WAS DU BEKOMMST

Du bekommst **die ZIP-Datei** → `Py_DAW_v0_0_20_XXX_TEAM_READY.zip`

Darin findest du ALLES was du brauchst:
- Den kompletten, lauffähigen Code
- `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` → **DER MASTERPLAN** mit allen Arbeitspaketen
- `PROJECT_DOCS/progress/TODO.md` → Was ist offen?
- `PROJECT_DOCS/progress/DONE.md` → Was wurde schon gemacht?
- `PROJECT_DOCS/sessions/LATEST.md` → Was der letzte Kollege gemacht hat
- Dieses Dokument → `PROJECT_DOCS/TEAM_RELAY_PROTOCOL.md`

---

## 🎯 WAS DU MACHEN SOLLST

### Du arbeitest SELBSTÄNDIG die ROADMAP ab!

```
1. Lies ROADMAP_MASTER_PLAN.md
2. Finde das nächste offene Arbeitspaket (AP) und die nächste offene Phase
3. Arbeite diese Phase ab
4. Hake ab was du erledigt hast
5. Gehe zur nächsten Phase
6. Wiederhole bis deine Session voll ist
7. Dokumentiere und gib die ZIP zurück
```

**Du brauchst KEINE Anweisungen vom Auftraggeber!**
Der Masterplan sagt dir genau was zu tun ist. Die Reihenfolge steht drin.
Die Checkboxen zeigen dir was schon erledigt ist und was als nächstes kommt.

### Empfohlene Reihenfolge (steht auch in der Roadmap):

```
AP1 (Rust Core) → AP2 (Recording) → AP5 (Routing) → AP4 (Plugins)
→ AP3 (Warp) → AP8 (FX) → AP6 (MIDI) → AP7 (Sampler)
→ AP9 (Automation) → AP10 (Export)
→ RUST DSP MIGRATION (R1–R13, siehe RUST_DSP_MIGRATION_PLAN.md)
```

Wenn AP1–AP10 alle [x] abgehakt sind, geht es weiter mit dem
**Rust DSP Migration Plan** in `PROJECT_DOCS/RUST_DSP_MIGRATION_PLAN.md`.
Dieser Plan hat eigene Phasen R1–R13 mit Checkboxen.

Innerhalb jedes APs: Phase A → Phase B → Phase C → Phase D (der Reihe nach).

### Wann gibst du zurück?

- **Idealfall:** Du arbeitest so viel wie möglich in deiner Session ab
- **Minimum:** Mindestens eine Phase komplett abschließen
- **Maximum:** So viele Phasen/APs wie du schaffst
- **Abbruch:** Wenn du bei einem Problem nicht weiterkommst → dokumentiere es, gib zurück

---

## 🔧 WIE DU ARBEITEST

### Schritt 1: ZIP entpacken und orientieren

```bash
# Entpacken
unzip Py_DAW_v0_0_20_XXX_TEAM_READY.zip -d work
cd work

# PRÜFE SOFORT:
ls pydaw/          # ← MUSS existieren!
cat VERSION        # ← Aktuelle Version lesen
cat PROJECT_DOCS/ROADMAP_MASTER_PLAN.md  # ← Gesamtplan lesen
cat PROJECT_DOCS/progress/TODO.md | head -30  # ← Was ist offen?
cat PROJECT_DOCS/progress/DONE.md | head -30  # ← Was wurde schon gemacht?
```

### Schritt 2: Lies die relevanten Dokumente

```bash
# Roadmap lesen — dein AP und deine Phase verstehen
cat PROJECT_DOCS/ROADMAP_MASTER_PLAN.md

# Letzte Session lesen — was wurde zuletzt gemacht?
cat PROJECT_DOCS/sessions/LATEST.md

# Architektur verstehen
ls PROJECT_DOCS/     # ← Alle Design-Docs
ls pydaw/            # ← Code-Struktur
```

### Schritt 3: Arbeite an deinem Auftrag

- Ändere NUR was zu deinem Auftrag gehört
- Teste JEDE geänderte Datei:
  ```bash
  python3 -c "import py_compile; py_compile.compile('pydaw/DATEI.py', doraise=True)"
  ```
- Mache KEINE "Nebenbei-Aufräumarbeiten" an Code der nicht zu deinem Auftrag gehört
- Wenn du einen Bug findest der NICHT zu deinem Auftrag gehört: **dokumentiere ihn, fixe ihn NICHT**

### Schritt 4: Dokumentiere deine Arbeit

**A) VERSION erhöhen:**
```bash
echo -n "0.0.20.XXX" > VERSION   # Nächste freie Nummer
```

**B) CHANGELOG schreiben:**
```bash
# Eine Datei pro Version im Hauptverzeichnis
cat > CHANGELOG_v0.0.20.XXX_KURZTITEL.md << 'EOF'
# CHANGELOG v0.0.20.XXX — Kurztitel

**Datum:** YYYY-MM-DD
**Autor:** [Dein Name / Claude Modell]
**Arbeitspaket:** AP X, Phase XY

## Was wurde gemacht
- Feature/Fix 1
- Feature/Fix 2

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/xxx.py | Neue Klasse YYY |

## Was als nächstes zu tun ist
- Nächster Schritt in dieser Phase
- Oder: Phase XY ist FERTIG → weiter mit Phase XZ

## Bekannte Probleme / Offene Fragen
- (falls vorhanden)
EOF
```

**C) TODO.md aktualisieren:**
```bash
# Oben einfügen — erledigte Tasks abhaken, neue AVAILABLE Tasks hinzufügen
nano PROJECT_DOCS/progress/TODO.md
```

Format:
```markdown
## v0.0.20.XXX — Kurztitel

- [x] (Autor, Datum): **Was erledigt wurde** — Kurzbeschreibung
- [ ] AVAILABLE: **Was als nächstes zu tun ist** — Kurzbeschreibung
```

**D) DONE.md aktualisieren:**
```markdown
## v0.0.20.XXX — Kurztitel

- [x] (Autor, Datum): **Was erledigt wurde**
```

**E) Session-Log schreiben:**
```bash
cat > PROJECT_DOCS/sessions/SESSION_v0.0.20.XXX_KURZTITEL.md << 'EOF'
# Session Log — v0.0.20.XXX

**Datum:** YYYY-MM-DD
**Kollege:** [Name/Modell]
**Arbeitspaket:** AP X, Phase XY
**Aufgabe:** [Was sollte gemacht werden]

## Was wurde erledigt
- ...

## Geänderte Dateien
- ...

## Nächste Schritte
- ...

## Offene Fragen an den Auftraggeber
- ...
EOF

# LATEST.md überschreiben
cp PROJECT_DOCS/sessions/SESSION_v0.0.20.XXX_KURZTITEL.md PROJECT_DOCS/sessions/LATEST.md
```

**F) ROADMAP aktualisieren:**
Hake in `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` ab was du erledigt hast:
```markdown
- [x] Erledigt: Grundstruktur Cargo-Projekt  ← war vorher [ ]
- [ ] Noch offen: IPC-Protokoll definieren
```

### Schritt 5: ZIP bauen und prüfen

```bash
# ZIP bauen
zip -r Py_DAW_v0_0_20_XXX_TEAM_READY.zip \
  pydaw pydaw_engine PROJECT_DOCS docs *.py *.md *.txt VERSION *.sh \
  -x "*.pyc" "*__pycache__*" "*.egg-info*" "*/.git/*" "*/node_modules/*" "*/target/*"

# ZIP VERIFIZIEREN (PFLICHT!)
cd /tmp && mkdir verify && cd verify
unzip -q /path/Py_DAW_v0_0_20_XXX_TEAM_READY.zip
python3 -c "
import py_compile, os
for root, dirs, files in os.walk('pydaw'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            py_compile.compile(path, doraise=True)
print('✅ Alle .py Dateien OK')
"
cat VERSION  # Stimmt die Version?
rm -rf /tmp/verify
```

---

## 📤 WAS DU ZURÜCKGIBST

Du gibst dem Auftraggeber genau **2 Dinge** zurück:

### 1. Die neue ZIP-Datei
`Py_DAW_v0_0_20_XXX_TEAM_READY.zip`

Die ZIP enthält automatisch alles:
- Deinen neuen Code
- Alle aktualisierten Docs (CHANGELOG, TODO, DONE, Session-Log, ROADMAP)
- Die neue VERSION-Datei

### 2. Eine kurze Übergabe-Nachricht

```
📦 Py_DAW v0.0.20.XXX — [Kurztitel]

✅ Erledigt (diese Session):
- AP X Phase XA: komplett ✅
- AP X Phase XB: 3 von 5 Tasks erledigt (Details in ROADMAP)

⏭️ Hier geht's weiter:
- AP X Phase XB, Task 4: [Beschreibung]
- (Nächster Kollege liest ROADMAP → erste offene Checkbox)

⚠️ Offene Punkte (falls vorhanden):
- [Probleme die nicht gelöst werden konnten]
- [Entscheidungen die der Auftraggeber treffen muss]

📁 Geänderte Dateien: X Dateien
📋 Details: siehe CHANGELOG + ROADMAP Checkboxen in der ZIP
```

**Der nächste Kollege braucht NUR die ZIP!**
Alles steht drin: ROADMAP (mit abgehakten Checkboxen), LATEST.md,
TODO.md, DONE.md. Er findet selbständig die nächste offene Aufgabe.

---

## 🔄 DER KREISLAUF

```
Anno (Auftraggeber)
  │
  ├── gibt NUR die ZIP (alles steht drin!)
  │
  ▼
Kollege A
  │
  ├── liest ROADMAP → findet nächstes offenes AP + Phase
  ├── arbeitet selbständig Phase für Phase ab
  ├── dokumentiert alles, hakt Checkboxen ab
  ├── gibt ZIP + Übergabe-Nachricht zurück
  │
  ▼
Anno (testet kurz: läuft alles?)
  │
  ├── Alles OK? → gibt ZIP an nächsten Kollegen
  ├── Problem?  → gibt zurück mit Fehlerbeschreibung
  │
  ▼
Kollege B
  │
  ├── liest LATEST.md → weiß wo Kollege A aufgehört hat
  ├── liest ROADMAP → findet nächste offene Phase
  ├── arbeitet selbständig weiter
  ├── gibt ZIP + Übergabe-Nachricht zurück
  │
  ▼
Anno (testet)
  │
  ... usw. bis alle 10 Arbeitspakete durch sind
```

**Wichtig:** Anno muss NICHT sagen "mach Phase 1B" — das steht alles
in der ROADMAP. Der Kollege sieht die Checkboxen und weiß selbst
was als nächstes dran ist.

---

## 📏 QUALITÄTS-CHECKLISTE (vor Rückgabe)

Bevor du die ZIP zurückgibst, prüfe:

- [ ] VERSION erhöht?
- [ ] CHANGELOG geschrieben?
- [ ] TODO.md aktualisiert (erledigte Tasks abgehakt)?
- [ ] DONE.md aktualisiert?
- [ ] Session-Log + LATEST.md geschrieben?
- [ ] ROADMAP Checkboxen aktualisiert?
- [ ] Alle geänderten .py Dateien kompilieren fehlerfrei?
- [ ] ZIP gebaut mit korrektem Befehl (keine __pycache__, keine .pyc)?
- [ ] ZIP verifiziert (entpackt + Syntax-Check)?
- [ ] Übergabe-Nachricht geschrieben?
- [ ] NICHTS KAPUTT GEMACHT? (Bestehende Features getestet?)

---

## 🗂️ DATEISTRUKTUR IM PROJEKT

```
Py_DAW_v0_0_20_XXX_TEAM_READY/
├── VERSION                              ← Versionsnummer
├── main.py                              ← Einstiegspunkt
├── requirements.txt                     ← Python Dependencies
├── CHANGELOG_v0.0.20.XXX_*.md           ← Changelogs (eins pro Version)
├── TROUBLESHOOTING.md                   ← Bekannte Probleme
├── pydaw/                               ← Hauptcode
│   ├── ui/                              ← GUI (PyQt6)
│   │   ├── main_window.py              
│   │   ├── clip_launcher.py            
│   │   ├── pianoroll_editor.py         
│   │   ├── arranger_canvas.py          
│   │   ├── mixer.py                    
│   │   └── ...                         
│   ├── services/                        ← Business Logic
│   │   ├── project_service.py          
│   │   ├── transport_service.py        
│   │   ├── cliplauncher_playback.py    
│   │   └── ...                         
│   ├── audio/                           ← Audio Engine
│   │   ├── audio_engine.py             
│   │   ├── arrangement_renderer.py     
│   │   └── ...                         
│   └── models/                          ← Datenmodelle
├── PROJECT_DOCS/                        ← Dokumentation
│   ├── ROADMAP_MASTER_PLAN.md          ← 🎯 DER MASTERPLAN
│   ├── TEAM_RELAY_PROTOCOL.md          ← 🔄 DIESES DOKUMENT
│   ├── progress/
│   │   ├── TODO.md                     ← Offene Tasks
│   │   └── DONE.md                     ← Erledigte Tasks
│   ├── sessions/
│   │   ├── LATEST.md                   ← Letzte Session
│   │   └── SESSION_v0.0.20.XXX_*.md   ← Alle Session-Logs
│   └── features/                       ← Feature-Design-Docs
│       └── *.md
└── docs/                                ← Zusätzliche Docs
```

---

*Letztes Update: v0.0.20.627 — 2026-03-19*
