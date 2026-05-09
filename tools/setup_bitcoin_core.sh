#!/bin/bash
# =============================================================================
#  Bitcoin Core + bitcoin-utxo-dump — Setup automático (Ubuntu/Debian x86_64)
# =============================================================================
#
#  O que este script faz:
#    1. Baixa e instala Bitcoin Core em modo pruned (~10-15 GB disco)
#    2. Cria bitcoin.conf otimizado (pruned, sem txindex)
#    3. Baixa e instala bitcoin-utxo-dump (exporta UTXO set para CSV)
#
#  Após instalar, sincronize o nó e então execute:
#    python3 tools/update_utxo.py --from-node
# =============================================================================

set -e

# ── Versões ──────────────────────────────────────────────────────────────────
BITCOIN_VERSION="27.1"
UTXO_DUMP_VERSION="1.1.0"
ARCH="x86_64-linux-gnu"

# ── Cores ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

BITCOIN_DIR="$HOME/.bitcoin"
TMP="/tmp/bitcoin_setup_$$"
mkdir -p "$TMP"

# ── Funções helpers ──────────────────────────────────────────────────────────
step() { echo -e "\n${GREEN}[$1/$2]${NC} $3"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
warn() { echo -e "  ${YELLOW}AVISO:${NC} $1"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   Bitcoin Core + bitcoin-utxo-dump — Setup       ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Verifica se já está instalado ────────────────────────────────────────────
if command -v bitcoind &>/dev/null; then
    INSTALLED_VER=$(bitcoind --version | head -1 | grep -oP '\d+\.\d+(\.\d+)?')
    warn "Bitcoin Core $INSTALLED_VER já está instalado."
    read -p "  Reinstalar? [s/N] " -n 1 -r; echo
    [[ ! $REPLY =~ ^[Ss]$ ]] && echo "  Pulando instalação do Bitcoin Core." && SKIP_BITCOIN=1
fi

# ── [1/3] Bitcoin Core ───────────────────────────────────────────────────────
if [ -z "$SKIP_BITCOIN" ]; then
    step 1 3 "Baixando Bitcoin Core $BITCOIN_VERSION..."

    TARBALL="bitcoin-${BITCOIN_VERSION}-${ARCH}.tar.gz"
    URL="https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/${TARBALL}"
    SUMS_URL="https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/SHA256SUMS"

    info "URL: $URL"
    wget -q --show-progress -O "$TMP/$TARBALL" "$URL"
    wget -q -O "$TMP/SHA256SUMS" "$SUMS_URL"

    info "Verificando SHA256..."
    cd "$TMP"
    sha256sum --check --ignore-missing SHA256SUMS
    ok "Checksum OK"

    info "Instalando binários em /usr/local/bin/..."
    tar -xzf "$TARBALL"
    sudo install -m 0755 -o root -g root -t /usr/local/bin \
        "bitcoin-${BITCOIN_VERSION}/bin/bitcoind" \
        "bitcoin-${BITCOIN_VERSION}/bin/bitcoin-cli"
    ok "bitcoind e bitcoin-cli instalados"
    cd -
fi

# ── [2/3] bitcoin.conf ───────────────────────────────────────────────────────
step 2 3 "Configurando Bitcoin Core (modo pruned)..."

mkdir -p "$BITCOIN_DIR"

if [ -f "$BITCOIN_DIR/bitcoin.conf" ]; then
    warn "bitcoin.conf já existe — fazendo backup em bitcoin.conf.bak"
    cp "$BITCOIN_DIR/bitcoin.conf" "$BITCOIN_DIR/bitcoin.conf.bak"
fi

RPC_PASS=$(openssl rand -hex 20)

cat > "$BITCOIN_DIR/bitcoin.conf" << EOF
# =============================================================================
#  Bitcoin Core — Modo Pruned para UTXO Scanner
#  Gerado por tools/setup_bitcoin_core.sh
# =============================================================================

# Pruned: mantém apenas os últimos 2 GB de blocos + UTXO set completo
# O UTXO set (chainstate) é preservado integralmente independente do prune
prune=2048

# Não precisa de índice de transações (economiza ~60 GB)
txindex=0

# RPC — necessário para bitcoin-cli e monitoramento
server=1
daemon=1
rpcuser=bitcoinrpc
rpcpassword=${RPC_PASS}
rpcallowip=127.0.0.1

# Performance
dbcache=512
maxmempool=100
EOF

ok "bitcoin.conf criado em $BITCOIN_DIR/bitcoin.conf"

# Salva as credenciais RPC para o update_utxo.py usar
cat > "$BITCOIN_DIR/rpc_credentials" << EOF
rpcuser=bitcoinrpc
rpcpassword=${RPC_PASS}
EOF
chmod 600 "$BITCOIN_DIR/rpc_credentials"
ok "Credenciais RPC salvas em $BITCOIN_DIR/rpc_credentials"

# ── [3/3] bitcoin-utxo-dump ──────────────────────────────────────────────────
step 3 3 "Instalando bitcoin-utxo-dump..."

UTXO_DUMP_URL="https://github.com/in3rsha/bitcoin-utxo-dump/releases/download/v${UTXO_DUMP_VERSION}/bitcoin-utxo-dump-linux-amd64"

if wget -q --spider "$UTXO_DUMP_URL" 2>/dev/null; then
    wget -q --show-progress -O "$TMP/bitcoin-utxo-dump" "$UTXO_DUMP_URL"
    sudo install -m 0755 "$TMP/bitcoin-utxo-dump" /usr/local/bin/bitcoin-utxo-dump
    ok "bitcoin-utxo-dump instalado em /usr/local/bin/"
else
    # Tenta instalar via Go se disponível
    if command -v go &>/dev/null; then
        info "Instalando via Go..."
        go install github.com/in3rsha/bitcoin-utxo-dump@latest
        sudo cp "$(go env GOPATH)/bin/bitcoin-utxo-dump" /usr/local/bin/
        ok "bitcoin-utxo-dump instalado via Go"
    else
        warn "Não foi possível baixar bitcoin-utxo-dump automaticamente."
        warn "Instale manualmente:"
        echo ""
        echo "  Opção 1 — instalar Go e compilar:"
        echo "    sudo apt install golang-go"
        echo "    go install github.com/in3rsha/bitcoin-utxo-dump@latest"
        echo "    sudo cp ~/go/bin/bitcoin-utxo-dump /usr/local/bin/"
        echo ""
        echo "  Opção 2 — baixar binário:"
        echo "    https://github.com/in3rsha/bitcoin-utxo-dump/releases"
        echo "    sudo install -m 0755 bitcoin-utxo-dump /usr/local/bin/"
    fi
fi

# ── Limpeza ───────────────────────────────────────────────────────────────────
rm -rf "$TMP"

# ── Resumo final ──────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗"
echo    "║            Setup concluído!                       ║"
echo -e "╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "Próximos passos:"
echo ""
echo -e "  ${CYAN}1. Inicie o Bitcoin Core:${NC}"
echo    "       bitcoind"
echo ""
echo -e "  ${CYAN}2. Monitore a sincronização (leva 2–5 dias):${NC}"
echo    "       bitcoin-cli getblockchaininfo | grep -E 'blocks|headers|verificationprogress'"
echo    "       watch -n 30 'bitcoin-cli getblockchaininfo | grep verificationprogress'"
echo ""
echo -e "  ${CYAN}3. Quando verificationprogress ≥ 0.9999, gere o banco UTXO:${NC}"
echo    "       python3 tools/update_utxo.py --from-node"
echo ""
echo -e "  ${YELLOW}Espaço necessário: ~10–15 GB (UTXO set ~5 GB + blocos recentes ~2 GB + margem)${NC}"
echo ""
