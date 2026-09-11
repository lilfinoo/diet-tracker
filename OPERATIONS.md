# Operação em produção

Este guia separa o que já está implementado no repositório das configurações que precisam ser feitas nas contas externas. Nunca salve chaves no Git; use apenas Environment Variables do Render e Actions Secrets do GitHub.

## 1. Redis e worker de IA

O Redis tem duas funções: manter um contador único de rate limit entre processos e transportar jobs de IA entre o servidor web e o worker Celery. O resultado e o estado de cada job ficam no PostgreSQL; o Redis não armazena o resultado definitivo.

### Criar no Render

1. Abra o dashboard do Render e selecione **New > Key Value**.
2. Escolha a mesma região do Web Service e do PostgreSQL.
3. Ative persistência. Uma fila não deve usar uma instância configurada para descartar chaves sob pressão.
4. Crie o serviço e copie a **Internal Redis URL**. Ela começa com `redis://` ou `rediss://`.
5. No Web Service, abra **Environment** e adicione `REDIS_URL` com essa URL.
6. Mantenha `AI_ASYNC_ENABLED=true`. `CELERY_BROKER_URL` pode ficar vazio; nesse caso o app usa `REDIS_URL`.

### Criar o worker no Render

1. Selecione **New > Background Worker** e conecte o mesmo repositório e branch do site.
2. Use o mesmo Build Command do Web Service, normalmente `pip install -r requirements.txt`.
3. Use o Start Command `python -m celery -A main:celery_app worker --loglevel=INFO --concurrency=2`.
4. Copie para o worker todas as variáveis necessárias pelo app: `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`, configurações Gemini, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `ASAAS_ENV`, `ASAAS_API_BASE_URL`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `BILLING_ENABLED`, `AI_TASK_RETENTION_DAYS`, `ANALYTICS_RETENTION_DAYS`, `METRICS_ENABLED`, `METRICS_TOKEN` e as quatro variáveis `MEDIA_R2_*`.
5. Faça deploy primeiro do worker e depois do Web Service. Confirme nos logs do worker que aparece `celery@... ready`.
6. Gere uma análise de macros com uma conta Premium. O POST deve retornar `202`, o navegador consultará `/api/ai/tasks/<id>` e o worker concluirá o job.

O modo gratuito continua síncrono porque os três usos só podem ser consumidos após uma resposta bem-sucedida. O volume máximo desse caminho é limitado a três usos por conta.

## 2. Métricas e Grafana Cloud

Prometheus é o formato de métricas. Grafana é a tela que transforma essas métricas em gráficos e alertas. O endpoint `/metrics` exige um token Bearer e não contém nomes, e-mails, IPs ou conteúdo dos usuários.

### Preparar o app

1. Gere um token localmente: `openssl rand -hex 32`.
2. No Web Service e no worker, defina `METRICS_ENABLED=true` e `METRICS_TOKEN=<token-gerado>`.
3. Após o deploy, teste: `curl -H "Authorization: Bearer <token>" https://SEU-DOMINIO/metrics`.
4. Uma chamada sem o header deve retornar `401`.

### Criar o Grafana Cloud

1. Crie uma conta em `https://grafana.com/products/cloud/` e abra seu Stack.
2. Em **Connections**, procure **Hosted Prometheus** e abra a opção de enviar métricas.
3. Anote o **Remote Write Endpoint**, o **Prometheus username/instance ID** e crie um Access Policy Token com permissão `metrics:write`.
4. No Render, crie outro **Background Worker** usando este repositório com **Root Directory** `monitoring` e runtime Docker.
5. Configure nesse worker:
   - `APP_METRICS_HOST`: domínio sem `https://`, por exemplo `fit-tracker.onrender.com`.
   - `METRICS_TOKEN`: o mesmo token do Web Service.
   - `PROMETHEUS_REMOTE_WRITE_URL`: Remote Write Endpoint do Grafana.
   - `PROMETHEUS_USERNAME`: instance ID informado pelo Grafana.
   - `GRAFANA_CLOUD_API_KEY`: token com `metrics:write`.
