"""Modelos Pydantic compartilhados da API de auditoria.

Papel no fluxo: estes schemas são o contrato entre o backend e o frontend
(React) para o ciclo de avaliação de uma ligação/documento — desde o alerta
classificado (`AuditAlert` + `AuditCriterion`, carregados do catálogo oficial
no banco) até o resultado final (`AuditResult`), que é persistido em
"Arquivos Salvos" e depois promovido para aprovação/fechamento.

Dependências: apenas Pydantic; nenhum acesso a banco ou API paga acontece
aqui. Os payloads de reavaliação (`ReevaluateRequest` /
`RegenerateSummaryRequest`) são entradas de endpoints que DISPARAM chamadas
pagas ao Azure OpenAI (GPT-4o) — o custo está nos serviços, não no schema.

Atenção: o frontend e o BI consomem estes nomes de campo (inclusive os em
camelCase, ex.: `criterionId`, `maxPossibleScore`). Renomear campo aqui
quebra o contrato com o front/fechamento.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class AuditCriterion(BaseModel):
    """Um critério do catálogo oficial (tabela `audit_criteria` no Neon)."""

    id: str  # Identificador único do critério (ex.: 'saudacao', 'senha'). Usado nas regras de zeragem.
    chave: Optional[str] = None  # Chave alternativa/legada usada por importadores; pode espelhar `id`.
    label: Optional[str] = "Critério"  # Nome exibido na UI (legível para o auditor).
    weight: float  # Peso (pontos) do critério no score; soma dos pesos = maxPossibleScore.
    deflator: Optional[float] = None  # Penalidade aplicada quando falha (se diferente do peso); None = perde o peso cheio.
    evaluation_type: Optional[Literal['auto', 'manual']] = 'auto'  # 'auto' = IA avalia; 'manual' = auditor humano marca na UI.
    description: Optional[str] = None  # Texto-guia do critério enviado no prompt da IA (o que verificar na ligação).

class AuditAlert(BaseModel):
    """Alerta/motivo da ligação + conjunto de critérios aplicáveis.

    Definido pela classificação (GPT) e resolvido contra o catálogo do banco
    via `canonicalize_alert_id` antes de chegar aqui.
    """

    id: str  # Id canônico do alerta (ex.: 'parada_indevida_efetivada'). Carrega a direção no sufixo.
    label: Optional[str] = "Alerta"  # Nome exibido na UI.
    context: Optional[str] = "Geral"  # Agrupador/contexto do alerta (setor ou tema) para exibição.
    expected_direction: Optional[Literal['efetivada', 'receptiva']] = None  # Direção esperada da ligação (guardrail EFETUADA x RECEPTIVA, v1.3.73). None = sem checagem.
    criteria: List[AuditCriterion]  # Critérios oficiais que a IA deve avaliar para este alerta. Vazio => erro (sem critério oficial não se audita).

class AuditResultDetail(BaseModel):
    """Resultado da avaliação de UM critério dentro de uma auditoria."""

    criterionId: str  # Id do critério avaliado (casa com AuditCriterion.id). camelCase: contrato com o front.
    label: str  # Nome do critério na época da avaliação (snapshot — não buscar de novo no banco).
    status: Literal['pass', 'fail', 'pending_manual']  # pass/fail = decidido (IA ou humano); pending_manual = aguarda auditor na UI.
    weight: float  # Peso do critério no momento da avaliação (snapshot).
    deflator: Optional[float] = None  # Penalidade aplicada em caso de fail (snapshot do catálogo).
    obtainedScore: float  # Pontos efetivamente obtidos neste critério (0 quando fail/zeragem).
    comment: str  # Justificativa da IA (ou do auditor) para o status — exibida na UI e no fechamento.
    timestamp: Optional[str] = None  # Momento (mm:ss ou ISO) em que a evidência ocorre na ligação, quando a IA aponta.
    evidence_text: Optional[str] = None  # Trecho literal da transcrição usado como evidência do pass/fail.
    evidence_validation: Optional[dict] = None  # Resultado da validação automática da evidência (ex.: evidência fraca → retry). Estrutura livre, só p/ diagnóstico.

class TranscriptionSegment(BaseModel):
    """Um segmento da transcrição diarizada (uma fala de um locutor)."""

    start: str  # Início do segmento (timestamp em string, formato vindo do provedor de STT).
    end: str  # Fim do segmento.
    text: str  # Texto da fala, já com prefixo de locutor (ex.: 'Operador: ...') e correções fonéticas aplicadas.

class ReevaluateRequest(BaseModel):
    """Payload de reavaliação: reusa transcrição existente e chama o GPT-4o de novo.

    CUSTO: o endpoint que recebe este payload faz 1+ chamadas pagas ao Azure
    OpenAI (avaliação completa), mas NÃO re-transcreve (sem custo de Speech).
    """

    transcription: List[TranscriptionSegment] = Field(..., max_length=5000)  # Transcrição já existente (limite anti-abuso de 5000 segmentos).
    alert: AuditAlert  # Alerta + critérios a aplicar na reavaliação (pode ser um alerta diferente do original).
    operator_name: Optional[str] = Field(None, max_length=200)  # Nome do operador auditado (entra no prompt para a IA identificar o locutor).
    operator_id: Optional[str] = Field(None, max_length=100)  # Matrícula/id do operador (rastreio, cota 2/mês).
    sector_id: Optional[str] = Field(None, max_length=50)  # Setor interno (ex.: 'transferencia', 'uti', 'fenix') — define regras/prompt.
    source_type: Optional[Literal['audio', 'pdf']] = 'audio'  # Origem: ligação transcrita ou documento (chat Service Cloud em PDF).
    audio_quality: Optional[dict] = None  # Métricas do QualityAnalyzer (score 0-1, volume, silêncio...) repassadas para contexto/penalidades.
    input_hash: Optional[str] = Field(None, max_length=128)  # Hash do insumo original (dedup/idempotência — mesma ligação não vira 2 registros).

class RegenerateSummaryRequest(BaseModel):
    """Payload para regenerar SÓ o resumo/feedback da auditoria.

    CUSTO: 1 chamada paga ao Azure OpenAI (mais barata que reavaliação
    completa — não reavalia critérios, só reescreve o texto do resumo).
    """

    transcription: List[TranscriptionSegment] = Field(..., max_length=5000)  # Transcrição de referência para o resumo.
    alert: AuditAlert  # Alerta da auditoria (dá contexto ao resumo).
    operator_name: Optional[str] = Field(None, max_length=200)  # Nome do operador citado no resumo.
    details: List[AuditResultDetail] = Field(..., max_length=50)  # Resultados por critério JÁ decididos (inclusive ajustes manuais) — o resumo deve refletir isto, não reavaliar.

class AuditResult(BaseModel):
    """Resultado completo de uma auditoria — objeto que o front salva em
    "Arquivos Salvos" e que alimenta aprovação e fechamento (BI).

    Cuidado: campos camelCase e defaults fazem parte do contrato com o
    frontend; não renomear nem mudar default sem alinhar com o front/BI.
    """

    score: float  # Pontuação final obtida (já com zeragens/deflatores aplicados).
    maxPossibleScore: float  # Pontuação máxima possível (soma dos pesos dos critérios do alerta).
    summary: str  # Resumo objetivo da ligação gerado pela IA (exibido na UI e no fechamento).
    ai_feedback: Optional[str] = None  # Feedback construtivo da IA para o operador (separado do resumo factual).
    details: List[AuditResultDetail]  # Resultado por critério.
    transcription: List[TranscriptionSegment] = []  # Transcrição diarizada completa (vazia em fluxos só-documento até o parse).
    operatorId: Optional[str] = ""  # Matrícula/id do operador auditado ('' quando não identificado).
    operatorName: Optional[str] = "Não identificado"  # Nome do operador; default sinaliza falha de identificação (triagem manual resolve).
    timestamp: Optional[str] = None  # Quando a auditoria foi gerada (ISO).
    input_hash: Optional[str] = None  # Hash do insumo (áudio/PDF) — chave de dedup entre triagem, automação e salvamento.
    source_type: Literal['audio', 'pdf'] = 'audio'  # Tipo do insumo auditado; o backend roteia por MIME, não pela aba da UI.
    audit_scope: Literal['call_quality'] = 'call_quality'  # Escopo fixo hoje (qualidade de atendimento); reservado p/ futuros escopos.
    sentiment: Optional[dict] = None  # Análise de sentimento (Azure Text Analytics) quando habilitada — chamada paga separada.
    audio_quality: Optional[dict] = None  # Métricas do QualityAnalyzer pré-transcrição (score 0-1, clipping, silêncio...).
    audio_date: Optional[str] = None  # Data/hora da LIGAÇÃO original (Huawei) — difere de `timestamp`, que é a data da auditoria.
    fatal_flags: List[str] = Field(default_factory=list)  # Falhas graves detectadas pela IA (ex.: falta de senha) que zeram o score (camada 2 da zeragem 3-camadas).

    @property
    def criteria_results(self) -> List[AuditResultDetail]:
        """Alias de leitura para `details` (nome usado por código legado)."""
        return self.details

    @property
    def transcription_text(self) -> str:
        """Transcrição "achatada" em uma única string (uso em buscas/prompts)."""
        return " ".join(segment.text for segment in self.transcription if segment.text).strip()


class AuditDraftPayload(BaseModel):
    """Rascunho de auditoria salvo pelo front (estado intermediário da UI).

    Os campos chegam como JSON serializado em string (o front envia o estado
    cru); o backend persiste sem desserializar/validar o conteúdo interno.
    """

    details_json: str  # JSON (string) com a lista de AuditResultDetail em edição na UI.
    transcription_json: str  # JSON (string) com a transcrição associada ao rascunho.
