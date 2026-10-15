#!/bin/bash
set -e

echo "=========================================================="
echo "  Iniciando REA MCP Server sobre SSE con Supergateway    "
echo "=========================================================="

if ! command -v rea &> /dev/null; then
    echo "Instalando rea-agents globalmente..."
    npm install -g rea-agents@latest supergateway untun
fi

PORT=8000
echo "Levantando el puente MCP en el puerto $PORT..."
npx -y supergateway --stdio "rea mcp" --port $PORT --cors &

sleep 3
echo ""
echo "=========================================================="
echo "  Generando enlace directo Cloudflare (sin bloqueo)      "
echo "=========================================================="
npx -y untun tunnel --port $PORT