6. Faça deploy. Em **Explore > Metrics**, procure `diet_tracker_http_requests_total`.
7. Crie alertas iniciais:
   - taxa de HTTP 5xx maior que 1% durante 5 minutos;
   - `diet_tracker_ai_oldest_queued_seconds > 300` durante 10 minutos;
   - endpoint `/api/health` indisponível por 2 minutos;
   - aumento de jobs com `status="failed"`.

## 3. Backups em Cloudflare R2

O workflow diário gera um `pg_dump` no formato custom, verifica o arquivo e envia uma cópia datada e `latest.dump`. O teste mensal restaura `latest.dump` em um PostgreSQL descartável do GitHub Actions e consulta o schema e usuários.

### Criar o bucket

1. Crie uma conta Cloudflare e abra **R2 Object Storage**.
2. Crie um bucket privado, por exemplo `diet-tracker-backups`.
3. Abra **Manage R2 API Tokens > Create API token**.
4. Dê apenas permissão **Object Read & Write** nesse bucket. Guarde Access Key ID e Secret Access Key; o segredo só aparece uma vez.
5. Copie o endpoint S3 do bucket, semelhante a `https://<account-id>.r2.cloudflarestorage.com`.
6. Configure uma regra de lifecycle no bucket para remover objetos em `postgres/` após 30 ou 90 dias. Não habilite acesso público.

### Configurar GitHub Actions Secrets

No GitHub, abra **Settings > Secrets and variables > Actions > New repository secret** e crie:

- `BACKUP_DATABASE_URL`: use a URL externa do PostgreSQL do Render, não a URL interna.
- `BACKUP_AWS_ACCESS_KEY_ID`: Access Key ID do token R2.
- `BACKUP_AWS_SECRET_ACCESS_KEY`: Secret Access Key do token R2.
- `BACKUP_AWS_REGION`: use `auto` para R2.
- `BACKUP_S3_BUCKET`: nome do bucket.
- `BACKUP_S3_ENDPOINT_URL`: endpoint S3 do R2.

Depois abra **Actions > Daily PostgreSQL Backup > Run workflow**. Confirme que o job ficou verde e que existem `postgres/latest.dump` e um arquivo datado no bucket. Em seguida execute manualmente **Monthly PostgreSQL Restore Check**; ele precisa ficar verde antes do lançamento.

Para restaurar manualmente, baixe um `.dump`, crie um PostgreSQL vazio e execute:

```sh
RESTORE_CONFIRM=RESTORE ./scripts/restore_backup.sh backup.dump 'postgresql://usuario:senha@host:5432/banco_vazio'
```

Nunca teste restauração diretamente no banco de produção.

## 4. Fotos de perfil em Cloudflare R2

As fotos de perfil usam um bucket privado diferente do bucket de backups. O app valida JPEG, PNG ou WebP de até 3 MB e 16 megapixels, redimensiona para no máximo 512 × 512, remove metadados e grava somente WebP. O navegador recebe a imagem por uma rota autenticada com cache privado desabilitado.

1. Crie outro bucket privado, por exemplo `diet-tracker-media`. Não reutilize `diet-tracker-backups` e não habilite domínio público.
2. Crie um token R2 com permissão **Object Read & Write** apenas nesse bucket.
3. No Web Service e no worker, configure `MEDIA_R2_ENDPOINT_URL`, `MEDIA_R2_ACCESS_KEY_ID`, `MEDIA_R2_SECRET_ACCESS_KEY` e `MEDIA_R2_BUCKET`.
4. Confirme que upload, troca, remoção da foto e exclusão da conta removem os objetos esperados.
5. Monitore objetos sem referência e uso do bucket. Não aplique lifecycle que remova fotos ainda vinculadas a contas ativas.

## 5. Asaas em produção

