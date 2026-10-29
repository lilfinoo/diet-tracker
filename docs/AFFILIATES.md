# Indicações e afiliados — implementação local

## Resultado e limites

Implementado o cadastro administrativo de parceiros, códigos globais únicos, aplicação no cadastro ou na tela atual de convites, atribuição permanente, consulta de indicados e painel agregado de cada parceiro. A recompensa antiga continua sendo **3 novos cadastros no mês de Brasília → 1 mês de Premium**, no máximo uma recompensa por mês.

**O sistema financeiro permanece desativado.** Não há geração, liberação nem pagamento de comissão por cadastro, trial, restauração ou snapshot de acesso. A API responde `financial_tracking_enabled: false`; a tentativa de registrar pagamento retorna `503 / affiliate_finance_disabled`. As tabelas e a rotina interna de registro manual estão preparadas para uma integração futura; não representam receita ou comissão já apurada. Não há transferências Pix.

## Auditoria realizada

- Backend real: Flask, sessões próprias e SQLAlchemy/Alembic; não é Supabase Auth. O Supabase fornece PostgreSQL; os UUIDs são de `public.user`, não de `auth.users`.
- Consulta somente de leitura ao Supabase em 28/10/2026 confirmou `referral_code`, `referral`, `referral_reward`, `subscription`, `billing_event` e revisão implantada `a2c4e6f8b0d1`. Nenhum dado pessoal foi necessário à auditoria.
- `src/services/referrals.py`: `ensure_code()` cria código pessoal; `attach_referral()` valida e associa no cadastro de senha, Google ou Apple; `referral_summary()` entrega a meta mensal. O terceiro cadastro cria `ReferralReward` e `Subscription(provider="referral")`, sem alterar assinatura paga nem `User.is_premium`.
- A associação acontece na mesma transação do cadastro. Código inválido desfaz a conta inteira; login social existente não aplica código novamente.
- App SwiftUI: `native-ios/App/NativeSocialAuth.swift` já recebe código no primeiro acesso. `NativeReferralView.swift` mostra convites. Ambos reutilizados; a mesma tela de convites agora permite código de parceiro quando elegível.
- Compras: RevenueCat no app SwiftUI (`NativeBillingStore.swift`) e no cliente Capacitor (`copilot/js/native-billing.js`). A identidade usada pelo SDK é o UUID da sessão. A consulta canônica fica em `src/services/revenuecat.py` e o webhook autenticado em `src/routes/billing_routes.py`.
- Não existe no backend um mapeamento próprio StoreKit/appAccountToken nem receptor próprio de App Store Server Notifications V2. A verificação atual é delegada ao RevenueCat; não foi criado um receptor alternativo de JWS sem validação.
- `Subscription(provider="revenuecat")` é um snapshot de acesso: seu ID externo é o UUID da conta, não uma transação financeira. Trial, sandbox, restauração e transferências impedem inferir uma venda a partir de `active` ou `is_premium`.
- Asaas também existe, com checkout, assinaturas, `BillingEvent` idempotente e reconciliação. A integração atual não oferece um histórico financeiro unificado com receita líquida para todas as plataformas; foi preservada.

## Banco e migration

Migration nova: `migrations/versions/a7c9e1f3b5d8_add_affiliate_attribution.py`, após `f2a0b8c6d4e1`.

O release preserva a cadeia canônica `a2c4e6f8b0d1 → f2a0b8c6d4e1 → a7c9e1f3b5d8`. Como pré-requisito, `f2a0b8c6d4e1` amplia `workout_plan.source` para também aceitar `template` e adiciona `workout_session.duration_seconds_confirmed` e `workout_session.energy_estimate`, ambas opcionais. Não altera dados existentes; o backend anterior continua compatível com as colunas extras. O restante das funcionalidades locais de água e estimativa energética não integra este release.

