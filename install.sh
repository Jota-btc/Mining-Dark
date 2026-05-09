#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Bitcoin Balance Scanner Pro — Instalador automático
#  Execute uma vez: bash install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

VENV_DIR=".venv"
PYTHON="python3"

echo "==> [1/4] Instalando dependências do sistema (requer sudo)..."
sudo apt-get update -q
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    pkg-config

# libsecp256k1 — opcional mas acelera muito o coincurve
if apt-cache show libsecp256k1-dev &>/dev/null; then
    sudo apt-get install -y libsecp256k1-dev && echo "  ✓ libsecp256k1-dev instalado (modo rápido)"
else
    echo "  ℹ  libsecp256k1-dev não encontrado — coincurve vai compilar a própria lib (mais lento na 1ª vez)"
fi

echo ""
echo "==> [2/4] Criando ambiente virtual em $VENV_DIR ..."
$PYTHON -m venv "$VENV_DIR"

echo ""
echo "==> [3/4] Instalando pacotes Python ..."
"$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
"$VENV_DIR/bin/pip" install -r requirements.txt

echo ""
echo "==> [4/4] Verificando instalação ..."
"$VENV_DIR/bin/python" -c "
import coincurve, aiofiles, rich, typer, loguru, yaml, pydantic, mnemonic, base58
print('  ✓ Todas as dependências importadas com sucesso!')
"

echo ""
echo "════════════════════════════════════════════════"
echo "  Instalação concluída!"
echo ""
echo "  Para ativar o ambiente e rodar:"
echo "    source $VENV_DIR/bin/activate"
echo "    python main.py scan"
echo ""
echo "  Ou sem ativar:"
echo "    $VENV_DIR/bin/python main.py scan"
echo "════════════════════════════════════════════════"
