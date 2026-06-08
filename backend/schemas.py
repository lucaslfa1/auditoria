from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class AuditCriterion(BaseModel):
    id: str
    chave: Optional[str] = None
    label: Optional[str] = "Critério"
    weight: float
    deflator: Optional[float] = None
    evaluation_type: Optional[Literal['auto', 'manual']] = 'auto'
    description: Optional[str] = None

class AuditAlert(BaseModel):
    id: str
    label: Optional[str] = "Alerta"
    context: Optional[str] = "Geral"
    expected_direction: Optional[Literal['efetivada', 'receptiva']] = None
    criteria: List[AuditCriterion]

class AuditResultDetail(BaseModel):
    criterionId: str
    label: str
    status: Literal['pass', 'fail', 'pending_manual']
    weight: float
    deflator: Optional[float] = None
    obtainedScore: float
    comment: str
    timestamp: Optional[str] = None
    evidence_text: Optional[str] = None
    evidence_validation: Optional[dict] = None

class TranscriptionSegment(BaseModel):
    start: str
    end: str
    text: str

class ReevaluateRequest(BaseModel):
    transcription: List[TranscriptionSegment] = Field(..., max_length=5000)
    alert: AuditAlert
    operator_name: Optional[str] = Field(None, max_length=200)
    operator_id: Optional[str] = Field(None, max_length=100)
    sector_id: Optional[str] = Field(None, max_length=50)
    source_type: Optional[Literal['audio', 'pdf']] = 'audio'
    audio_quality: Optional[dict] = None
    input_hash: Optional[str] = Field(None, max_length=128)

class RegenerateSummaryRequest(BaseModel):
    transcription: List[TranscriptionSegment] = Field(..., max_length=5000)
    alert: AuditAlert
    operator_name: Optional[str] = Field(None, max_length=200)
    details: List[AuditResultDetail] = Field(..., max_length=50)

class AuditResult(BaseModel):
    score: float
    maxPossibleScore: float
    summary: str
    ai_feedback: Optional[str] = None
    details: List[AuditResultDetail]
    transcription: List[TranscriptionSegment] = []
    operatorId: Optional[str] = ""
    operatorName: Optional[str] = "Não identificado"
    timestamp: Optional[str] = None
    input_hash: Optional[str] = None
    source_type: Literal['audio', 'pdf'] = 'audio'
    audit_scope: Literal['call_quality'] = 'call_quality'
    sentiment: Optional[dict] = None
    audio_quality: Optional[dict] = None
    audio_date: Optional[str] = None
    fatal_flags: List[str] = Field(default_factory=list)

    @property
    def criteria_results(self) -> List[AuditResultDetail]:
        return self.details

    @property
    def transcription_text(self) -> str:
        return " ".join(segment.text for segment in self.transcription if segment.text).strip()


class AuditDraftPayload(BaseModel):
    details_json: str
    transcription_json: str
