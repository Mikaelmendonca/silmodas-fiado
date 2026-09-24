#!/usr/bin/env bash
# Instala a Silmodas neste Mac: liga sozinha quando o computador iniciar, protegida por senha,
# com o painel acessível no celular pelo Wi-Fi. Pode rodar de novo à vontade (é idempotente).
#
#   ./scripts/instalar-mac.sh
#   DRY_RUN=1 ./scripts/instalar-mac.sh    # só mostra o que faria, sem instalar nada
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="br.silmodas.fiado"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/silmodas.log"
ENV_FILE="$ROOT/.env"
PY="$ROOT/.venv/bin/python"

say() { printf '%s\n' "$*"; }
fail() { say "ERRO: $*" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "este instalador é para Mac."
command -v python3 >/dev/null || fail "instale o Python 3.11 ou mais novo (python.org/downloads)."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "o Python é muito antigo: precisa do 3.11 ou mais novo (python.org/downloads)."

if [ "$DRY_RUN" = "1" ]; then
  PLIST="${TMPDIR:-/tmp}/$LABEL.plist"
  say "[simulação] nada será instalado; o arquivo de serviço será gerado em $PLIST"
else
  say "1/5 Preparando o programa (pode levar 1 minuto)…"
  [ -x "$PY" ] || python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -e "$ROOT"

  say "2/5 Configurando senha e canal de avisos…"
  [ -f "$ENV_FILE" ] || cp "$ROOT/.env.example" "$ENV_FILE"
  # Só preenche o que estiver vazio: rodar de novo nunca troca sua senha nem seu canal.
  fill_env() {
    "$PY" - "$ENV_FILE" "$1" "$2" <<'PY'
import pathlib
import sys

path, key, value = sys.argv[1:4]
p = pathlib.Path(path)
lines = p.read_text().splitlines() if p.exists() else []
for i, line in enumerate(lines):
    if line.startswith(key + "="):
        if not line.split("=", 1)[1].strip():
            lines[i] = f"{key}={value}"
        break
else:
    lines.append(f"{key}={value}")
p.write_text("\n".join(lines) + "\n")
PY
  }
  fill_env FIADO_NTFY_TOPIC "silmodas-$("$PY" -c 'import secrets; print(secrets.token_hex(6))')-alertas"
  fill_env FIADO_PASSWORD "$("$PY" -c 'import secrets; print(secrets.token_hex(4))')"
  chmod 600 "$ENV_FILE"
fi

say "3/5 Criando o serviço que liga sozinho…"
mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>-m</string>
    <string>fiado</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_EOF
plutil -lint "$PLIST" >/dev/null || fail "o arquivo de serviço ficou inválido."

if [ "$DRY_RUN" = "1" ]; then
  say "[simulação] arquivo de serviço válido. Fim."
  exit 0
fi

say "4/5 Ligando…"
DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl kickstart -k "$DOMAIN/$LABEL"

for _ in $(seq 1 30); do
  curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1 \
  || fail "o programa não subiu. Veja o que houve em: $LOG"

say "5/5 Pronto!"
TOPIC="$(grep '^FIADO_NTFY_TOPIC=' "$ENV_FILE" | cut -d= -f2-)"
PASS="$(grep '^FIADO_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
cat <<RESUMO

  Painel neste Mac ........ http://localhost:$PORT
  Painel no celular ....... http://${IP:-<endereço-do-mac>}:$PORT   (mesmo Wi-Fi)
  Senha do painel ......... $PASS   (usuário: qualquer um)
  Canal dos avisos (ntfy) . $TOPIC

  Falta só o celular (2 minutos):
   1. Instale o app "ntfy" e assine o canal acima (botão +).
   2. Abra o endereço do painel no navegador do celular, digite a senha
      e use "Compartilhar → Adicionar à Tela de Início".
   3. No painel, toque em "Testar no celular".

  Se o Mac perguntar se o Python pode "aceitar conexões de rede", clique em Permitir.
  Para desinstalar: ./scripts/desinstalar-mac.sh
RESUMO
