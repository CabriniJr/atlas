# Iniciando Atlas

## Na Rasp (Pseudo-Prod)

Use o script de inicialização que carrega `.env` automaticamente:

```bash
cd ~/atlas
bash start-atlas.sh
```

Ou em background:
```bash
cd ~/atlas
nohup bash start-atlas.sh > /tmp/atlas.log 2>&1 &
```

## Local (Dev)

```bash
cd ~/atlas
source .venv/bin/activate
source .env  # carrega variáveis de .env
python -m atlas
```

Ou mais simples (se o shell suportar):
```bash
cd ~/atlas
python -m atlas  # lê .env automaticamente em algumas configurações
```

## Variáveis de ambiente obrigatórias

Veja `.env.example` para template. Obrigatório ter:
- `TELEGRAM_TOKEN` — token do bot Telegram
- `ATLAS_ALLOWED_USER_ID` — seu ID do Telegram

## Logs

- **Rasp:** `/tmp/atlas.log`
- **Local:** stdout (console)

## Parar Atlas

```bash
pkill -f 'python -m atlas'
```
