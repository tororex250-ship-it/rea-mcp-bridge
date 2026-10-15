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
echo "El endpoint SSE sera: /sse"
echo "=========================================================="

npx -y supergateway --stdio "rea mcp" --port $PORT --cors