| Entidade | Alteração |
| --- | --- |
| `affiliate` | Nova: cadastro, conta vinculada opcional, status, regras mensais e anuais separadas, duração e observações. |
| `referral_code` | Reutilizada. Código torna-se PK global de até 32 caracteres; usuário proprietário único opcional ou afiliado; tipo, ativo e criação. |
| `referral` | Reutilizada como atribuição. Acrescenta tipo, afiliado, código, origem e validação; mantém unicidade por convidado e histórico anterior. |
| `referral_reward` | Mecânica e tabela preservadas. |
| `affiliate_commission` | Nova, preparada: transação por provedor/ambiente, valores decimais bruto/líquido/comissão opcionais, taxa aplicada, datas e estado. |
| `affiliate_payout` | Nova, preparada: período, moeda, valor, estado, data e referência administrativa. |
| `admin_action_audit` | Reutilizada para criação/edição de parceiros e códigos, com antes/depois nas configurações. |

A migration preenche o código das atribuições antigas pelo indicador. Nenhum código pessoal ou recompensa é regenerado. Constraints verificam proprietários, taxas, estados, valores não negativos e ambiente. Comissão liberada/paga exige valores líquido e comissão conhecidos. Há índices para parceiro/data, códigos e comissões por parceiro/ambiente/status. Transação única por provedor/ID/ambiente evita duplicação financeira futura.

Exclusão de convidado anonimiza seu vínculo (`SET NULL`) sem reduzir a contagem histórica. Exclusão do indicador comum mantém o comportamento legado (`CASCADE`). A exclusão de conta vinculada ao parceiro remove só o vínculo de login, preservando o parceiro. Parceiros com histórico não podem ser removidos via FK; não há endpoint de exclusão.

### Implantação segura

Nada foi aplicado em produção. Antes de implantar:

1. Fazer backup e testar a cadeia de migrations em uma cópia PostgreSQL do ambiente real.
2. Conferir a versão Alembic e que o usuário SQL do backend é proprietário das tabelas ou possui acesso de servidor que contorna RLS. Não usar o papel `authenticated` para o ORM.
3. Aplicar `DATABASE_URL=... python -m flask --app main db upgrade` no ambiente escolhido. A revisão intermediária `f2a0b8c6d4e1` também será aplicada se o ambiente ainda estiver na revisão observada.
4. Publicar backend antes do app novo. Os campos anteriores e os códigos pessoais continuam disponíveis para o app já publicado.
5. Verificar `/api/health`, convites existentes e o roteiro Ana Fitness abaixo.

A troca de PK, FKs e backfill exige bloqueios DDL: executar em janela adequada ao volume de dados. O upgrade é preservador; testes locais exercitam dados anteriores. O downgrade recusa execução quando há parceiros, para impedir perda silenciosa de histórico. Para rollback com dados, voltar o código da aplicação mantendo o esquema expandido, ou restaurar backup aprovado. Não executar downgrade destrutivo em produção.

### Segurança

- Novas tabelas e tabelas de indicação expandidas recebem RLS no PostgreSQL, política sem acesso de cliente e revogação de privilégios de `PUBLIC`, `anon` e `authenticated`. O acesso é exclusivamente pela API Flask autorizada. Nenhuma política depende de metadados editáveis do cliente.
- Administração usa `User.is_admin` carregado no servidor, sessão autenticada e CSRF existente. A conta vinculada ao influencer é definida apenas pelo administrador.
- `/api/affiliates/me` usa o UUID da sessão, sem aceitar ID de parceiro do cliente; devolve apenas métricas agregadas, códigos públicos e pagamentos sem referência administrativa.
- Sem e-mails, nomes, UUIDs ou dados de saúde dos indicados no painel do influencer. Somente administradores consultam a lista de usuários.
- Aplicação usa bloqueios de usuário/código/parceiro e unicidade do convidado. Repetir o mesmo código ativo é idempotente; outro código retorna conflito. Desativar impede novos vínculos e mantém histórico.
- Consulta externa ao RevenueCat acontece antes dos bloqueios; a elegibilidade local é revalidada dentro da transação. A vinculação administrativa segue ordem usuário → parceiro para evitar ciclo de locks.
- Atribuição é atômica no banco. Compras externas à aplicação não participam dessa transação: uma integração financeira futura precisa verificar também a data real da primeira compra antes de reconhecer conversão/comissão.
- Listas paginadas, respostas privadas `no-store`, códigos com limite de tentativas, valores apresentados com escape/textContent e métricas carregadas em lote.
- Não foram adicionadas chaves no app, permissões diretas ao banco nem endpoint para o cliente escrever percentuais/comissões.

## Política dos códigos

