#!/bin/bash
set -e

echo "=========================================================="
echo "  Iniciando REA MCP Server sobre SSE con Supergateway    "
echo "=========================================================="

if ! command -v rea &> /dev/null; then
    echo "Instalando rea-agents globalmente..."
    npm install -g rea-agents@latest supergateway
fi

PORT=8000
echo "Levantando el puente MCP en el puerto $PORT..."
npx -y supergateway --stdio "rea mcp" --port $PORT --cors &

sleep 3

if [ ! -f ./cloudflared ]; then
    echo "Descargando Cloudflare Tunnel..."
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
    chmod +x cloudflared
fi

echo "=========================================================="
echo "  Generando enlace directo Cloudflare (sin bloqueo)      "
echo "=========================================================="
./cloudflared tunnel --url http://localhost:$PORT
