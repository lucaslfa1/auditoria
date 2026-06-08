# Guia - Execucao Local do Sync Huawei AICC

**Contexto:** Enquanto a Teledata nao whitelistar um IP fixo para ambiente
de nuvem (GCloud/Azure), o sync Huawei roda numa maquina da rede NSTECH
(IP ja whitelisted). O agendamento eh feito pelo **Windows Task
Scheduler**, cronometrado - nao precisa de servidor 24/7.

Portas de saida futuras ja estao preparadas no codigo:
- `HUAWEI_AUTH_MODE=proxy` (padrao) delega assinatura ao `c2Authorization.php`.
- `HUAWEI_AUTH_MODE=direct` assina localmente com HMAC-SHA256.
- Quando formos para GCloud/Azure, so precisamos trocar o IP de saida
  (Cloud NAT estatico ou Azure NAT Gateway) e avisar a Teledata.

---

## 1. Pre-requisitos na maquina NSTECH

- Windows 10/11 com acesso a rede corporativa (ou VPN da NSTECH ativa).
- Python 3.11+ instalado.
- Repositorio clonado em, por exemplo, `C:\Users\<voce>\projetos\auditoria`.
- Venv do backend criado e dependencias instaladas:

```powershell
cd C:\Users\<voce>\projetos\auditoria
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
```

## 2. Configurar `backend\.env`

Editar `backend\.env` (copiar de `backend\.env.example` se nao existe)
e preencher:

```env
# Banco (producao - Supabase do time)
DATABASE_URL=postgresql://...

# Huawei AICC - pegar da collection Postman ou do painel Telefonia
HUAWEI_CMS_URL=https://brazilsaas.aicccloud.com:28443
HUAWEI_FS_URL=https://brazilsaas.aicccloud.com:28443
HUAWEI_CC_ID=1
HUAWEI_VDN=25
HUAWEI_AK=<app_key_c2 da collection>
HUAWEI_SK=<app_secret_c2 da collection>
HUAWEI_APP_KEY=

# Assinatura via proxy Teledata (recomendado)
HUAWEI_AUTH_MODE=proxy
HUAWEI_PROXY_URL=https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php

# LIGAR o sync de verdade
ENABLE_HUAWEI_SYNC=true

# Janela retroativa em horas (quanto pra tras buscar em cada execucao)
HUAWEI_SYNC_HORAS_RETROATIVAS=1
```

> **Importante:** Opcionalmente, essas credenciais tambem podem ser
> salvas no banco pela tela `Telefonia -> Configuracoes`. O `.env` tem
> prioridade em dev local.

## 3. Teste manual pelo terminal

Antes de agendar, valide que tudo funciona executando de forma manual:

```powershell
cd C:\Users\<voce>\projetos\auditoria
scripts\huawei_sync.bat --horas 2
```

Saida esperada (exemplo com credenciais OK):

```json
{
  "status": "ok",
  "operadores_considerados": 42,
  "baixadas": 3,
  "enfileiradas": 3,
  "duplicadas": 0,
  "erros": []
}
```

O log completo fica em `backend\logs\huawei_sync\<YYYYMMDD_HHMMSS>.log`.

Casos comuns de erro:

| Mensagem | Causa provavel |
|---|---|
| `status=disabled` | `ENABLE_HUAWEI_SYNC` ainda nao esta `true`. |
| `status=missing_credentials` | AK/SK/CCID/VDN ausente no .env. |
| `Huawei proxy HTTP 403` | A maquina nao esta na rede NSTECH (IP fora do whitelist). |
| `Huawei CMS retornou codigo 9999*` | Credenciais invalidas. Conferir `app_key_c2`/`app_secret_c2`. |

## 4. Agendar no Windows Task Scheduler

### 4.1 Via interface grafica

