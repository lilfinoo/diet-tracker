# Fit Tracker — plano de lançamento iOS

Atualizado em 6 de outubro de 2026. Objetivo confirmado: publicar na App Store com Premium pago. O usuário tem iPhone e informou ter pago o Apple Developer Program. Confirmar ativação da equipe no App Store Connect/Xcode.

**Situação: ainda não enviar à revisão.** A compra/restauração Apple e a validação RevenueCat foram implementadas no código. Login Apple, documentos finais, build assinado e validação de compras no aparelho continuam pendentes. Veja `docs/REVENUECAT_SETUP.md`.

## Caminho escolhido

Manter Capacitor e a interface empacotada no iPhone, Flask no Render e PostgreSQL no Supabase. O app já não depende de carregar o site para mostrar suas telas: `webDir=copilot`, sem `server.url`. A interface usa HTML/CSS/JS dentro de uma WebView, com integrações nativas; não é uma reescrita em SwiftUI. Isso reaproveita os fluxos existentes e reduz o trabalho até a primeira versão.

A API continuará online. Manter apenas as páginas públicas de privacidade, termos e suporte necessárias ao lançamento. Não é preciso investir em um novo site institucional.

Para assinaturas, a recomendação é usar compras Apple com RevenueCat para validar acesso, renovação e restauração. O SDK oficial Capacitor foi integrado, com compra/restauração e validação pelo servidor; falta validar o fluxo no iPhone. [Documentação RevenueCat](https://www.revenuecat.com/docs/getting-started/installation/capacitor).

## Ordem de execução e critérios de conclusão

| Etapa | Trabalho | Responsável | Concluído quando |
| --- | --- | --- | --- |
| 1. Conta Apple | Pagamento informado como concluído; confirmar ativação e acesso ao App Store Connect | Titular | Conta ativa e equipe correta selecionável no Xcode |
| 2. Cadastro do app | Registrar `ai.fittracker.app`, criar ficha Fit Tracker, confirmar disponibilidade do nome e habilitar Sign in with Apple | Titular + Codex | Identificador e assinatura pertencem à mesma equipe |
| 3. Premium | Configurar contratos bancários/fiscais; criar grupo de assinaturas mensal/anual; conectar RevenueCat; implementar compra, restauração e acesso validado pelo backend | Titular configura contas; Codex implementa | Compra Sandbox libera Premium, restauração recupera acesso, cancelamento mantém acesso até vencimento e expiração/reembolso revogam acesso |
| 4. Conta e privacidade | Acrescentar login Apple mantendo Google; concluir exclusão com assinatura; preparar recuperação de conta, termos, privacidade e suporte | Codex + dados do titular | Cadastro/login/recuperação/exclusão funcionam e páginas públicas têm contato real e nenhum rascunho |
| 5. Produção | Render sempre ativo, health check, variáveis de produção, fila de IA se habilitada, Supabase e backup restaurável | Titular aprova custos; Codex verifica | API responde, IA conclui, dados persistem após reinício e restauração funciona em banco descartável |
| 6. TestFlight | Build assinado, upload e testes no iPhone; testar iPad enquanto suportado | Codex + titular/testadores | Fluxos abaixo passam no aparelho usando a API real |
| 7. App Store | Descrição, screenshots reais, privacidade, classificação etária, contato e conta para revisão; enviar versão final paga | Codex prepara; titular conclui portal | App e assinaturas aprovados e versão liberada |

As etapas 3–5 podem avançar enquanto a Apple ativa a equipe. A inscrição foi paga pelo titular. A correção WorkoutX abaixo inclui limpeza de cache por migração no próximo deploy; não há alteração de plano/custo de hospedagem.

## Pendências da versão paga

- Compras digitais: substituir PIX/cartão Asaas no iOS por compras Apple. O código usa RevenueCat no iOS para compra/restauração; a venda Apple ainda precisa ser validada no aparelho. A regra geral para desbloqueio digital é IAP; esta rota evita depender de exceções regionais. [Apple, regra 3.1.1](https://developer.apple.com/app-store/review/guidelines/#in-app-purchase).
- Preços: exibir os valores localizados retornados pela App Store, com período e renovação. Os R$ 20/mês e R$ 120/ano atuais são preços do Asaas e não configuram automaticamente a loja.
- Entitlement: usar o UUID da conta Fit Tracker no RevenueCat, manter segredos no servidor e liberar Premium somente com confirmação do provedor. Tratar notificações autenticadas, duplicadas e fora de ordem. Cliente sozinho não concede acesso.
- Restauração: ação visível para recuperar compras; testar conta/aparelho diferentes, logout e troca de conta. Definir a regra de vínculo para impedir transferência indevida ou duas assinaturas simultâneas.
- Login: Google já está integrado; acrescentar Sign in with Apple preserva as contas existentes e atende à opção equivalente exigida pela regra 4.8. [Apple, login](https://developer.apple.com/app-store/review/guidelines/#login-services).
- Exclusão: a API já apaga a conta, mas hoje exige cancelar assinatura antes. Ajustar o fluxo: informar que apagar a conta não cancela automaticamente uma assinatura Apple e permitir exclusão imediata. [Apple, exclusão](https://developer.apple.com/support/offering-account-deletion-in-your-app/).
- Consentimento: a cópia agora identifica Google Gemini e os dados enviados. O servidor exige a versão atual para uma nova autorização; consentimentos antigos não habilitam IA. Publicar API e app com a mesma versão, instruindo usuários de builds antigos a atualizar.
- Documentos: `copilot/privacy.html` e `copilot/terms.html` seguem como rascunhos. Faltam dados reais do titular, contato, fornecedores/regiões, retenção, regras de cobrança e elegibilidade. Acrescentar os documentos finalizados ao cadastro/perfil e à ficha da loja.
- Suporte: publicar uma página curta com e-mail real e ajuda para login, assinatura, privacidade e exclusão. Cadastro atual usa nome de usuário/senha, com e-mail opcional; recuperação precisa contemplar contas antigas.
- Conteúdo público: revisar perfil e vínculo profissional; caso o lançamento exponha conteúdo de outros usuários, validar denúncia, bloqueio e atendimento de abuso antes da revisão.

## Ambiente observado

| Item | Evidência em 06/10/2026 |
| --- | --- |
| Projeto iOS | Bundle `ai.fittracker.app`; versão 1.0, build 2; iOS 15+; iPhone e iPad; câmera, compartilhamento e Google nativos |
| Recursos | Ícone 1024×1024 sem transparência; interface e JSON de alimentos locais |
| Xcode | Xcode 27 / SDK iOS 27 instalados; requisito atual é Xcode 26+ e SDK iOS 26+ ([Apple](https://developer.apple.com/news/upcoming-requirements/)) |
| Render | Serviço `fit-tracker`, região Oregon; compute `free`; health check vazio; deploy automático desligado |
| Deploy ativo | Commit `5e53b70eb97f` de 03/10; checkout local em `da1a8c12c3d2`; alterações locais precisam ser revisadas antes do deploy |
| API pública | `/api/health`: HTTP 200; `/api/version`: v1.1.2; CORS aceita `capacitor://localhost` com credenciais |
| Cobrança atual | `/api/plans`: `provider_configured=false`, ambiente `production`; vendas ainda não habilitadas |
| Consentimento publicado | API ainda anuncia `draft-2026-08-29`; mudança local usa `2026-10-06` |
| Supabase | Informado pelo usuário; plano, SSL, backups, região e configuração efetiva não verificados nesta auditoria |
| IA/fila | Worker não apareceu na lista de serviços consultada; Redis/fila podem estar externos. Confirmar configuração e execução antes de vender acesso |

O Render gratuito suspende o serviço após 15 minutos sem tráfego. Planejar compute pago sempre ativo antes do lançamento; configurar `/api/health` como health check. [Render](https://render.com/docs/free).

## Contas e orçamento inicial

1. [Apple Developer — inscrição](https://developer.apple.com/programs/enroll/): pagamento já informado como concluído; confirmar ativação e acesso usando a conta Apple/iCloud. US$ 99/ano; preço local aparece na contratação. Pessoa física aparece com nome legal como vendedor; organização exige verificação própria.
2. [App Store Connect](https://appstoreconnect.apple.com/): após aprovação, concluir os contratos de apps pagos e os dados bancários/fiscais para receber pelas assinaturas.
3. [RevenueCat](https://app.revenuecat.com/): criar projeto Fit Tracker e app Apple com o bundle correto. Começa gratuito até US$ 2.500 em receita mensal rastreada; acima, o plano divulgado cobra 1% da receita rastreada. Essa cobrança é adicional à comissão da Apple. [Preços](https://www.revenuecat.com/pricing).
4. [Apple Small Business Program](https://developer.apple.com/app-store/small-business-program/): solicitar participação se elegível; comissão reduzida de 15% depende de inscrição e aprovação, não é automática.
5. Render: escolher o menor compute sempre ativo no [painel do serviço](https://dashboard.render.com/web/srv-d1dhpt7fte5s73bl4hg0), conferindo custo no momento da contratação. Separar orçamento de IA, banco e eventual worker conforme a configuração efetiva.

## Checklist no iPhone antes de enviar

- Instalação nova: cadastro por senha e por Apple/Google; autorização de IA opcional; alimentação manual funciona sem consentimento.
- Sessão: fechar/reabrir, trocar Wi-Fi/4G, voltar do background e sair; conta anterior não reaparece pelo cache.
- Diário: cadastrar, editar e excluir refeição; tirar/selecionar foto; cancelar ou negar permissão sem travar.
- Treino/progresso: abrir plano, concluir sessão, registrar medidas e compartilhar usando o sistema do iPhone.
- IA: gerar análise/plano; revogar consentimento; confirmar que novas chamadas são bloqueadas.
- Premium: compra, cancelamento da tela Apple sem cobrança, restauração, renovação, vencimento/reembolso e troca de conta.
- Exclusão: senha/reauth corretas; excluir conta gratuita e com assinatura; confirmar remoção de dados e foto.
- Rede: abrir offline, reconectar e sincronizar sem duplicar registros; API indisponível deve mostrar tentativa novamente.
- iPad: verificar layout/login/compra e screenshots se mantido como dispositivo suportado.

No App Store Connect, preparar categoria Saúde e Fitness, nome/subtítulo/descrição, screenshots do app em uso com dados fictícios, URL pública de privacidade, URL de suporte, classificação etária e rótulos de privacidade consistentes com conta, saúde/fitness, fotos, mensagens e analytics. A conta da revisão deve dar acesso aos recursos pagos sem depender de uma compra real.

## Verificação desta primeira etapa

- Implementado: bloqueio de checkout Asaas no iOS, sem valores Asaas no paywall; gestão de assinatura existente preservada.
- Implementado: declaração explícita Google Gemini e versão atual de consentimento no servidor/configurações.
- Testes JavaScript: 175 passaram, incluindo cinco testes novos de cobrança iOS versus web.
- Python: nove testes de privacidade passaram, incluindo rejeição de autorização antiga/sem versão. Suíte completa: 277 passaram e 38 falharam. A análise dos tracebacks e comparação com o código anterior identificou 35 expectativas do fluxo profissional removido, dois cenários Asaas com vencimento fixo já passado e uma expectativa antiga de texto PIX. Essas falhas não foram causadas pelas alterações desta etapa; reconciliar a suíte com o produto atual antes do lançamento.
- Lint: arquivos Python alterados passaram; `ruff check .` encontrou 14 erros preexistentes em scripts de marketing versionados. Corrigir esses scripts em trabalho próprio antes de exigir CI geral verde.
- Build: sincronização Capacitor e compilação Release sem assinatura concluídas com sucesso, usando Xcode 27 e uma cópia temporária do projeto e dos recursos sincronizados. Archive assinado e upload/TestFlight continuam pendentes.

Não publicar esta compilação como versão paga enquanto os critérios de compra, login, documentos e teste real estiverem pendentes.

## Correção WorkoutX Basic — 06/10/2026

- O titular informou ter pago o plano Basic. Uma consulta direta com a chave local retornou HTTP 200, `X-WorkoutX-Plan: basic` e um GIF válido de 360×360 sem marca d’água na prévia inspecionada. A chave não foi exposta.
- Causa confirmada: GIFs Free persistiam em `workoutx_gif`, no diretório local e por um ano no navegador. Trocar o plano não invalidava essas camadas.
- Migrações `d6a2f8c4b910` e `d7b3f9a5c021`: renovam o cache baixado e os imports administrativos antigos. A validação de produção confirmou marca d’água também nesses imports. O histórico de auditoria é preservado; contas, treinos e catálogo não são alterados.
- Cache local passa a usar `basic-v2`; cliente solicita uma URL nova no site e no iOS. Rotas passam a revalidar via ETag, sem manter uma imagem por um ano. Upload administrativo substitui também o arquivo local, sob o mesmo bloqueio usado na restauração/download.
- Downloads continuam sob demanda, com cache persistente, limite de concorrência e tratamento de 429 existentes. Não executar prefetch de todo o catálogo para esta limpeza.
- Próxima etapa do lançamento pago: confirmar acesso ao [App Store Connect](https://appstoreconnect.apple.com/), criar o app `ai.fittracker.app`, concluir contratos bancários/fiscais e cadastrar assinaturas mensal/anual. Depois integrar RevenueCat, compra/restauração Apple e login Apple antes do TestFlight.

Validação da correção: 34 testes Python de WorkoutX/privacidade e sete testes JavaScript de cobrança iOS/URL de GIF passaram; lint dos arquivos alterados e verificação de sintaxe passaram. Todas as migrações foram aplicadas do zero até `d7b3f9a5c021` em SQLite temporário. Validar a imagem pública e o health check após o deploy no Render.
