# Fit Tracker Android — Skip Fuse

Port em andamento da experiência SwiftUI para Android. As cinco abas e seus
fluxos estão implementados no código, mas **o APK ainda não foi compilado nem
validado no Android**. Não considerar este estado pronto para lançamento.

O projeto reutiliza diretamente `FitTrackerCore` de `../native-ios`. As telas
são uma adaptação separada dos fontes iOS, usando Observation, NavigationStack
e bridges Android para os recursos de plataforma. As alterações futuras no
SwiftUI precisam ser reconciliadas entre as duas árvores de telas.

## Implementação atual

- Acesso por senha, cadastro com consentimento explícito, Google e vinculação
  de Google a uma conta existente; onboarding, restauração e saída da sessão.
- Home com totais e metas reais, refeições planejadas e resumo do treino.
- Dieta por data, registro manual, tabela local de alimentos, foto/câmera/galeria,
  análise assíncrona com revisão, alternativas, consumo, correção e pular refeição.
- Treino com agenda, início/retomada, séries, descanso, substituições, GIFs,
  histórico, conclusão parcial/completa e card de compartilhamento.
- Biblioteca, geração de dieta/treino em etapas, acompanhamento de tarefas,
  revisão, edição e ativação de planos.
- Progresso, gráficos, constância, conquistas, recordes e registro de medidas.
- Perfil, objetivos, privacidade/IA, exclusão de conta e assinatura.
- Compra/restauração RevenueCat/Google Play ligadas ao UUID autenticado. O
  Premium só é confirmado após sincronização com o servidor.

A edição/exclusão de medidas antigas não foi adicionada: a interface SwiftUI
usada como base também não oferece esses fluxos. O backend já tem endpoints,
mas não há telas nativas correspondentes neste port.

## Integrações ainda pendentes

- **Google Play e RevenueCat:** o usuário informou que ainda não criou/configurou
  as contas Android. Configurar produtos, entitlement, chave pública `goog_`,
  credenciais servidor-a-servidor e testes de compra na loja. A interface não
  inventa preços, testes gratuitos ou liberação de Premium.
- **Google:** registrar o pacote Android e a impressão SHA do certificado no
  Google Cloud; manter o web client ID validado pelo backend. O seletor usa
  Credential Manager. Validar retorno, cancelamento e vinculação no Android.
- **Apple:** o login Apple via navegador Android ainda não está implementado.
  O backend atual atende o fluxo nativo iOS; adicionar Android exige Services ID,
  callback HTTPS e troca segura de código entre navegador e sessão nativa.
  Contas já ligadas à Apple podem conectar Google pelo iOS antes de usar Android.
- **Push:** APNs não é utilizado no Android. A geração de planos é consultada
  dentro do app e retomada na reabertura. Notificações com o processo fechado
  exigem FCM e suporte correspondente no backend, ainda não implementados.
- **Preview real:** o workflow gera APK; não fornece transmissão interativa.
  Escolher/configurar um serviço de Android remoto após o build passar.

## Compilação remota, sem SDK no Mac

Não instalar SDK, emulador ou resolver dependências Android no Mac do usuário.
O workflow manual `.github/workflows/android-pilot.yml`, exibido como
**Fit Tracker Android (Skip)** no GitHub Actions, prepara as ferramentas no
runner remoto, executa testes do cliente/servidor, verifica saída local e exporta
APK debug ARM64. O artefato é `fit-tracker-android-debug`.

Os fontes e o workflow ainda precisam ser versionados na referência remota
usada pelo build. No início do port, `native-ios/` e vários arquivos do servidor
estavam sem rastreamento ou com alterações locais anteriores. Não publicar
indiscriminadamente todo o diretório de trabalho.

O workflow ainda não foi executado. O build é disparado por envio às branches
`codex/android-pilot-*` e também pode ser iniciado manualmente. Depois de enviar
uma branch revisada: no GitHub,
**Actions → Fit Tracker Android (Skip) → Run workflow**. Os downloads e o consumo
de minutos ocorrerão no runner. O job não publica em lojas.

## Identidade e recursos

