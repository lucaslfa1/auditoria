# 3. Segurança e Gestão de Dados

## 3.1. Autenticação e Autorização

A aplicação é governada por controles restritos de acesso para resguardar as avaliações operacionais da empresa.

- **Sessões Assinadas:** Autenticação baseada em cookie HMAC, sem exposição contínua de JWTs inseguros.
- **Criptografia:** Senhas são salvas usando algoritmos fortes (`bcrypt`).
- **RBAC (Role-Based Access Control):** Há separação estrita entre auditores básicos, supervisores da fila de avaliação e administradores globais (responsáveis por critérios).
- **Rate Limit de Autenticação:** Previne ataques de força bruta à infraestrutura local.

## 3.2. Privacidade e Rastreabilidade

- **Mídia Não Exposta Diretamente:** Todo arquivo operacional ingressado via endpoints (`/api/audit`) pode ser gerido no armazenamento local, mantendo-se restrito às contas logadas que participam da auditoria. 
- **Restrições de IA Corporativa:** Os serviços da Microsoft Azure (Azure OpenAI e Speech) são mantidos isolados e operam sem repasse de informações locais para os modelos base de treinamento abertos de IA.
- **Log de Eventos (Workflows):** O ciclo de auditoria guarda informações não apenas da transcrição, mas de quem aprovou, contestou e resolveu contestação da auditoria.

## 3.3. Configuração de Credenciais

Nenhuma chave sensível é comitada para o repositório. O projeto faz a leitura de um arquivo `.env` estrito que armazena endpoints e tokens privados da Azure (Whisper e GPT-4o), garantindo o controle técnico sobre o vazamento.