1. No painel Asaas, confira em dados comerciais/bancários se a conta está aprovada e se a transferência automática ou o saque está configurado conforme sua preferência.
2. Inicie o deploy com `BILLING_ENABLED=false`, `ASAAS_ENV=production` e `ASAAS_API_BASE_URL=https://api.asaas.com/v3`. O kill switch bloqueia novos checkouts, mas mantém o webhook e a reconciliação ativos para pagamentos já iniciados.
3. Confirme que `ASAAS_API_KEY` é uma chave de produção e gere `ASAAS_WEBHOOK_TOKEN` com `openssl rand -hex 32`.
4. No painel Asaas, configure o webhook `https://SEU-DOMINIO/api/webhooks/asaas` com o mesmo segredo de `ASAAS_WEBHOOK_TOKEN`. Habilite `CHECKOUT_PAID`, `CHECKOUT_CANCELED`, `CHECKOUT_EXPIRED`, eventos de assinatura e todos os eventos de cobrança.
5. Após a migração, execute `python -m flask --app main reconcile-asaas`. Assinaturas Asaas antigas ficam pendentes até a reconciliação encontrar um pagamento `CONFIRMED` ou `RECEIVED`; confira manualmente o resultado antes de liberar vendas.
6. Defina `BILLING_ENABLED=true`, faça novo deploy e confirme que `GET /api/plans` retorna `provider_configured: true` e `provider_environment: production`.
7. Para validar apenas o recebimento bancário, crie no painel Asaas uma cobrança Pix pequena para você mesmo, pague e confira saldo, taxa e transferência.
8. Para validar o app de ponta a ponta, use uma conta comum do site, compre cada modalidade real e confira: cartão permanece pendente até `PAYMENT_CONFIRMED` ou `PAYMENT_RECEIVED`; PIX permanece pendente até `CHECKOUT_PAID`; cancelamento mantém somente o período já pago.
9. Depois do teste, cancele ou reembolse no painel se necessário. Confirme que estorno e chargeback revogam o período correspondente.
10. Não presuma prazo de saque: ele depende do meio de pagamento, análise da conta e configuração atual exibida pelo próprio Asaas.

O cartão usa Checkout recorrente. O PIX usa Checkout avulso e libera 30 dias somente após `CHECKOUT_PAID`; a renovação fica disponível nos últimos 7 dias e soma 30 dias ao vencimento atual. A API de Checkout do Asaas não oferece consulta de estado: se um webhook PIX falhar, localize o evento em **Webhooks > Logs** no painel Asaas e solicite o reenvio. Monitore registros `billing_event` com `processing_status='failed'`.

### Rotinas agendadas

Crie dois **Cron Jobs** no Render com as mesmas variáveis do Web Service:

- A cada 15 minutos: `python -m flask --app main reconcile-asaas`. A rotina reconcilia assinaturas recorrentes e expira checkouts locais vencidos; não concede PIX sem `CHECKOUT_PAID`.
- Diariamente: `python -m flask --app main privacy-cleanup`. A rotina remove tarefas de IA concluídas após `AI_TASK_RETENTION_DAYS` (padrão 7), limpa entradas de tarefas travadas e remove analytics após `ANALYTICS_RETENTION_DAYS` (padrão 395).

Alertar quando `reconcile-asaas` reportar `failed` maior que zero, quando houver `billing_event` falho por mais de 15 minutos ou quando qualquer Cron Job falhar. Os logs devem registrar apenas contagens e tipos de evento, nunca payloads, e-mails, tokens ou IDs do provedor.

## 6. Capacidade

Dez mil contas cadastradas não equivalem a dez mil requisições simultâneas. Antes de aumentar instâncias, defina uma meta de concorrência e valide p95, erros HTTP, conexões PostgreSQL e fila de IA com tráfego representativo.

O processo web aceita `GUNICORN_THREADS` (padrão 8), e o pool PostgreSQL usa `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` e `DB_POOL_RECYCLE`. Mantenha `WEB_CONCURRENCY=1` enquanto as métricas Prometheus forem process-local. Para mais processos ou réplicas, configure coleta multiprocess/por instância e garanta que `workers × (pool_size + max_overflow)` não ultrapasse o limite de conexões do PostgreSQL.

Critérios mínimos antes de divulgar para 10.000 usuários:

1. teste de carga no ambiente de produção com dados descartáveis;
2. p95 e taxa de erro dentro da meta definida;
3. Redis, worker Celery e PostgreSQL sem saturação;
4. alertas de 5xx, latência, fila de IA e falhas de webhook ativos;
5. restore de backup executado e documentado;
6. pagamento real controlado por cartão e PIX validado ponta a ponta.

## 7. Catálogo local

`copilot/minha-pasta/alimentos.json` foi declarado pelo autor como compilação original. O arquivo permanece local para reduzir custo e latência da IA. Preserve `copilot/minha-pasta/README.md` junto com o catálogo e não incorpore dados copiados de bases de terceiros sem revisar a licença.
