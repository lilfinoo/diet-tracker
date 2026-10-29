# Área do personal e catálogo completo — 2026-10-29

O site permite ao personal cadastrar alunos, montar treinos em três etapas (plano, dias/exercícios e revisão), salvar rascunhos e enviar o treino ao aluno vinculado. O aluno aceita o convite no site e pode ativar o treino recebido no app existente. O acesso do personal exige aprovação administrativa e uma concessão profissional ativa; a gestão permanece limitada a cinco alunos.

O catálogo selecionável reúne 1.327 exercícios da API WorkoutX v1 e 73 exercícios locais. Os 1.327 nomes têm tradução pt-BR, os nomes originais permanecem como aliases de busca e os IDs numéricos/GIFs continuam compatíveis com o app atual. A geração automática mantém seu catálogo curado. O editor permite pesquisar, filtrar e carregar todos os resultados.

A importação de produção foi aditiva (111 → 1.327 linhas), sem apagar ou substituir os exercícios anteriores. A lista completa de IDs foi conferida com a API atual; fingerprint dos IDs ordenados: `e11e59c30a9fdda2fe7f6f3a5d81b273`.

## Uso

1. No admin, abrir Usuários e conceder acesso Personal à conta do treinador.
2. No site, acessar Perfil → Área profissional, cadastrar ou convidar o aluno e montar o treino.
3. O aluno aceita o link de vínculo no site; o treino publicado fica disponível na biblioteca do app para ativação.

## Validação

- Smoke offline: 1.400 chaves únicas selecionáveis/resolvidas; 1.327 traduções e aliases originais conferidos.
- Testes focados: 68 passaram — CRUD, permissões/consentimentos, convites, publicação, ativação pelo aluno, importação completa, substituições, tradução e fila de IA, incluindo recuperação de rascunho e revogação de acesso.
- JavaScript: 208 testes passaram, incluindo 15 testes do editor; sintaxe dos scripts conferida.
- Ruff, compilação Python e verificação de whitespace passaram.
- A suíte Python completa na base de publicação executou 678 testes: 648 passaram e 30 falharam antes das últimas correções. Os mesmos 29 testes antigos falharam também no commit-base limpo `9ad1350`; a única falha do teste novo foi corrigida e validada novamente. As falhas antigas incluem expectativas de produtos indisponíveis, cobrança com datas fixas e um uso de `zip(strict=True)` incompatível com o Python 3.9 local. A entrega não altera esses módulos para contornar os testes. Também foram corrigidos os casos alcançáveis da área reativada de fila profissional e revogação administrativa.

Preparado sobre a versão de produção `9ad1350`, isolando alterações locais de outras funcionalidades. Nenhuma atualização do binário do app é necessária para selecionar os exercícios, receber ou ativar os treinos publicados.
