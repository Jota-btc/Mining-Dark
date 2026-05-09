# Bitcoin Balance Scanner Pro

> **Projeto educacional e de pesquisa sobre criptografia Bitcoin.**  
> **by: J.**

---

## Funcionalidades

- Geração de chaves via curva elíptica **secp256k1**
- **6 formatos de endereço** derivados da mesma chave privada:
  - `P2PKH` — Legacy comprimida `1…`
  - `P2PKH uncompressed` — Legacy não comprimida `1…` *(era Satoshi / blocos antigos)*
  - `P2SH-P2WPKH` — Nested SegWit `3…`
  - `P2WPKH` — Native SegWit `bc1q…`
  - `P2WSH` — Witness Script Hash `bc1q…`
  - `P2TR` — Taproot `bc1p…`
- **Banco UTXO local** (SQLite) — verificação instantânea (~0.1ms por endereço, sem internet)
- Modo **Random** (chaves aleatórias) e **HD Wallet** (BIP32/44/49/84/86)
- Dashboard em tempo real com estatísticas ao vivo
- Salvamento automático em `.txt`, `.json` e `summary.csv`
- Chaves privadas **nunca** aparecem nos logs

---

## Instalação

```bash
cd ~/Projetos/Mining-Dark
bash install.sh
```

O script instala as dependências do sistema, cria o ambiente virtual `.venv` e instala os pacotes Python.

<details>
<summary>Instalação manual</summary>

**Ubuntu / Debian**
```bash
sudo apt-get install -y python3-pip python3-venv python3-dev \
    build-essential libssl-dev libffi-dev libsecp256k1-dev
```

**macOS**
```bash
brew install secp256k1
```

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
</details>

---

## Banco UTXO Local

O banco contém **todos os endereços Bitcoin com saldo** em um arquivo SQLite (~3–5 GB).  
O scanner **não funciona sem o banco** — siga os passos abaixo antes de iniciar.

### 1. Instalar Bitcoin Core (uma vez só)

Rode o script de setup:

```bash
bash tools/setup_bitcoin_core.sh
```

Instala o **Bitcoin Core** em modo pruned e o **bitcoin-utxo-dump**.  
Requisitos: ~10–15 GB de espaço em disco.

Verifique se tudo foi instalado corretamente:

```bash
which bitcoind && which bitcoin-cli && which bitcoin-utxo-dump
```

Os três comandos devem retornar um caminho. Se `bitcoin-utxo-dump` não aparecer, instale o Go e compile manualmente:

```bash
# Baixar e instalar o Go
curl -L "https://go.dev/dl/$(curl -s 'https://go.dev/dl/?mode=json' | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["version"])')linux-amd64.tar.gz" -o /tmp/go.tar.gz
sudo tar -C /usr/local -xzf /tmp/go.tar.gz
export PATH=$PATH:/usr/local/go/bin
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc

# Compilar e instalar o bitcoin-utxo-dump
go install github.com/in3rsha/bitcoin-utxo-dump@latest
sudo cp ~/go/bin/bitcoin-utxo-dump /usr/local/bin/
```

### 2. Sincronizar o nó

> **Não precisa de `.venv`** — `bitcoind` é um programa do sistema, não Python.  
> Pode ser rodado de qualquer pasta, mas por padrão use a pasta do projeto.

```bash
cd ~/Projetos/Mining-Dark
bitcoind -daemon
```

> **Reiniciando após desligar o PC:** rode `bitcoind -daemon` novamente — ele continua de onde parou, não zera do zero.

```bash
# Acompanhe o progresso (leva 2–5 dias na primeira vez)
watch -n 10 "bitcoin-cli getblockchaininfo | grep -E 'blocks|headers|verificationprogress|initialblockdownload'"
```

### 3. Gerar o banco UTXO

Quando `verificationprogress` chegar em `0.9999` ou mais:

```bash
source .venv/bin/activate
python3 tools/update_utxo.py --from-node
```

### Atualizar no futuro

```bash
python3 tools/update_utxo.py --from-node --force
```

### Solução de problemas

**Erro: `Cannot obtain a lock on data directory` (Bitcoin Core já está rodando):**

```
Error: Cannot obtain a lock on data directory /home/mining-dark/.bitcoin. Bitcoin Core is probably already running.
```

O `bitcoind` está rodando em background. Se `bitcoin-cli stop` retornar erro de autenticação, pare o processo diretamente:

```bash
# Parar com segurança (aguarda o shutdown limpo antes de sair)
kill -SIGTERM $(cat ~/.bitcoin/bitcoind.pid)

# Aguardar 30-60 segundos, depois reiniciar
bitcoind -daemon
```

---

**Erro ao iniciar `bitcoind` após desligamento abrupto do PC:**

```
ERROR: ReplayBlock(): ReadBlockFromDisk failed
Please restart with -reindex or -reindex-chainstate to recover.
```

O banco de dados de blocos corrompeu. Como o nó está em modo pruned, use:

```bash
bitcoind -reindex
```

> `-reindex-chainstate` **não funciona** em modo pruned — use sempre `-reindex`.  
> Leva algumas horas. Após terminar, o nó volta a funcionar normalmente.

---

## Uso

```bash
cd ~/Projetos/Mining-Dark
source .venv/bin/activate
```

| Comando | Descrição |
|---------|-----------|
| `python3 main.py scan` | Inicia o scanner (menu interativo) |
| `python3 main.py scan --workers 20` | Scanner com 20 workers |
| `python3 main.py scan --mode hd` | Modo HD Wallet |
| `python3 main.py check <endereço>` | Verifica um endereço |
| `python3 main.py found` | Lista carteiras encontradas |
| `python3 main.py keygen` | Gera wallets de exemplo |

---

## Estrutura do Projeto

```
Mining-Dark/
├── core/               # Geração de chaves e endereços
├── generators/         # Modo random e HD Wallet
├── checkers/           # Verificação via banco UTXO local
├── ui/                 # Dashboard e menu de configuração
├── utils/              # Logger, file manager, banco UTXO
├── tools/
│   ├── update_utxo.py         # Importa o UTXO set do Bitcoin Core
│   └── setup_bitcoin_core.sh  # Instala Bitcoin Core + bitcoin-utxo-dump
├── config/             # Pydantic Settings (YAML)
├── found_wallets/      # Wallets com saldo encontradas
├── utxo_data/          # Banco SQLite (~3–5 GB)
├── logs/               # Logs rotativos
├── main.py             # Entry point
├── config.yaml         # Configuração principal
└── install.sh          # Instalador automático
```

---

## Configuração

Edite `config.yaml` para ajustar:

| Chave | Descrição |
|-------|-----------|
| `scanner.workers` | Workers assíncronos paralelos |
| `scanner.mode` | `random` ou `hd` |
| `scanner.address_types` | Tipos de endereço a verificar |
| `hd_wallet.derivation_paths` | Paths BIP32 para modo HD |

---

## Segurança

- Chaves privadas **nunca** aparecem nos logs (filtro automático)
- Todos os dados ficam **localmente** em `found_wallets/`
- Nenhuma informação é enviada para terceiros

---

## Licença

MIT License — uso livre para fins educacionais e de pesquisa.
