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
echo "  Generando enlace directo Cloudflare (HTTP2)            "
echo "=========================================================="

./cloudflared tunnel --protocol http2 --url http://localhost:$PORT > tunnel.log 2>&1 &

echo "Esperando que Cloudflare asigne la URL..."
for i in {1..30}; do
    if grep -q "trycloudflare.com" tunnel.log 2>/dev/null; then
        URL=$(grep -o 'https://[-a-zA-Z0-9@:%._\+~#=]*\.trycloudflare\.com' tunnel.log | head -n 1)
        echo ""
        echo "=========================================================="
        echo "  COPIA Y PEGA ESTE ENLACE EN GEMINI:                     "
        echo "  ${URL}/sse"
        echo "=========================================================="
        echo "${URL}/sse" > URL_DE_GEMINI.txt
        break
    fi
    sleep 1
done

tail -f tunnel.log