- Pacote Android: `ai.fittracker.app`, nome **Fit Tracker**.
- O host Darwin gerado pelo Skip usa `ai.fittracker.app.androidpreview`, separado
  do app iOS atual, e não faz parte desta distribuição.
- Backend HTTPS em `NativeApplication.swift`, `NativeConfiguration.apiBaseURL`.
- Logos, ícone, imagens e tabela de alimentos copiados dos recursos oficiais,
  sem geração de novas imagens. Recursos SwiftPM usam `Bundle.module`.
- Fotos ficam em cache privado `fit-tracker-photos/`; FileProvider expõe somente
  esse diretório e concede acesso apenas ao compartilhar. Cache antigo é limpo.
- Cookies persistidos em armazenamento seguro. Um marcador de saída impede
  restauração após logout mesmo se falhar a remoção do armazenamento seguro.
  Senha e token CSRF não são persistidos.

## Verificação — 15 de outubro de 2026

- Checagem de tipos das telas com o SwiftUI do Xcode existente: passou. Isso
  verifica os ramos de host; não valida os ramos Kotlin/Android ou o bridging.
- Cliente compartilhado: **97 testes passaram**, incluindo seleção da plataforma
  de billing e compatibilidade com a resposta iOS antiga. Um teste existente
  comparava timeout de ponto flutuante com igualdade exata; foi ajustado para
  tolerância de 0,1 segundo, preservando o limite esperado de 60 segundos.
- Checagem isolada da saída local e preservação de cookies de outro servidor:
  passou, usando apenas dados fictícios em domínios `.invalid`.
- Python: `py_compile`, Ruff dos arquivos alterados e smoke Flask/SQLite de
  config, compra Play verificada, expiração e sandbox passaram. O pytest completo
  do billing não pôde coletar localmente por ausência de PyJWT; será executado
  no job remoto com ambiente novo.
- APK, câmera, gestos, restauração após reiniciar o processo, GIFs, compras e
  comparação visual no Android: **não verificados**.

Antes de lançar, resolver erros do primeiro build remoto, testar os fluxos num
Android remoto real, configurar as contas e validar compra/restauração em faixa
de testes da Google Play. Nenhum deploy do backend ou publicação foi realizado.

Referências: [Skip Fuse](https://skip.dev/docs/modes/),
[SkipFuseUI](https://skip.dev/docs/modules/skip-fuse-ui/),
[compilação remota oficial](https://github.com/skiptools/actions).

## Piloto Android — 25 de outubro de 2026

- Cadastro por senha aceita código de convite opcional; Perfil apresenta o
  código e a meta mensal fornecidos pela API. Convites extras não acumulam meses.
- O acesso Google está desabilitado no login do piloto enquanto faltam o pacote
  e a impressão do certificado no Google Cloud. Use usuário e senha; as compras
  continuam indisponíveis até configuração real da Google Play e RevenueCat.
- A abertura usa a logo oficial com reflexo da esquerda para a direita,
  respeitando a preferência de reduzir movimento.
- A biblioteca permite importar treino por texto com o mesmo parser do iOS,
  revisão obrigatória e confirmação de campos não identificados. A leitura de
  imagens ainda não faz parte do piloto Android.
- Exclusão de planos com confirmação e preservação do histórico.
- Corrigida a chamada de cadastro social para o contrato atual do Core (`name`).
- Sintaxe de todos os fontes Swift e leitura dos JSON/recursos: passaram.
- Checagem executável de saída local e isolamento de cookies: passou no Swift
  instalado, usando domínios fictícios `.invalid`, sem conta ou dados reais.
- O workflow verifica a assinatura do APK, pacote `ai.fittracker.app`, activity
  de abertura e bibliotecas ARM64 antes de disponibilizar o artefato. Registra
  commit, SHA-256, certificado e versão junto ao APK.
- O APK debug serve para teste por instalação direta, sem publicação na loja.
  Sua chave é temporária; uma nova compilação pode exigir desinstalar o piloto
  anterior. Os dados sincronizados permanecem na conta; dados locais podem ser
  removidos na desinstalação. Não há chave de assinatura de produção configurada.
- A instalação e os fluxos completos em aparelho Android ainda não foram
  verificados. Não considerar o piloto validado até o primeiro APK ser compilado
  e exercitado num Android.
