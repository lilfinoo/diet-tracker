# Premium Apple — integração RevenueCat

## Configuração

App: `ai.fittracker.app`. Entitlement: `fittracker_ai_pro`. Oferta: `default`.
Produtos: `ai.fittracker.premium.monthly` e `ai.fittracker.premium.annual`.

No Render, configurar `REVENUECAT_IOS_API_KEY` (chave pública `appl_`),
`REVENUECAT_SECRET_API_KEY` (chave privada V1) e
`REVENUECAT_WEBHOOK_AUTHORIZATION` (valor completo do header Authorization).
Nenhuma credencial privada pertence ao app, ao Git ou às URLs.

Webhook RevenueCat: `https://diet-tracker-6i67.onrender.com/api/billing/revenuecat/webhook`,
apenas para Fit Tracker (iOS), todos os eventos. O servidor consulta o estado
canônico da conta; o conteúdo do evento ou do cliente não concede Premium.

O SDK usa o UUID da conta autenticada. A compra/restauração é seguida de
sincronização autenticada no servidor. Cancelar a renovação mantém o período
pago; expiração remove o acesso Apple sem alterar uma assinatura Asaas válida.
Excluir a conta não cancela uma assinatura Apple: o app oferece gerenciamento
na Apple antes da exclusão, mas permite apagar a conta imediatamente.

## TestFlight

`REVENUECAT_ALLOW_SANDBOX=false` deve permanecer em produção. Para testar,
colocar somente os UUIDs dos testadores em `REVENUECAT_SANDBOX_USER_IDS`,
separados por vírgula. Remover os UUIDs depois dos testes. Não liberar compras
Sandbox para todos os usuários da API de produção.

Testar no iPhone: preços localizados; elegibilidade real para sete dias grátis;
compra cancelada sem liberar Premium; compra confirmada liberando no servidor;
restauração; logout/troca de conta; renovação; expiração e reembolso; indisponibilidade
do servidor; gerenciamento de assinatura e exclusão de conta. Compras não são
consideradas validadas apenas porque testes com mocks passaram.

A sincronização usa um bloqueio no processo e depende do único worker Gunicorn
configurado no projeto. Antes de escalar para vários processos, usar coordenação
no banco para evitar atualizações concorrentes do estado.

O SDK nativo foi adicionado ao projeto Capacitor. Executar `npm ci` e
`npm run ios:sync` antes de compilar. Build assinado e teste no aparelho são
necessários antes de enviar à revisão.