1. Abrir **Task Scheduler** (`taskschd.msc`).
2. Action -> **Create Task...** (nao "Create Basic Task").
3. Aba **General**:
   - Name: `Huawei AICC Sync`
   - Description: `Baixa ligacoes Huawei e enfileira na triagem`
   - Security options: marcar **"Run whether user is logged on or not"**.
   - Marcar **"Run with highest privileges"** se houver conflito com
     permissao no venv.
4. Aba **Triggers** -> **New**:
   - Opcao 1 - Rodar uma vez de madrugada: `Daily`, `03:00:00`.
   - Opcao 2 - Rodar a cada hora na jornada: `Daily`, repeat every `1 hour`,
     duration `12 hours`, a partir das `08:00`.
5. Aba **Actions** -> **New**:
   - Action: `Start a program`.
   - Program/script:
     `C:\Users\<voce>\projetos\auditoria\scripts\huawei_sync.bat`
   - Add arguments: `--horas 2` (deixa uma folga caso a execucao anterior
     tenha falhado).
   - Start in:
     `C:\Users\<voce>\projetos\auditoria`
6. Aba **Conditions**:
   - Desmarcar `Start the task only if the computer is on AC power` se
     for notebook.
7. Aba **Settings**:
   - Marcar `Allow task to be run on demand`.
   - Marcar `If the task fails, restart every: 15 minutes, up to 2 times`.
8. OK. Vai pedir a senha do usuario para rodar sem login.

### 4.2 Via linha de comando (atalho)

```powershell
schtasks /Create `
  /TN "Huawei AICC Sync" `
  /TR "C:\Users\<voce>\projetos\auditoria\scripts\huawei_sync.bat --horas 2" `
  /SC DAILY /ST 03:00 `
  /RU <dominio>\<usuario> /RP `
  /RL HIGHEST /F
```

Testar manualmente a execucao:

```powershell
schtasks /Run /TN "Huawei AICC Sync"
schtasks /Query /TN "Huawei AICC Sync" /V /FO LIST
```

## 5. Como saber se rodou

- **Logs por execucao:** `backend\logs\huawei_sync\*.log`.
- **Historico de execucoes:** Task Scheduler -> `Huawei AICC Sync` -> aba
  **History** (pode precisar habilitar em `Action -> Enable All Tasks
  History`).
- **Idempotencia:** `call_id` ja sincronizado vai para a tabela
  `huawei_sync_logs` e nao eh reprocessado. Rodar varias vezes seguidas
  nao gera duplicata.
- **Cota mensal:** `MAX_INTERACOES_POR_OPERADOR = 2` - o sync para
  sozinho quando o operador ja tem 2 auditorias no mes.

## 6. Desligar temporariamente

Se precisar pausar sem desabilitar a task:

- Edit `backend\.env` -> `ENABLE_HUAWEI_SYNC=false`.
- Nas proximas execucoes, o script loga o aviso e encerra sem bater na
  API. Nao eh preciso mexer no Task Scheduler.

Para desabilitar de vez:

```powershell
schtasks /Change /TN "Huawei AICC Sync" /DISABLE
```

## 7. Caminho para migrar para GCloud/Azure no futuro

Quando quisermos sair da maquina local:

1. **GCloud:** provisionar `Cloud NAT` com IP estatico no projeto.
   Apontar o Cloud Run para sair por esse IP via VPC Connector. Pedir
   pra Teledata whitelistar o IP. Nada muda no codigo - basta rodar o
   mesmo `run_huawei_sync.py` via Cloud Scheduler + Cloud Run Jobs.
2. **Azure:** provisionar NAT Gateway com IP publico estatico.
   Hospedar num Azure Function ou Container App com VNet integration
   saindo por esse NAT. Mesma logica: so o IP de saida muda.
3. **Hibrido temporario:** manter a task local rodando enquanto a
   migracao de nuvem eh decidida - as duas formas convivem porque a
   idempotencia em `huawei_sync_logs` evita trabalho duplicado.
