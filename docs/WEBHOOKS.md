# Webhooks — como ligar reindex automático e gatilhos externos

Guia operacional para expor o backend da plataforma à internet (durante
dev local) e configurar GitHub/Jira pra disparar webhooks.

## Por que isso é necessário

A plataforma tem 2 webhooks reais hoje:

1. **GitHub push** → indexer reindex dos arquivos do diff (LEO-17).
2. **GitHub PR comment / review** → playbook miner classifica feedback
   recorrente (Fase 1.3).

E está planejado:

3. **Jira issue created/updated** → enqueue de run autônomo (Nível 3).

Como o backend roda em `localhost:9000` dentro do WSL, GitHub/Jira na
internet não conseguem chamar. Precisamos de um **tunnel reverso** que
exponha uma URL HTTPS pública apontando pro localhost.

## Opção A — cloudflared (recomendada — gratuita sem limite)

### Instalação

No WSL Ubuntu:

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
cloudflared --version
```

### Tunnel ad-hoc (sessão)

```bash
cloudflared tunnel --url http://localhost:9000
```

Saída exemplo:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at:                                          |
|  https://abc-def-ghi.trycloudflare.com                                                     |
+--------------------------------------------------------------------------------------------+
```

Aquele URL `*.trycloudflare.com` é o que você configura no GitHub.

**Limitação:** URL muda a cada reinício. Pra URL estável, use tunnel
nomeado (próxima seção).

### Tunnel nomeado (URL permanente)

1. `cloudflared tunnel login` (abre browser, autoriza com sua conta CF)
2. `cloudflared tunnel create dev-autonomo`
3. Cria `~/.cloudflared/config.yml`:

```yaml
tunnel: <UUID-DO-TUNNEL>
credentials-file: /home/rubens/.cloudflared/<UUID>.json
ingress:
  - hostname: dev-autonomo.seu-dominio.com
    service: http://localhost:9000
  - service: http_status:404
```

4. `cloudflared tunnel route dns dev-autonomo dev-autonomo.seu-dominio.com`
5. `cloudflared tunnel run dev-autonomo`

URL agora é estável.

## Opção B — ngrok (limite de 1h no plano free)

```bash
curl -O https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Cadastra: https://dashboard.ngrok.com/get-started/your-authtoken
ngrok config add-authtoken <TOKEN>

# Sobe tunnel
ngrok http 9000
```

Limitações free:
- URL muda a cada sessão (max ~2h).
- 1 tunnel ativo por conta.

## Configurar webhook GitHub no repo do cliente

Depois de ter o URL público do tunnel (ex: `https://dev-autonomo.example.com`):

1. No GitHub, vai em `Settings > Webhooks > Add webhook` no **repo do
   cliente** (não no da plataforma).
2. **Payload URL:** `https://dev-autonomo.example.com/webhooks/github/push`
3. **Content type:** `application/json`
4. **Secret:** (opcional mas recomendado) algum token aleatório. Salvar
   no vault como `GITHUB_WEBHOOK_SECRET` via UI do admin.
5. **Events:** marcar **Push** e **Pull request review comment**.
6. Active: ✓
7. Add webhook.

O GitHub manda um ping inicial. Se voltou 2xx, está ok. Se não, ver
log do backend (`tail -f /tmp/backend.log`).

## Configurar webhook Jira (futuro — Nível 3)

1. Na sua Atlassian admin, vai em `System > WebHooks > Create`.
2. **URL:** `https://dev-autonomo.example.com/webhooks/jira/issue`
3. **Events:** `Issue Created`, `Issue Updated`.
4. **JQL filter:** `project = LEO AND issuetype = Tarefa` (ou o que
   fizer sentido).
5. Save.

## Segurança

- Cloudflared/ngrok são **seguros pra dev** mas não pra produção
  (qualquer um com a URL acessa o backend).
- Sempre configure HMAC secret no webhook GitHub e valide no handler
  do `webhooks.py` (já tem suporte parcial).
- Pra produção: deploy do backend em servidor real com DNS dedicado.
  Tunnel é só pra dev local.

## Validar que está funcionando

```bash
# Do PC do usuário (não do WSL), tentar GET no health
curl https://<seu-tunnel-url>/health
# Esperado: {"status":"ok"}
```

Se não voltar 200, o tunnel não está apontando certo. Confirme que:
1. Backend está rodando (`ss -tlnp | grep 9000`)
2. Tunnel aponta pra porta 9000 (não 8000)
3. Firewall do WSL não está bloqueando

## Quando ligar pra valer

Hoje a sessão dev costuma deixar isso desligado. Liga quando:
1. Quer testar reindex automático ponta-a-ponta (LEO-17 implementado).
2. Quer testar playbook miner com PR comment real.
3. Está demonstrando pra cliente.

Pra dev no dia-a-dia, simular o webhook localmente é mais barato:

```bash
curl -X POST http://localhost:9000/webhooks/github/push \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d @sample-push-payload.json
```
