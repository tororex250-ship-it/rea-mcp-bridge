# REA MCP Bridge para Gemini (GitHub Codespaces)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/tororex250-ship-it/rea-mcp-bridge)

Este repositorio te permite correr el servidor **MCP de REA (Reverse Engineer Anything)** en la nube de GitHub con **0% consumo de batería o almacenamiento en tu teléfono (POCO X6 Pro)** y conectarlo directamente a Gemini.

## Pasos para conectar a Gemini

1. Toca el botón **Open in GitHub Codespaces** o abre un Codespace en este repositorio.
2. Una vez cargue la terminal en tu navegador, ejecuta:
   ```bash
   bash start.sh
   ```
3. Ve a la pestaña **Ports** (Puertos) abajo en la interfaz web de VS Code:
   - Verás el puerto `8000`.
   - Haz clic derecho o mantén presionado en la columna **Port Visibility** y cámbialo de *Private* a **Public**.
   - Copia la dirección en **Local Address** (ejemplo: `https://tororex250-ship-it-....app.github.dev`).
4. Abre la ventana **Conéctate a un servidor de MCP** en Gemini y pega esa URL añadiendo `/sse`:
   ```text
   https://tu-url-de-codespaces.app.github.dev/sse
   ```
5. Deja vacíos los campos de *ID de cliente* y *Secreto del cliente*. Presiona **Siguiente** ¡y listo!
