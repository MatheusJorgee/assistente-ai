#!/bin/bash
# start-frontend.sh - Iniciar frontend Next.js

cd "$(dirname "$0")/frontend"

echo "╔════════════════════════════════════╗"
echo "║   Quinta-Feira Frontend (Next.js)   ║"
echo "╚════════════════════════════════════╝"
echo ""

if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependências..."
    npm install -q
    echo ""
fi

echo "🚀 Iniciando servidor em http://localhost:3000"
echo "Press CTRL+C para parar"
echo ""

npm run dev