- Normalização no servidor: remover espaços e converter para maiúsculas; caracteres aceitos `A–Z`, `0–9`, de 3 a 32 posições. Códigos pessoais continuam com 12 caracteres hexadecimais.
- `user_referral`: somente cadastro, mantendo todos os critérios anteriores de recompensa.
- `affiliate`: cadastro ou aplicação autenticada posterior, desde que não exista indicação anterior, assinatura comercial de qualquer estado ou tentativa de checkout. Benefícios administrativos/de convites não são compra comercial.
- Quando RevenueCat está configurado, aplicação posterior consulta também seu histórico canônico; compra/trial anterior, mesmo expirado e ainda não sincronizado localmente, impede aplicação. Falha do provedor impede a operação temporariamente. Sem configuração, o bloqueio usa apenas o histórico local conhecido; configurar RevenueCat é necessário para a verificação externa.
- O código do parceiro não concede Premium nem aumenta o contador de amigos. Cada conta tem no máximo uma atribuição; não há troca livre nem autoindicação pela conta vinculada.
- Aplicação posterior mostra confirmação com nome público. O cadastro mantém a resposta original de criação e o vínculo pode ser consultado na tela de convites.

## Operação: Ana Fitness / ANAFIT

1. Entrar com administrador existente e abrir `/admin` → **Parceiros**.
2. Informar nome e nome público `Ana Fitness`, código `ANAFIT`, 50% primeira mensalidade, 10% renovações e 12 meses. Regras anuais vazias significam **sem regra anual**; não herdam a taxa mensal.
3. Opcionalmente vincular o UUID da conta da Ana para liberar seu painel. A própria conta vinculada não pode aplicar `ANAFIT`.
4. Criar conta de teste com `ANAFIT` no campo de convite, ou usar **Código de parceiro** na tela atual de convites de uma conta elegível antes da assinatura.
5. Selecionar Ana em **Parceiros → Ver e editar**: aparecem os códigos, quantidade de atribuições e lista paginada de usuários. Estado da assinatura é acesso, não prova de cobrança.
6. Usar **Criar código**, **Copiar** ou **Desativar**. Desativação preserva a lista anterior. Desativar a parceria suspende todos os seus códigos para novas aplicações.
7. Ana entra com a conta vinculada no mesmo domínio e abre `/affiliate.html`. Vê somente seus resultados agregados. A API correspondente é `/api/affiliates/me`.

## Endpoints

Todos sob `/api`. Mutações de sessão exigem `X-CSRF-Token` e `credentials: include`.

| Método/caminho | Uso |
| --- | --- |
| `GET /referrals` | Resposta legada de código pessoal/meta mensal, sem mudanças de contrato. |
| `GET /referrals/attribution` | Vínculo da conta atual e elegibilidade local para aplicação. |
| `POST /referrals/apply` | Apenas `{ "code": "ANAFIT" }`; aplicação de parceiro na conta da sessão. |
| `GET/POST /admin/affiliates` | Lista paginada/cadastro. |
| `PATCH /admin/affiliates/{id}` | Atualizar parceiro e regras, com auditoria. |
| `POST /admin/affiliates/{id}/codes` | `{ "code": "ANAFIT2" }` ou `{}` para gerar. |
| `PATCH /admin/affiliates/{id}/codes/{code}` | `{ "active": false }`; preservar histórico. |
| `GET /admin/affiliates/{id}/referrals` | Lista administrativa paginada. |
| `GET /admin/affiliates/{id}/payouts` | Histórico paginado preparado. |
| `POST /admin/affiliates/{id}/payouts` | Preparado para pagamento manual de comissões liberadas; atualmente bloqueado. |
| `GET /affiliates/me` | Painel agregado exclusivo do parceiro vinculado. |

Listas usam `page` e `per_page` (máximo 100). Cadastros e alterações retornam objeto direto; listas usam `affiliates`, `referrals` ou `payouts` mais `page/pages/total`.

## Integração financeira futura necessária

Não basta habilitar uma flag. Implementar e testar um adaptador de transações verificadas com:

