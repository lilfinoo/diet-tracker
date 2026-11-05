# Fit Tracker — base iOS em SwiftUI

Projeto paralelo ao aplicativo Capacitor de `ios/`. O projeto já contém navegação nativa em cinco abas, autenticação por usuário/senha e fluxos de dieta, treino, planos e progresso ligados aos contratos da API existente. O visual aprovado está em `docs/swiftui-proposal/index.html`; a validação visual e funcional das telas SwiftUI no aparelho ainda está pendente.

Abra `FitTrackerNative.xcodeproj` e selecione o esquema `FitTrackerNative`. O projeto usa iOS 15 ou posterior e um pacote Swift local, sem dependências externas. O ícone oficial foi reaproveitado do projeto iOS existente. A URL HTTPS da API usa `FIT_TRACKER_API_BASE_URL` no projeto e é incorporada pela chave `FitTrackerAPIBaseURL` em `App/Info.plist`; não há senha ou token embutido.

## Verificação local

```sh
swift test --package-path native-ios
xcodebuild -project native-ios/FitTrackerNative.xcodeproj -scheme FitTrackerNative -configuration Debug -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

Os testes usam respostas simuladas e não acessam contas de produção. Verificam os contratos JSON, renovação do CSRF antes de login/logout, envio do token da sessão atual, tratamento de falhas e ausência de repetição automática de operações rejeitadas.

Verificado em 7 de outubro de 2026: build Debug para dispositivo iOS sem assinatura concluído; 55 testes XCTest passaram. A compilação foi feita de uma cópia temporária do projeto para evitar lentidão de leitura da pasta de trabalho.

## Limites desta etapa

- Apple/Google, cadastro, onboarding, assinaturas, compartilhamento, recursos sociais e funcionamento offline ainda precisam de implementação nativa.
- Criar substituições de exercícios, excluir exercícios e editar/remover medidas ainda não estão disponíveis nestas telas. Substituições já existentes são preservadas na retomada.
- O registro manual de uma refeição é separado do consumo de uma refeição planejada. Para vincular ao plano, use “Comi como planejado”; a revisão de “consumi diferente” vinculada ao slot ainda está pendente.
- A persistência dos cookies após fechar o processo e o problema de CSRF relatado no iPhone precisam de validação em aparelho. Testes simulados não comprovam a correção do app atual.
- O identificador de bundle nativo é separado (`ai.fittracker.app.native`), para instalar ao lado do app atual (`ai.fittracker.app`). A autenticação Apple/Google e assinaturas precisam das configurações próprias desse identificador antes de serem habilitadas.
- Nenhum arquivo, archive ou upload para TestFlight é produzido por esta etapa. O app Capacitor e seu número de build permanecem separados.

## Fluxos implementados

- Home: anéis nutricionais compactos, expansão de detalhes, ação destacada Adicionar refeição e resumo real do treino.
- Dieta: data, totais/metas, refeições registradas e botão fixo de registro. Foto/câmera, descrição com IA e busca na tabela local de alimentos (597 itens) levam à revisão antes de salvar. Valores desconhecidos não viram zero. Refeições planejadas têm seleção de alternativa, consumo em um toque, pular e correção com confirmação.
- Treino: sessão do dia, semana, início/retomada, rascunhos de séries, carga/repetições/aquecimento, conclusão de exercícios e finalização completa ou parcial com confirmação. Histórico paginado e detalhes reais.
- Planos: biblioteca paginada, geração de alternativas, consulta de tarefas assíncronas, revisão antes de ativar, edição de refeições e prescrição de exercícios; agenda semanal na ativação do treino.
- Progresso: resumo semanal, constância, séries temporais de medidas, conquistas e registro de oito medidas opcionais.
- Perfil: identidade, estado do perfil e logout. Conta e caches das abas são recriados quando muda o usuário.

Não há envio automático de foto, solicitação automática de IA ou gravação de exemplos fictícios. Escritas usam o CSRF da sessão atual. Operações com resultado incerto mantêm o mesmo conteúdo/chave para repetição explícita quando suportado pelo endpoint.

Próxima etapa: validar esses fluxos em aparelho e concluir os recursos restantes acima, antes de distribuir a versão nativa.


## Teste no aparelho

Em 7 de outubro de 2026, a versão de desenvolvimento foi assinada, instalada diretamente no iPhone 12 e aberta como **Fit Tracker Native** (`ai.fittracker.app.native`). O app atual continua separado. A instalação não usa TestFlight. Login por usuário/senha; os registros usam a conta e API reais. O arquivo Info.plist do pacote foi conferido para conter a URL HTTPS da API e a descrição de acesso à câmera.

## Auditoria de conta — 8 de outubro de 2026

A interface nativa agora inclui cadastro por senha com escolha explícita de IA,
edição de dados/objetivos, preferências de IA, consulta da assinatura e exclusão
com confirmação. Os formulários usam os contratos existentes; nenhum cadastro,
consentimento, exclusão ou mudança de perfil de produção foi executado na auditoria.
Peso e altura inalterados são omitidos do envio, evitando criar medições ao editar
apenas o objetivo. Compra/restauração ainda não está implementada.

A troca de login/logout cancela e aguarda transportes pendentes antes de trocar a
sessão. Logout remove cookies desse servidor também quando a confirmação remota
falha. A expiração autenticada por HTTP 401 volta à entrada; falhas 403 de CSRF não
provocam repetição automática. A reprodução real do problema original no iPhone
continua necessária: testes de transporte simulado não confirmam sua resolução.

### Bloqueios concretos de Apple e Google no identificador paralelo

- Apple: o backend valida e troca códigos usando um único `APPLE_CLIENT_ID`; a
  configuração documentada é `ai.fittracker.app`. O bundle `.native` requer
  habilitação Sign in with Apple e provisioning próprios, além de uma solução
  explícita para validar/trocar/revogar tokens dos dois identificadores sem
  interromper o app atual. Apenas aceitar outra audience não resolve a troca de
  código nem a revogação. Não alteramos o servidor nem seus segredos.
- Google: cadastrar um OAuth client iOS para `ai.fittracker.app.native`, obter
  seu client ID e URL scheme reverso, integrar o SDK GoogleSignIn e manter o
  server client ID que o backend verifica. O client iOS do app anterior não é
  evidência de autorização do identificador paralelo. Esses valores públicos não
  devem ser confundidos com credenciais privadas.
- Após configuração, implementar e verificar entrada/cancelamento/retorno ao app,
  primeiro acesso com `username_required` (409) e consentimento explícito, saída e
  reentrada. Os botões não estão anunciados como funcionais nesta etapa.

## Validação integrada em 8 de outubro de 2026

68 testes XCTest e 10 testes Python de progresso/treino passaram. Build Debug compilado, assinado, instalado e aberto no iPhone 12. Home, refeições pendentes, retorno do card de treino e navegação Perfil/assinatura observados no espelhamento. Escritas reais e logins Apple/Google não foram validados. Consulte `../docs/swiftui-experience-audit.md` para a matriz completa e pendências; a migração ainda não tem paridade total.

## Revisão de fluxos aprovada — 8 de outubro de 2026

Biblioteca de planos com cartões, detalhes expansíveis e início de qualquer dia. Geração em etapas com revisão, rotina/horários e estilos de preparo; seleção nativa de 1–7 refeições. Registro de refeição com câmera direta, galeria na captura e revisão após análise. Consumo planejado atualiza os totais imediatamente, descarta leituras anteriores à escrita e reconcilia o resultado com o servidor sem repetir a gravação. A versão foi compilada e assinada para o iPhone 12 e instalada localmente; 70 testes XCTest passaram. Câmera, chamadas de IA e gravações reais precisam ser testadas no aparelho pelo usuário.

Limite do servidor: `validate_diet_questionnaire` ainda aceita somente 3–5 refeições. A seleção de 1, 2, 6 ou 7 no app requer atualização do backend antes de gerar. Nenhum deploy do servidor ou upload ao TestFlight foi realizado nesta revisão.

## Execução de treino aprovada — 8 de outubro de 2026

Prévia do primeiro exercício na aba Treino, cache de demonstrações com antecipação limitada a dois downloads simultâneos e transição de cards com próximo exercício por baixo. Registro de uma série por vez retorna ao GIF com descanso; ao concluir um exercício com uma única série de trabalho preenchida, os valores são repetidos nas séries prescritas. Aquecimentos e múltiplas séries explícitas não são repetidos.

Conclusões de exercícios são persistidas antes do avanço e sincronizadas em ordem com chaves estáveis. Falhas mantêm os registros no aparelho e exigem conferência/repetição explícita. O resumo e os valores de compartilhamento vêm do servidor após finalização, com confetes respeitando Reduzir Movimento e card neon no terço inferior da imagem. Foto opcional permanece local até abrir o compartilhamento nativo.

72 testes XCTest passaram, incluindo repetição da série, preservação de aquecimentos e compatibilidade/persistência da fila. Build Debug assinado instalado localmente no iPhone 12. Gestos, câmera/galeria, exportação e gravações reais precisam ser validados pelo usuário no aparelho. Nenhum envio ao TestFlight.

## Carregamento e revisão do treino — 9 de outubro de 2026

Animação inicial nativa ligada à restauração real, sem tempo de espera artificial. Treino e resumo de progresso são antecipados em paralelo e compartilhados entre abas; o diário mantém sua leitura mesmo ao sair da aba. Cancelamentos de navegação não aparecem como falhas. Atualizações preservam o conteúdo existente, com erros reais disponíveis para repetição explícita.

A fila de conclusões continua persistente, sem aviso constante de sincronização. A última conclusão abre imediatamente a preparação do resumo, que só vira conclusão confirmada após a resposta do servidor. Voltar reabre o exercício com uma operação DELETE e preserva as séries como rascunho; a reabertura pendente também sobrevive à reinicialização. Alternativas mostram até três GIFs e reutilizam as opções já buscadas. A primeira busca ainda depende do servidor/WorkoutX. Compartilhamento usa logo completa oficial, borda neon reforçada e painel translúcido no terço inferior.

74 testes XCTest, 8 testes Python de progresso/reabertura e 18 testes JavaScript de sessão iOS passaram. Build Debug assinado para o iPhone 12. A checagem adicional de autenticação Python passou em 10 casos e encontrou uma falha preexistente de expectativas do catálogo de assinaturas, fora desta alteração. API publicada separadamente no commit `8550876`, apenas rota de reabertura e seus testes; alterações locais anteriores foram preservadas. Escritas reais e inspeção visual desta revisão no aparelho não foram realizadas; o espelhamento informou que o iPhone estava em uso. Sem envio ao TestFlight.

## Distribuição SwiftUI no TestFlight — 9 de outubro de 2026

Release usa `ai.fittracker.app` (mesmo app do TestFlight), versão 1.0 build 7. Debug mantém `ai.fittracker.app.native` para instalação paralela pelo Xcode. O esquema agora permite Archive em Release. Esta distribuição é apenas beta; entrada Apple/Google e compra/restauração de assinatura ainda não estão implementadas nativamente.

Refinamentos aprovados incluídos: ícones coloridos das refeições, seleção de alternativas em sheet com texto completo, gestos de registrar/pular, descrição opcional da foto, cache das seções de progresso, busca de exercícios/PRs, exclusão confirmada de atividades e edição definitiva de plano com proposta de IA e confirmação. API publicada no Render (deploy `dep-db485pbbc2fs73av5mvg` live), commit `96c2545`, saúde e rotas verificados, com sete testes passando; nenhuma chamada paga de IA foi feita para verificação.

Archive Release e upload do build 7 concluídos com sucesso. Processamento concluído: build 7 disponível no grupo interno Teste Fit Tracker. Builds HTML 2–6 expirados no App Store Connect; somente SwiftUI segue disponível. Instruções de teste salvas na compilação.
