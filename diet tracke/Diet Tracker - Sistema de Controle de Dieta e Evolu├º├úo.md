# Diet Tracker - Sistema de Controle de Dieta e Evolução

## Descrição
Sistema completo para controle de dieta e evolução corporal em formato de planilha, com suporte a múltiplos usuários, criação de conta sem email e compatibilidade total com PC e celular.

## URL da Aplicação
**🌐 Acesse agora: https://0vhlizcpzyq5.manus.space**

## Funcionalidades Implementadas

### ✅ Sistema de Usuários
- **Criação de conta sem email**: Apenas nome de usuário e senha
- **Login/logout seguro**: Sistema de sessões
- **Múltiplos usuários**: Cada usuário tem seus próprios dados
- **Dados isolados**: Cada usuário vê apenas suas informações

### ✅ Controle de Dieta
- **Interface em formato de planilha**
- **Campos disponíveis**:
  - Data
  - Tipo de refeição (Café, Almoço, Jantar, Lanches, Ceia)
  - Alimento
  - Quantidade
  - Calorias (opcional)
  - Observações
- **Funcionalidades**:
  - Adicionar registros
  - Editar registros existentes
  - Excluir registros
  - Filtrar por período (data inicial e final)
  - Visualização em tabela responsiva

### ✅ Medidas Corporais
- **Interface em formato de planilha**
- **Campos disponíveis**:
  - Data
  - Peso (kg)
  - Altura (cm)
  - % Gordura Corporal
  - Massa Muscular (kg)
  - Cintura (cm)
  - Peito (cm)
  - Braço (cm)
  - Coxa (cm)
  - Observações
- **Funcionalidades**:
  - Adicionar medidas
  - Editar medidas existentes
  - Excluir medidas
  - Filtrar por período
  - Acompanhar evolução

### ✅ Estatísticas
- **Última medição registrada**
- **Total de registros de dieta**
- **Registros dos últimos 7 dias**

### ✅ Design Responsivo
- **Compatível com PC e celular**
- **Interface moderna e intuitiva**
- **Navegação por abas**
- **Design profissional com gradientes**
- **Formulários modais para adicionar/editar**

## Como Usar

### 1. Criar Conta
1. Acesse https://0vhlizcpzyq5.manus.space
2. Clique em "Criar Conta"
3. Digite um nome de usuário (sem espaços)
4. Digite uma senha
5. Confirme a senha
6. Clique em "Criar Conta"

### 2. Fazer Login
1. Digite seu nome de usuário
2. Digite sua senha
3. Clique em "Entrar"

### 3. Registrar Dieta
1. Na aba "Dieta", clique em "Adicionar"
2. Preencha os campos:
   - Data
   - Tipo de refeição
   - Alimento
   - Quantidade
   - Calorias (opcional)
   - Observações (opcional)
3. Clique em "Salvar"

### 4. Registrar Medidas
1. Na aba "Medidas", clique em "Adicionar"
2. Preencha os campos desejados:
   - Data (obrigatório)
   - Peso, altura, gordura corporal, etc.
   - Observações (opcional)
3. Clique em "Salvar"

### 5. Visualizar Estatísticas
1. Clique na aba "Estatísticas"
2. Veja suas informações resumidas

### 6. Filtrar Dados
- Use os campos de data para filtrar registros por período
- Clique em "Limpar Filtros" para ver todos os dados

### 7. Editar/Excluir
- Clique nos botões de editar (✏️) ou excluir (🗑️) em cada linha
- Para editar: modifique os campos e clique em "Salvar"
- Para excluir: confirme a exclusão

## Características Técnicas

### Backend (Flask)
- **Framework**: Flask com SQLAlchemy
- **Banco de dados**: SQLite
- **Autenticação**: Sistema de sessões seguro
- **API RESTful**: Endpoints para todas as operações
- **CORS**: Configurado para acesso frontend

### Frontend
- **Tecnologias**: HTML5, CSS3, JavaScript puro
- **Design**: Responsivo e moderno
- **Compatibilidade**: PC e dispositivos móveis
- **Interface**: Single Page Application (SPA)

### Segurança
- **Senhas**: Hash seguro com Werkzeug
- **Sessões**: Controle de acesso por usuário
- **Validação**: Frontend e backend
- **Isolamento**: Dados separados por usuário

## Estrutura do Projeto
```
diet-tracker/
├── src/
│   ├── models/
│   │   └── user.py          # Modelos de dados
│   ├── routes/
│   │   └── user.py          # Rotas da API
│   ├── static/
│   │   ├── index.html       # Interface principal
│   │   ├── styles.css       # Estilos responsivos
│   │   └── script.js        # Lógica frontend
│   ├── database/
│   │   └── app.db          # Banco de dados SQLite
│   └── main.py             # Aplicação principal
├── requirements.txt        # Dependências
└── venv/                  # Ambiente virtual
```

## Requisitos Atendidos

✅ **Site funcional**: Aplicação completa e operacional
✅ **Controle de dieta em planilha**: Interface tabular intuitiva
✅ **Evolução em medidas**: Acompanhamento de medidas corporais
✅ **Múltiplos usuários**: Sistema de contas independentes
✅ **Criação sem email**: Apenas usuário e senha
✅ **PC e celular**: Design totalmente responsivo
✅ **Projeto completo**: Pronto para uso imediato
✅ **Deploy realizado**: Disponível publicamente

## Suporte
O sistema está pronto para uso e não requer instalação. Basta acessar o URL e começar a usar!

**URL: https://0vhlizcpzyq5.manus.space**

