#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  Py_DAW → GitHub Release Builder (Deutsch)
#  
#  Ein Befehl — baut automatisch .exe + .dmg + .bin
#
#  Usage:
#    ./github_release.sh              # Erstes Mal: Repo erstellen
#    ./github_release.sh --release    # Release bauen
#    ./github_release.sh --status     # Build-Status
#    ./github_release.sh --download   # Fertige Dateien holen
# ═══════════════════════════════════════════════════════════

set -e

# ── Farben ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${CYAN}ℹ️  $1${NC}"; }

header() {
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ── Konfiguration ──
REPO_NAME="Py-DAW"
VERSION=$(cat VERSION 2>/dev/null || echo "0.0.20.729")

# ═══════════════════════════════════════════════════════════
#  GitHub CLI installieren
# ═══════════════════════════════════════════════════════════

install_gh_cli() {
    info "GitHub CLI (gh) wird installiert..."
    
    if command -v apt-get &>/dev/null; then
        # Debian/Ubuntu/Kali
        (type -p wget >/dev/null || sudo apt-get install wget -y) \
        && sudo mkdir -p -m 755 /etc/apt/keyrings \
        && out=$(mktemp) \
        && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
        && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
        && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
        && sudo apt-get update \
        && sudo apt-get install gh -y
    elif command -v brew &>/dev/null; then
        brew install gh
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm github-cli
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y gh
    else
        err "Bitte installiere GitHub CLI manuell: https://cli.github.com/"
        exit 1
    fi
    
    if command -v gh &>/dev/null; then
        ok "GitHub CLI installiert"
    else
        err "Installation fehlgeschlagen"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════
#  Abhängigkeiten prüfen
# ═══════════════════════════════════════════════════════════

check_deps() {
    header "Abhängigkeiten prüfen"
    
    # Git
    if command -v git &>/dev/null; then
        ok "Git: $(git --version | cut -d' ' -f3)"
    else
        err "Git fehlt!"
        echo "    sudo apt install git"
        exit 1
    fi
    
    # GitHub CLI
    if command -v gh &>/dev/null; then
        ok "GitHub CLI: $(gh --version | head -1 | awk '{print $3}')"
    else
        install_gh_cli
    fi
}

# ═══════════════════════════════════════════════════════════
#  GitHub Anmeldung (DEUTSCH erklärt)
# ═══════════════════════════════════════════════════════════

ensure_gh_auth() {
    header "GitHub Anmeldung"
    
    # Schon eingeloggt?
    if gh auth status &>/dev/null 2>&1; then
        ok "Du bist bereits bei GitHub angemeldet"
        gh auth status 2>&1 | grep -i "logged in" | head -1 | sed 's/^/    /'
        return 0
    fi
    
    # Anmeldung nötig
    echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║  Du musst dich EINMALIG bei GitHub anmelden.        ║${NC}"
    echo -e "${BOLD}║  Danach nie wieder — der Login bleibt gespeichert.  ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}So funktioniert es:${NC}"
    echo ""
    echo -e "  1. Gleich kommen ein paar englische Fragen."
    echo -e "     Drücke einfach ${BOLD}3x Enter${NC} (die Vorschläge sind richtig)."
    echo ""
    echo -e "  2. Dann erscheint ein ${BOLD}8-stelliger Code${NC} wie z.B.  AB12-CD34"
    echo ""
    echo -e "  3. Dein Browser öffnet sich → ${BOLD}Code eingeben${NC} → fertig."
    echo ""
    echo -e "  ${YELLOW}Falls du noch keinen GitHub-Account hast:${NC}"
    echo -e "  Im Browser auf \"Create account\" klicken."
    echo -e "  Braucht nur E-Mail + Passwort (kostenlos)."
    echo ""
    echo -e "  ${BOLD}Die 3 englischen Fragen und was du drückst:${NC}"
    echo ""
    echo -e "  ${CYAN}? What account do you want to log into?${NC}"
    echo -e "    → ${BOLD}Enter${NC}  (GitHub.com ist richtig)"
    echo ""
    echo -e "  ${CYAN}? What is your preferred protocol?${NC}"
    echo -e "    → ${BOLD}Enter${NC}  (HTTPS ist richtig)"
    echo ""
    echo -e "  ${CYAN}? How would you like to authenticate?${NC}"
    echo -e "    → ${BOLD}Enter${NC}  (Login with a web browser ist richtig)"
    echo ""
    echo -e "  ${CYAN}! First copy your one-time code: XXXX-XXXX${NC}"
    echo -e "    → ${BOLD}Code merken${NC}, dann Enter drücken"
    echo -e "    → Browser öffnet sich → Code eingeben → Authorize"
    echo ""
    
    echo -e -n "  ${BOLD}Bereit? Drücke Enter zum Starten...${NC}"
    read -r
    echo ""
    
    # Starte den Login
    gh auth login --web --git-protocol https
    
    # Prüfen ob es geklappt hat
    echo ""
    if gh auth status &>/dev/null 2>&1; then
        echo ""
        ok "Anmeldung erfolgreich! Du bist jetzt verbunden."
        echo ""
        echo -e "  ${GREEN}Ab jetzt musst du dich NIE WIEDER anmelden.${NC}"
        echo -e "  ${GREEN}Der Login bleibt gespeichert.${NC}"
    else
        echo ""
        err "Anmeldung fehlgeschlagen."
        echo ""
        echo "  Versuch es nochmal mit:"
        echo "    gh auth login"
        echo ""
        echo "  Oder manuell:"
        echo "    1. Geh auf https://github.com/settings/tokens"
        echo "    2. Erstelle einen Token (alle Rechte ankreuzen)"
        echo "    3. Führe aus: gh auth login --with-token < token.txt"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════
#  Git Repository erstellen
# ═══════════════════════════════════════════════════════════

init_repo() {
    header "Git Repository vorbereiten"
    
    if [ -d ".git" ]; then
        ok "Git-Repo existiert bereits"
        return 0
    fi
    
    # .gitignore
    cat > .gitignore << 'GITIGNORE'
__pycache__/
*.py[cod]
*.egg-info/
dist/
build_nuitka/
myenv/
venv/
.venv/
pydaw_engine/target/
.idea/
.vscode/
*.swp
*~
.DS_Store
Thumbs.db
*.bak
*.zip
*.tar.gz
*.dmg
*.exe
*.AppImage
GITIGNORE
    
    git init
    git add -A
    git commit -m "Erster Commit: Py_DAW v${VERSION}"
    
    ok "Lokales Git-Repository erstellt"
}

# ═══════════════════════════════════════════════════════════
#  GitHub Repository erstellen + Code hochladen
# ═══════════════════════════════════════════════════════════

create_github_repo() {
    header "GitHub Repository erstellen"
    
    # Schon verbunden?
    if git remote get-url origin &>/dev/null 2>&1; then
        ok "Bereits mit GitHub verbunden: $(git remote get-url origin)"
        return 0
    fi
    
    echo -e "  ${BOLD}Wie soll dein Projekt auf GitHub heißen?${NC}"
    echo -e "  Vorschlag: ${CYAN}${REPO_NAME}${NC}"
    echo -n "  Name [Enter = Vorschlag]: "
    read -r user_name
    [ -n "$user_name" ] && REPO_NAME="$user_name"
    
    echo ""
    echo -e "  ${BOLD}Soll jeder den Code sehen können?${NC}"
    echo "  1) Ja  — Open Source (empfohlen)"
    echo "  2) Nein — nur ich und eingeladene Personen"
    echo -n "  Wahl [1]: "
    read -r visibility
    
    local vis_flag="--public"
    [ "$visibility" = "2" ] && vis_flag="--private"
    
    info "Erstelle '${REPO_NAME}' auf GitHub und lade Code hoch..."
    echo ""
    
    gh repo create "${REPO_NAME}" \
        ${vis_flag} \
        --description "Py_DAW (ChronoScaleStudio) — Open Source DAW mit Rust Audio-Engine" \
        --source . \
        --remote origin \
        --push
    
    if [ $? -eq 0 ]; then
        echo ""
        ok "Geschafft! Dein Code ist auf GitHub."
        echo ""
        local REPO_URL=$(git remote get-url origin 2>/dev/null | sed 's/\.git$//')
        echo -e "  ${BOLD}🌐 Dein Repository:${NC}"
        echo -e "  ${CYAN}${REPO_URL}${NC}"
    else
        err "Hat nicht geklappt. Fehlermeldung oben beachten."
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════
#  Release erstellen → Baut .exe + .dmg + .bin
# ═══════════════════════════════════════════════════════════

create_release() {
    header "Release erstellen → Baut .exe + .dmg + .bin"
    
    VERSION=$(cat VERSION 2>/dev/null || echo "0.0.20.729")
    TAG="v${VERSION}"
    
    echo -e "  Version: ${BOLD}${VERSION}${NC}"
    echo -e "  Tag:     ${BOLD}${TAG}${NC}"
    echo ""
    
    # Tag existiert schon?
    if git tag -l "$TAG" | grep -q "$TAG"; then
        warn "Tag ${TAG} existiert schon."
        echo -n "  Neue Versionsnummer eingeben: "
        read -r new_ver
        if [ -n "$new_ver" ]; then
            echo -n "$new_ver" > VERSION
            cat > pydaw/version.py << PYEOF
__version__ = "${new_ver}"
VERSION = __version__
PYEOF
            VERSION="$new_ver"
            TAG="v${new_ver}"
            git add VERSION pydaw/version.py
            git commit -m "Version auf ${new_ver} erhöht"
        else
            err "Abgebrochen"
            exit 1
        fi
    fi
    
    # Änderungen hochladen
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        info "Änderungen werden gespeichert und hochgeladen..."
        git add -A
        git commit -m "Release ${TAG}"
    fi
    
    info "Code hochladen..."
    git push origin HEAD 2>/dev/null || git push
    
    # Tag erstellen + hochladen
    info "Release-Tag ${TAG} erstellen..."
    git tag -a "$TAG" -m "Release ${TAG} — Py_DAW v${VERSION}"
    git push origin "$TAG"
    
    ok "Tag ${TAG} erstellt!"
    
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  🚀 GitHub baut jetzt automatisch auf 4 Maschinen:${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  📦 Linux   x86_64  → ${CYAN}.tar.gz${NC}"
    echo -e "  📦 macOS   Intel   → ${CYAN}.tar.gz${NC}"
    echo -e "  📦 macOS   M1/M2   → ${CYAN}.tar.gz${NC}  (Apple Silicon)"
    echo -e "  📦 Windows x86_64  → ${CYAN}.zip${NC}    (.exe drin)"
    echo ""
    echo -e "  ⏱️  Dauert ca. ${BOLD}10–15 Minuten${NC}."
    echo ""
    echo -e "  ${BOLD}Status live verfolgen:${NC}"
    echo -e "  ${CYAN}./github_release.sh --status${NC}"
    echo ""
    
    REPO_URL=$(git remote get-url origin 2>/dev/null | sed 's/\.git$//')
    echo -e "  ${BOLD}Oder im Browser:${NC}"
    echo -e "  ${CYAN}${REPO_URL}/actions${NC}"
    echo ""
    echo -e "  ${BOLD}Wenn fertig — alle Downloads hier:${NC}"
    echo -e "  ${CYAN}${REPO_URL}/releases/tag/${TAG}${NC}"
    echo ""
    echo -e "  ${BOLD}Downloads in den Terminal holen:${NC}"
    echo -e "  ${CYAN}./github_release.sh --download${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════
#  Build-Status prüfen
# ═══════════════════════════════════════════════════════════

check_status() {
    header "Build-Status"
    
    echo -e "  ${BOLD}Letzte Builds:${NC}"
    echo ""
    gh run list --limit 5 2>/dev/null || {
        err "Konnte Status nicht abrufen. Bist du angemeldet?"
        echo "  Führe aus: ./github_release.sh"
        exit 1
    }
    
    echo ""
    echo -e "  ${BOLD}Befehle:${NC}"
    echo -e "  ${CYAN}./github_release.sh --status${NC}    Status nochmal prüfen"
    echo -e "  ${CYAN}./github_release.sh --download${NC}  Fertige Dateien holen"
    echo -e "  ${CYAN}gh run watch${NC}                    Build live verfolgen"
}

# ═══════════════════════════════════════════════════════════
#  Downloads holen
# ═══════════════════════════════════════════════════════════

download_releases() {
    header "Fertige Builds herunterladen"
    
    mkdir -p releases
    
    # Zuerst: letzten fertigen Run versuchen
    info "Suche fertige Builds..."
    echo ""
    
    if gh run download --dir releases/ 2>/dev/null; then
        ok "Downloads in ./releases/:"
        echo ""
        ls -lh releases/*/* 2>/dev/null || ls -lh releases/ 2>/dev/null
        echo ""
        echo -e "  ${GREEN}Das sind deine fertigen Pakete!${NC}"
        echo -e "  ${GREEN}Jedes enthält alles — einfach entpacken und starten.${NC}"
    else
        # Fallback: Release-Assets
        TAG="v$(cat VERSION 2>/dev/null || echo '0.0.20.729')"
        if gh release download "$TAG" --dir releases/ 2>/dev/null; then
            ok "Release-Downloads in ./releases/:"
            ls -lh releases/
        else
            warn "Noch keine fertigen Downloads."
            echo ""
            echo "  Mögliche Gründe:"
            echo "  • Die Builds laufen noch (dauert 10–15 Min)"
            echo "  • Es wurde noch kein Release erstellt"
            echo ""
            echo "  Status prüfen: ./github_release.sh --status"
            echo "  Release starten: ./github_release.sh --release"
        fi
    fi
}

# ═══════════════════════════════════════════════════════════
#  HAUPTPROGRAMM
# ═══════════════════════════════════════════════════════════

case "${1:-}" in
    --release|-r)
        check_deps
        ensure_gh_auth
        create_release
        ;;
    --status|-s)
        check_status
        ;;
    --download|-d)
        download_releases
        ;;
    --help|-h)
        echo ""
        echo "Py_DAW GitHub Release Builder"
        echo ""
        echo "Benutzung:"
        echo "  ./github_release.sh              Erstmalig: Repo erstellen + Code hochladen"
        echo "  ./github_release.sh --release    Neuen Release bauen (alle Plattformen)"
        echo "  ./github_release.sh --status     Wie weit ist der Build?"
        echo "  ./github_release.sh --download   Fertige .exe/.dmg/.bin holen"
        echo ""
        ;;
    *)
        # Erstmalige Einrichtung
        header "🎵 Py_DAW → GitHub Release Builder"
        echo -e "  Dieses Script macht ${BOLD}alles automatisch${NC}:"
        echo ""
        echo -e "  ${BOLD}Schritt 1:${NC} Bei GitHub anmelden (einmalig, kostenlos)"
        echo -e "  ${BOLD}Schritt 2:${NC} Code auf GitHub hochladen"
        echo -e "  ${BOLD}Schritt 3:${NC} GitHub baut .exe + .dmg + .bin für dich"
        echo ""
        echo -e "  Du brauchst ${BOLD}keinen Windows-PC${NC} und ${BOLD}keinen Mac${NC}."
        echo -e "  GitHub hat alle 3 Betriebssysteme als Build-Server."
        echo ""
        echo -n "  Jetzt starten? [j/N] "
        read -r confirm
        if [[ "$confirm" != [jJyY]* ]]; then
            echo "  Abgebrochen."
            exit 0
        fi
        
        echo ""
        check_deps
        ensure_gh_auth
        init_repo
        create_github_repo
        
        echo ""
        echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}${BOLD}  🎉 Geschafft! Dein Code ist auf GitHub.${NC}"
        echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "  ${BOLD}Nächster Schritt — Release bauen:${NC}"
        echo ""
        echo -e "  ${CYAN}./github_release.sh --release${NC}"
        echo ""
        echo -e "  Das startet automatische Builds für:"
        echo -e "  📦 Linux  → .tar.gz"
        echo -e "  📦 macOS  → .tar.gz (Intel + Apple Silicon)"
        echo -e "  📦 Windows → .zip (.exe drin)"
        echo ""
        echo -e "  Dauert 10–15 Minuten. Danach:"
        echo -e "  ${CYAN}./github_release.sh --download${NC}"
        echo ""
        ;;
esac
