# Procedimento de Extração e Automação de Ligações

Este documento descreve o fluxo de trabalho desde a coleta dos áudios no sistema de telefonia até o processamento automático pelo sistema de auditoria com Inteligência Artificial.

## 1. Coleta de Dados (Sistema de Telefonia)

A extração das gravações das ligações é feita a partir do painel de controle do sistema de telefonia (ex: Huawei / Weon). O processo requer o preenchimento correto dos filtros na tela **"Contato"** para isolar as amostras a serem auditadas.

Existem duas formas principais de realizar os filtros de busca:

### Busca por Número (Telefone Alvo)
Utilizado para rastrear ocorrências vinculadas a um número específico (ex: placa do veículo, número do motorista).
*   **Período:** Selecionar o intervalo de tempo desejado (ex: `1 dia`).
*   **Número Manipulado:** Inserir o número de telefone a ser investigado.
*   **Ação:** Clicar em **Pesquisar**.

### Busca Avançada por Motivo / Atendimento
Utilizado para amostragens diárias baseadas no tipo de evento logístico e no operador.
*   **Período:** Selecionar `1 dia` (ou outro intervalo pertinente).
*   **Tipo de Chamada:** Selecionar o formato (ex: Receptivo, Ativo).
*   **Tipo de Mídia:** Geralmente "Voz".
*   **Definir o Motivo da Chamada:** Filtrar pela classificação dada na URA ou pelo operador original (ex: Desvio de Rota, Parada Indevida).
*   **ID do Funcionário:** Inserir a matrícula/ID do operador para auditar chamadas específicas de um colaborador (Cruzamento com as matrículas da planilha `01 - LISTAGEM.xlsx`).
*   **Ação:** Clicar em **Pesquisar**.

### Exportação dos Áudios
Após a pesquisa, selecione as ligações listadas e realize o download dos arquivos de áudio em lote.

---

## 2. Organização dos Arquivos Locais

Para que o script de automação possa classificar corretamente o contexto da auditoria (Setor e Motivo), os áudios extraídos devem ser renomeados e colocados nas pastas corretas dentro do diretório `Ligações/` na raiz do projeto.

### Estrutura de Pastas Esperada
Crie subpastas no diretório `Ligações/` seguindo as categorias de negócio, por exemplo:
*   `Ligações/CADASTRO/`
*   `Ligações/LOGÍSTICA/`
*   `Ligações/MONDELEZ/`
*   `Ligações/UNILEVER/`

### Convenção de Nomes dos Arquivos
O nome do arquivo de áudio deve conter palavras-chave para que o sistema infira automaticamente o "Alerta/Critério" (conforme definido no script de importação).
Exemplos de nomenclaturas de arquivos aceitas:
*   `temperatura_motorista_123.wav` (Infera alerta 4.4.5)
*   `atraso_cliente_abc.mp3` (Infera alerta 4.4.8)
*   `antecedente_jose.ogg` (Infera alerta 4.2.1)

---

## 3. Importação para o Banco de Dados

Com os áudios devidamente organizados, o processo de leitura e indexação no banco de dados local (SQLite) é feito através de um script automatizado.

Abra o terminal (PowerShell ou CMD) na raiz do projeto e execute:
```powershell
python backend/scripts/importar_ligacoes_auditadas.py
```
*(Se estiver utilizando um ambiente virtual, certifique-se de executar `backend/.venv/Scripts/python.exe`)*

### O que o script faz:
1. Varre todas as pastas e arquivos dentro do diretório `Ligações/`.
2. Infere o **Grupo/Setor** pelo nome da pasta (ex: LOGÍSTICA).
3. Infere o **Alerta de Referência** através de palavras-chave no nome do arquivo (ex: "atraso", "desvio", "temperatura").
4. Calcula o Hash SHA-256 do arquivo para evitar duplicações futuras.
5. Salva todas as referências no banco de dados (`backend/database.db` na tabela `ligacoes_auditadas`).

---

## 4. Auditoria via Sistema (Inteligência Artificial)

Uma vez importadas para o banco de dados, as ligações estão prontas para aparecerem na interface web (Dashboard).
A partir desse ponto, o Backend processara as ligacoes localizadas utilizando o provedor de IA configurado para transcrever o audio, julgar os criterios (baseado nos prompts localizados em `audit-prompt/`) e calcular as penalidades (deflatores) definidos pelas planilhas gerenciais.
