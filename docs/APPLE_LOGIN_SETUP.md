# Login Apple no iPhone

O app usa AuthenticationServices do iOS; o servidor valida assinatura, issuer,
audience e nonce de uso único antes de autenticar. Contas são vinculadas pelo
subject Apple, nunca automaticamente por e-mail. O primeiro cadastro pede nome
de usuário e preferência de consentimento de IA, assim como o login Google.

## Configuração no servidor

- `APPLE_CLIENT_ID=ai.fittracker.app`
- `APPLE_TEAM_ID`: identificador da equipe paga Apple Developer.
- `APPLE_KEY_ID`: identificador da chave Sign in with Apple.
- `APPLE_PRIVATE_KEY`: conteúdo privado do arquivo `.p8` dessa chave.
- `APPLE_TOKEN_ENCRYPTION_KEY`: chave Fernet privada para proteger refresh tokens.

Guardar essas credenciais apenas no Render, fora do aplicativo e do Git.
Preservar a chave de criptografia: trocá-la sem recriptografar os tokens armazenados
impede revogar os vínculos existentes. A chave Apple é diferente da chave de IAP
usada pelo RevenueCat. Criar no Safari, habilitar Sign in with Apple e associar
`ai.fittracker.app` antes de baixar o arquivo.

## Teste no iPhone

Adicionar Sign in with Apple em Signing & Capabilities e manter assinatura
pela equipe paga. Sincronizar os arquivos Capacitor, aumentar o build e enviar
novo Archive ao TestFlight; o build 2 não contém o login Apple.

Validar: cancelar login sem entrar; cadastrar compartilhando e-mail; cadastrar
ocultando e-mail; sair e entrar novamente na mesma conta sem duplicar cadastro;
excluir a conta e verificar revogação do vínculo Apple. Confirmar que contas
Google e senha continuam funcionando. Só enviar à revisão após esses testes.
