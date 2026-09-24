#!/usr/bin/env bash
# Remove o serviço automático da Silmodas. Seus dados (fiado.db e backups/) NÃO são apagados.
set -euo pipefail

LABEL="br.silmodas.fiado"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Serviço removido. Seus dados continuam em: $(cd "$(dirname "$0")/.." && pwd)"
