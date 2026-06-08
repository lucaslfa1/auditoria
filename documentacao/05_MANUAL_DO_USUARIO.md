# 5. Manual do Usuário e API

## 5.1. Fluxos da Interface Principal

1. **Triagem de Lote (Classifier):** Acesso a `Classifier/Triagem` para o upload inicial, possibilitando separar e qualificar os alertas automaticamente antes do auditor humano atuar.
2. **Submissão de Auditoria:** Pelo menu `Upload`, os auditores submetem áudios ou documentos (PDF). O sistema exibe métricas em tempo real enquanto carrega a inferência.
3. **Análise de Resultados e Fila:** Após o cálculo dos critérios, o auditor entra na aba de Resultados e aprova o veredito ou adiciona apontamentos/revisões na transcrição (`Re-Auditoria`).
4. **Contestação (Supervisores):** As partes lesadas/supervisores acompanham filas, abrem disputa em uma qualificação de critério indevida, e um processo de reconciliação de score é guiado sistemicamente (`Review`).
5. **Relatórios e Exportações:** Utilizar abas de exportação de `.xlsx` ou DOCX para o balanço tático no final do ciclo do negócio.

## 5.2. Especificação da API Rest (Principais Endpoints)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/auth/login` | POST | Efetua login e recebe o cookie assinado. |
| `/api/auth/me` | GET | Informações e _roles_ do usuário ativo. |
| `/api/auth/logout` | POST | Destrói a sessão atual. |
| `/api/audit` | POST | Envia o arquivo e aciona pipeline completo de transcrição e IA. |
| `/api/audit/reevaluate` | POST | Re-avalia o pipeline após um humano editar as transcrições originais. |
| `/api/classify` | POST | Executa triagem em lote. |
| `/api/revisao/*` | GET/POST | Controle dos tickets de contestação de auditorias. |
| `/api/export/*` | GET/POST | Geração programática de planilhas e relatórios gerenciais da base de auditoria. |

*Para documentações estendidas de tipagem Pydantic dos payloads, consultar o schema dinâmico Swagger disponível nativamente no FastAPI raiz.*
