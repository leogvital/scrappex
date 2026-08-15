#!/bin/bash
set -e
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${CYAN}  X Video Scraper — Setup${NC}"; echo ""

if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ Python3 não encontrado.${NC}"; exit 1
fi
echo -e "${GREEN}✓ $(python3 --version)${NC}"

if [ ! -d "venv" ]; then
  echo -e "${CYAN}→ Criando ambiente virtual...${NC}"
  python3 -m venv venv || { echo -e "${RED}Instale: sudo apt install python3-venv${NC}"; exit 1; }
fi
source venv/bin/activate
echo -e "${GREEN}✓ Ambiente virtual ativo${NC}"

echo -e "${CYAN}→ Instalando dependências...${NC}"
pip install --upgrade pip --quiet
pip install flask flask-cors yt-dlp gunicorn requests selenium webdriver-manager "curl_cffi>=0.10,<0.15" psutil --quiet

# secretstorage só existe/faz sentido no Linux (bindings D-Bus para o keyring do
# GNOME/KDE, usado pelo yt-dlp para decifrar cookies do Chrome). No Mac o yt-dlp
# usa o Keychain nativo sem essa lib; no Windows usa DPAPI (ver setup_windows.bat).
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  pip install secretstorage --quiet
  echo -e "${GREEN}✓ flask, flask-cors, yt-dlp, gunicorn, secretstorage, requests, selenium, curl_cffi, psutil instalados${NC}"
else
  echo -e "${GREEN}✓ flask, flask-cors, yt-dlp, gunicorn, requests, selenium, curl_cffi, psutil instalados${NC}"
fi

echo ""; echo -e "${GREEN}✓ Setup concluído! Inicie com: ${CYAN}bash start.sh${NC}"
