# Constância — fonte alimentar e regras

A fonte canônica para o calendário de Evolução é `DietMealDailyState`.
`copilot/script.js` grava as ações atuais de alimentação em `/api/diet/days/...`,
usando `src/services/diet_daily.py`. Essa fonte conserva data local, resultado,
referência planejada e vínculo com o registro de consumo, incluindo correções.

A precedência é aplicada **por usuário e data**, em `src/services/consistency.py`:

1. Existindo qualquer `DietMealDailyState`, usar exclusivamente seus estados,
   inclusive quando todos estão pendentes. Não complementar com a fonte antiga.
2. Na ausência desses estados, usar `DietAdherenceDay/DietMealCheckIn`:
   `completed` → consumido conforme planejado, `substituted` → diferente,
   `skipped` → pulado. Dia `in_progress` indica acompanhamento pendente de conclusão.
3. Sem ambas as fontes, registros manuais `DietEntry` indicam acompanhamento
   sem classificação de adesão. Vários registros no mesmo dia contam um só dia.
4. Sem evidência, mostrar **sem informação**. Não projetar o plano atual sobre
   datas antigas nem fabricar pendências de refeições que não foram registradas.

As fontes nunca são somadas ou mescladas no mesmo dia. Nenhum dado é migrado,
apagado ou regravado. Os endpoints antigos continuam disponíveis.

Um dia alimentar acompanhado exige pelo menos um resultado informado (incluindo
pulado), ou um registro manual na regra de compatibilidade. Apenas pendente não
conta como dia acompanhado. A constância mede dias de acompanhamento, não número
de refeições, qualidade alimentar ou percentual de adesão. Estados diferentes
podem coexistir no dia e são apresentados no detalhe do calendário.

Treinos contam dias únicos com sessões concluídas que possuem exercícios
registrados, preservando `completed_local_date`; sessões antigas usam o fuso do
usuário. Excluir sessões remove sua contribuição na próxima consulta. Datas
futuras não entram no calendário, que cobre oito semanas até hoje.

Metas semanais conservam a regra existente de vigência por
`effective_week_start`: a primeira meta vale na semana de criação; alterações
valem na próxima semana. Antes da primeira vigência, a semana fica **sem meta**.
Com meta: atingir a quantidade = **cumprida**; semana atual abaixo dela = **em
andamento**; semana passada abaixo dela = **encerrada sem cumprir**. A UI não
usa mais “X de 8 semanas”, que incluía semanas sem meta e a semana ainda aberta.