- Identificador financeiro estável, ID original da assinatura, produto/plano, ambiente e associação segura à conta; impedir reatribuição por transferência/restauração de compra.
- Verificação pelo provedor/SDK e, caso se implemente receptor Apple próprio, validação criptográfica e de cadeia de confiança do `signedPayload` V2 e das transações. Nunca confiar no JSON enviado pelo app.
- Primeira cobrança paga distinguida de teste grátis, renovação, mudança de plano, recuperação e restauração. IDs de eventos não substituem IDs de transação para deduplicação.
- Data verificada da primeira cobrança para limitar recorrência; snapshot imutável da regra aplicada e regras anuais próprias. Não usar o momento do webhook para reiniciar os 12 meses.
- Receita líquida efetivamente recebida por moeda, reconciliada com relatórios de liquidação e regra financeira definida. Sem líquido, valor final `NULL` e comissão pendente; sem liberação/pagamento.
- Inbox e histórico auditável de estados, reembolsos/revogações inclusive históricos, chargebacks e estornos após pagamento. Manter separação sandbox/produção e cancelar/reverter sem apagar a transação.
- Asaas: eventos `PAYMENT_CONFIRMED` e `PAYMENT_RECEIVED` podem repetir uma cobrança; deduplicar pelo ID do pagamento. Reembolso de período anterior deve afetar sua comissão, mesmo sem mudar o entitlement atual.
- Ao concluir o adaptador e a reconciliação, habilitar finanças e disponibilizar a operação administrativa manual preparada, com auditoria e valor calculado no servidor. Não há endpoint para criar/liberar comissões por afirmação do cliente.

## Arquivos desta implementação

- `src/models/user.py`: modelos/constraints; `migrations/versions/a7c9e1f3b5d8_add_affiliate_attribution.py`: migration.
- `src/services/referrals.py`, `src/services/affiliates.py`: lógica; `src/routes/referral_routes.py`, `src/routes/affiliate_routes.py`, `main.py`: API e registro.
- `native-ios/Sources/FitTrackerCore/ReferralAPI.swift`, `native-ios/App/NativeReferralView.swift`, `native-ios/App/NativeSocialAuth.swift`: app.
- `copilot/admin.html`, `copilot/js/admin-affiliates.js`, `copilot/affiliate.html`: administração e painel agregado.
- `tests/test_affiliates.py`, `tests/test_affiliate_migration.py`, `native-ios/Tests/FitTrackerCoreTests/AccountAPITests.swift`: novos casos automatizados.
- `docs/AFFILIATES.md`: operação, auditoria, implantação e limites.

Os demais arquivos com alterações locais anteriores não fazem parte desta entrega.

## Verificação

- Ambiente Python 3.13 novo em `/private/tmp`, dependências de `requirements.txt` instaladas sem caches/bytecode após resolver a limitação de espaço.
- Suíte Python completa: **868 testes aprovados**, com avisos de depreciação existentes. Após os ajustes finais, **42 testes de afiliados, convites e migrations aprovados**, incluindo o roteiro exato Ana Fitness/ANAFIT e a proteção contra downgrade com histórico.
- Suíte JavaScript: **256 testes aprovados**, incluindo os 7 casos de carregamento administrativo existentes. Sintaxe dos scripts novos e smoke DOM do painel do parceiro aprovados.
- `py_compile` dos arquivos Python envolvidos: aprovado. Ruff dos arquivos desta tarefa: aprovado.
- `ruff check .`: três erros preexistentes em `marketing/reel-ia-organizada-2026-10-27/renderizar_previa.py` (import não usado e duas f-strings sem interpolação), preservados por estarem fora do escopo.
- Análise de sintaxe Swift dos quatro arquivos alterados: aprovada. Foram adicionados cinco testes Swift, mas **`swift test` não concluiu por falta de espaço em disco ao gerar módulos**; não foi validado build completo do app nem execução desses testes.
- Nenhuma migration aplicada nem deploy realizado em produção.

Testes cobrem cadastro Ana, aplicação, contador antigo, códigos inválidos/desativados, unicidade/concorrência, privacidade, autorização, CSRF, elegibilidade, ausência de vendas fictícias em eventos RevenueCat repetidos/trial/revogação e migração com backfill/histórico.

A concorrência automatizada local usa duas conexões SQLite para verificar a constraint final. Bloqueios PostgreSQL/RLS devem ser exercitados também em staging antes da implantação; não foram testados alterando produção.
