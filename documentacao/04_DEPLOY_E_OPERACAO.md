# 4. Deploy e Operação

## 4.1. Ambiente e Infraestrutura

A Auditoria nstech pode ser facilmente provisionada como um conjunto de contêineres e scripts locais de persistência.

**Requisitos Tecnológicos Mínimos:**
- Node.js (Ambiente Vite de Build)
- Python 3.11+
- Instância PostgreSQL

## 4.2. Procedimento de Bootstrap do Backend

A API central em FastAPI atua a partir do módulo raiz `main.py`.

```bash
cd backend
pip install -r requirements.txt

# O projeto exige bootstrap de autenticação em bancos vazios
export AUTH_USERS_FILE=./users_bootstrap.json
export SESSION_SECRET="sua-chave-segura-hmac"

python main.py
```

## 4.3. Instalação e Execução do Frontend

O shell principal é gerado pelo Vite/React.

```bash
npm install
npm run dev
# Ou npm run build para servir os estáticos consolidados em produção.
```

## 4.4. Monitoramento e Qualidade de Operação

- **Gestão de Falhas da IA:** Devido ao pipeline complexo e mutável da IA corporativa (APIs do Azure), o sistema já integra de modo resiliente fallbacks sequenciais: Fast Transcription -> GPT-4o -> Whisper, com telemetria do resultado calculada localmente (qualidade de Diarização).
- **Testes Automatizados:** Rotinas unitárias e de integração validadas em `npm run test` e separadamente (`test:backend`, `test:frontend`) para controle de Regressão Sistêmica.
