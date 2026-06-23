# Atlas na Rasp (Desenvolvimento)

## Acesso

**Atlas está rodando em:**
```
http://guaxinimserver.tail25c9d8.ts.net:8080
```

Ou se você estiver na máquina local da Rasp:
```
http://localhost:8080
```

## Configuração de Produção

1. **Crie `.env` na Rasp** (copie `.env.example`):
   ```bash
   ssh guaxinim@guaxinimserver.tail25c9d8.ts.net
   cd ~/atlas
   cp .env.example .env
   nano .env  # edite com seu TELEGRAM_TOKEN e ATLAS_ALLOWED_USER_ID reais
   ```

2. **Inicie Atlas:**
   ```bash
   source .venv/bin/activate
   python -m atlas
   ```

## Status

- **Hostname Tailscale:** `guaxinimserver.tail25c9d8.ts.net` (IP: 100.74.97.24)
- **Rede Local:** `192.168.86.28` (eth0)
- **Tailscale IP:** `100.74.97.24` (tailscale0)
- **Recurso:** 1GB RAM (suficiente para app + Ollama local)

## Workflow de Desenvolvimento

**Aqui (local):**
1. Edita código em `feat/sua-feature`
2. Commita e faz `git push origin feat/sua-feature`
3. Abre PR no GitHub

**Você valida:**
1. Aprova a PR no GitHub
2. Faz merge em `main`

**Na Rasp:**
1. `git pull origin main` 
2. Reinicia Atlas (kill + start)
3. Valida em `http://guaxinimserver.tail25c9d8.ts.net:8080`

## Troubleshooting

Se Atlas não responder:
```bash
ssh guaxinim@guaxinimserver.tail25c9d8.ts.net
ps aux | grep 'python -m atlas'
tail -50 /tmp/atlas.log
```

Se precisar matar e reiniciar:
```bash
pkill -f 'python -m atlas'
cd ~/atlas && source .venv/bin/activate
python -m atlas  # sem nohup para ver output em tempo real
```
