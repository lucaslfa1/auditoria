# Configurações do Sistema

> Documento gerado automaticamente pelo DB Knowledge Agent.
> Banco: PostgreSQL (local) | Data: 2026-04-17 11:32


- **ia_prompt_global** = `REGRA CRÍTICA 1: IDENTIFICAÇÃO E SAUDAÇÃO (OBRIGATÓRIO):
O operador DEVE informar ao menos: Saudação (bom dia/boa tarde/boa noite) + Nome próprio.
Se NÃO houver saudação E NÃO houver nome, marque FAIL no critério de identificação.
Se houver saudação OU nome (apenas um deles), marque PASS (Atende). O sistema é benevolente para operadores que demonstram esforço de identificação.
Se houver ambos (saudação + nome), marque PASS.

REGRA CRÍTICA SEVERIDADE:
- Seja EQUILIBRADO na avaliação. A avaliação é ESTRITAMENTE BINÁRIA (pass ou fail). As opções partial e na foram ABOLIDAS.
- Na dúvida se o critério foi cumprido, considere o esforço do operador: se houve tentativa clara de cumprimento, prefira pass (Atende).
- Omissão completa ou erro grave que comprometa o procedimento = FAIL (Não atende).
- Procedimento feito de forma incompleta mas com a intenção correta e sem prejuízo à segurança = PASS (Atende).
- Se o critério for inaplicável (ex: solicitar vídeo em uma ligação onde não houve violação), marque PASS (Atende).`
  - Prompt global de regras da IA auditora
- **robo_habilitado** = `false`
  - Ativa ou desativa o robô de importação
- **rpa_senha** = `***`
  - Senha para acesso ao sistema
- **rpa_url_login** = `(vazio)`
  - URL de acesso ao sistema de telefonia
- **rpa_usuario** = `(vazio)`
  - Usuário para acesso ao sistema
- **tema_visual** = `corporativo`
  - Tema visual padrao da interface
