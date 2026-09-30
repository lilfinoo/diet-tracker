# Polimento do uso diário — diagnóstico e validação

## Antes das alterações (29/09/2026)

Instância local em `127.0.0.1:8081`, banco SQLite descartável criado por migrações, conta fictícia, navegador integrado em 390 × 844. Latência de 2 s injetada no servidor de teste para resultados de refeições e sessão. Nenhum dado real alterado.

- Refeição arrastada para a esquerda: o card volta ao lugar e só desabilita o menu enquanto aguarda a resposta. Nenhum texto indica salvamento; os macros só mudam após confirmação. Causa: `endDietDailySwipe` limpa o deslocamento; `setDietDailyOutcome` renderiza o mesmo card antes de aguardar o PUT. Preservar confirmação, idempotência do endpoint e desfazer.
- Cards: o título do café aparece truncado em 390 px; metadado redundante “Opção 1 de 3 · Dia 1”; instrução de gesto com fonte muito pequena; ausência dos macros previstos no card.
- Iniciar treino cria a sessão e abre o player. A leitura do caminho revela `viewWorkoutPlan()` antes de iniciar; continuar usa `open-plan`. Remover esse caminho intermediário, preservando abrir plano por ação própria.
- Player: imagem permanece em “Carregando demonstração…” por mais de 20 s no teste. O fallback carregado tem identidade diferente de `data-media-url` e seu evento de load é rejeitado. O cache frio do provedor ainda pode demorar: downloads serializados, intervalo padrão de 3 s e timeout de 15 s. O cache local/banco já persiste GIFs; não há motivo medido para converter todo o acervo.
- Troca por “Supino na máquina” foi aplicada na sessão. Botão “Trocar exercício” é pequeno visualmente (fonte móvel 0,55 rem) e disputa espaço com a prescrição. A seleção de alternativas não reserva categoria de máquinas nem exclui elásticos quando existem alternativas preferidas.
- Aviso flutuante de sucesso ao iniciar o treino cobre o nome do exercício e repete o status inline. Esse ruído, textos redundantes, alvos discretos e estados de carregamento indefinidos são os elementos concretos a corrigir na sensação de app. A navegação principal já é funcional; não foi identificado feed social na home para remover.

## Plano e critérios

1. Feedback de salvamento imediatamente após o gesto, com animação curta e card recuperável em falha; confirmar totais só pelo servidor. Verificar atraso, falha, repetição, desfazer e gesto vertical.
2. Abrir execução diretamente em iniciar/continuar, sem overview; corrigir fallback e limitar pré-carga. Verificar sessão certa, erro/repetição, imagem e próximos exercícios.
3. Dar legibilidade à troca e priorizar categorias sem relaxar compatibilidade. Verificar filtros de equipamento/movimento e fallback para elásticos.
4. Refinar cards e feedback; conferir 375/390 px, console e verificações Python/JS do projeto.

## Resultados após alterações (30/09/2026)

- Refeição: o card exibe "Salvando refeição…" imediatamente após o gesto, mantém os totais condicionados à confirmação do servidor e permite nova tentativa em falha. Gesto repetido não duplica registro; desfazer permanece disponível após a confirmação. O card passou a mostrar macros e títulos legíveis, com animação curta e respeito a movimento reduzido.
- Treino: iniciar ou continuar da Home abre a execução com estado de carregamento, sem mostrar o plano antes; o plano continua acessível por sua ação própria. O botão de troca ganhou alvo móvel de pelo menos 44 px. As alternativas compatíveis priorizam pesos livres, máquinas e peso corporal, deixando elásticos como último recurso.
- Mídia: a imagem atual tem prioridade alta e apenas a próxima é antecipada após a atual carregar; a antecipação é desativada com economia de dados ou 2G. Fallback carregado é reconhecido e uma falha final oferece tentativa novamente. Respostas 503 transitórias usam `no-store`.
- O servidor deixou de ler ou gravar GIFs no R2. Usa arquivo local e banco de dados; um GIF novo vem do WorkoutX e é persistido no banco. O R2 permanece apenas para avatares. O deploy `bb2b8e8` ficou ativo em 30/09; uma consulta pública ao GIF `workoutx:0155` retornou HTTP 200, `image/gif` e cache de um ano em cerca de 3,4 s (medição única, não comparável à anterior).
- Verificações: 160 testes JavaScript passaram; Ruff e compilação Python passaram. A suíte Python completa teve 309 aprovações e duas falhas em testes de cobrança que fixam vencimento em 25/09/2026, data anterior à execução em 30/09/2026. Esses testes não exercitam as mudanças deste polimento.

Limitações: a nova interface móvel ainda não teve uma passagem visual completa após estas últimas alterações. O teste local anterior usou 390 × 844; o navegador integrado bloqueou acesso posterior ao servidor local. GIFs inéditos continuam dependendo da disponibilidade e dos limites de download do WorkoutX.
