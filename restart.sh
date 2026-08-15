#!/bin/bash
cd "$(dirname "$0")"

PORT=5000
LOG=/tmp/scrapperx.log

if [ ! -d "venv" ]; then
  echo "✗ Rode primeiro: bash setup.sh"
  exit 1
fi

source venv/bin/activate

# Carrega credenciais/config local (veja .env.local.example) — não versionado
if [ -f .env.local ]; then
  set -a
  source .env.local
  set +a
fi

PIDS=$(lsof -ti:$PORT)
if [ -n "$PIDS" ]; then
  echo "  Parando servidor atual (PID $PIDS)..."
  kill $PIDS 2>/dev/null
  sleep 1
  PIDS=$(lsof -ti:$PORT)
  [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null
fi

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    X Video Scraper — Reiniciando     ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

nohup gunicorn app:app \
  --bind 0.0.0.0:$PORT \
  --workers 1 \
  --worker-class gthread \
  --threads 4 \
  --timeout 600 \
  --log-level warning \
  --access-logfile - \
  --no-control-socket \
  > "$LOG" 2>&1 &

disown
sleep 2

if curl -s "http://localhost:$PORT/api/session" > /dev/null; then
  echo "  ✓ Servidor rodando em http://localhost:$PORT"
  echo "  Logs: tail -f $LOG"
else
  echo "  ✗ Falha ao iniciar — confira: tail -f $LOG"
  exit 1
fi
