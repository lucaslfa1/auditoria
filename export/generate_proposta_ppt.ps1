$ErrorActionPreference = 'Stop'

function Add-Logo {
  param(
    [Parameter(Mandatory = $true)] $Slide,
    [Parameter(Mandatory = $true)] [string] $LogoPath,
    [Parameter(Mandatory = $false)] [int] $Width = 90
  )

  if (-not (Test-Path $LogoPath)) { return }

  # Place logo bottom-right with a small margin.
  $margin = 12
  $slideWidth = $Slide.Parent.PageSetup.SlideWidth
  $slideHeight = $Slide.Parent.PageSetup.SlideHeight

  try {
    $pic = $Slide.Shapes.AddPicture($LogoPath, 0, -1, $slideWidth - $Width - $margin, $slideHeight - 40 - $margin, $Width, -1)
    $pic.LockAspectRatio = -1
  } catch {
    # If AddPicture fails (path/codec), skip silently.
  }
}

function Add-TextSlide {
  param(
    [Parameter(Mandatory = $true)] $Presentation,
    [Parameter(Mandatory = $true)] [int] $Index,
    [Parameter(Mandatory = $true)] [string] $Title,
    [Parameter(Mandatory = $true)] [string[]] $Bullets,
    [Parameter(Mandatory = $false)] [string] $Notes = '',
    [Parameter(Mandatory = $false)] [string] $LogoPath = ''
  )

  # 2 = ppLayoutText (Title + Content)
  $slide = $Presentation.Slides.Add($Index, 2)
  $slide.Shapes.Title.TextFrame.TextRange.Text = $Title

  $body = $slide.Shapes.Placeholders.Item(2).TextFrame.TextRange
  $body.Text = ($Bullets -join "`r`n")
  try {
    $body.ParagraphFormat.Bullet.Visible = -1
  } catch {
    # Some placeholder styles may not support bullet formatting; keep plain text.
  }

  if ($Notes -and $Notes.Trim().Length -gt 0) {
    try {
      $notesRange = $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange
      $notesRange.Text = $Notes
    } catch {
      # Notes placeholder index can vary; ignore if not available.
    }
  }

  if ($LogoPath) { Add-Logo -Slide $slide -LogoPath $LogoPath }
}

function Add-TitleSlide {
  param(
    [Parameter(Mandatory = $true)] $Presentation,
    [Parameter(Mandatory = $true)] [int] $Index,
    [Parameter(Mandatory = $true)] [string] $Title,
    [Parameter(Mandatory = $true)] [string] $Subtitle,
    [Parameter(Mandatory = $false)] [string] $Notes = '',
    [Parameter(Mandatory = $false)] [string[]] $LogoPaths = @()
  )

  # 1 = ppLayoutTitle
  $slide = $Presentation.Slides.Add($Index, 1)
  $slide.Shapes.Title.TextFrame.TextRange.Text = $Title
  $slide.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = $Subtitle

  if ($Notes -and $Notes.Trim().Length -gt 0) {
    try {
      $notesRange = $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange
      $notesRange.Text = $Notes
    } catch {}
  }

  foreach ($lp in $LogoPaths) {
    if (-not (Test-Path $lp)) { continue }
    try {
      # Top-right stacking.
      $slideWidth = $Presentation.PageSetup.SlideWidth
      $x = $slideWidth - 130
      $y = 15
      $slide.Shapes.AddPicture($lp, 0, -1, $x, $y, 110, -1) | Out-Null
      $y += 55
    } catch {}
  }
}

function New-Deck {
  param(
    [Parameter(Mandatory = $true)] [string] $OutPath,
    [Parameter(Mandatory = $true)] [string] $DeckFocus, # "Auditoria" or "Sentinel"
    [Parameter(Mandatory = $true)] [string] $PrimaryLogoPath
  )

  $app = New-Object -ComObject PowerPoint.Application
  # Some environments disallow hiding the PowerPoint window via COM.
  $app.Visible = -1
  $presentation = $app.Presentations.Add()

  $title = "Transcricao e Analise Automatizada de Ligacoes e Ocorrencias"
  $subtitle = "Projeto: $DeckFocus | Proposta: Whisper (transcricao) + GPT no Azure (analise)"
  $notesTitle = @"
Hoje temos informacao critica no audio, mas ela nao vira dado acionavel com rapidez.
A proposta cria um pipeline padrao: transcrever com qualidade e analisar no Azure para gerar achados, evidencias e relatorios.
"@.Trim()

  $logoSentinel = Join-Path $PSScriptRoot "..\\assets\\logo-sentinel.png"
  $logoNstech = Join-Path $PSScriptRoot "..\\public\\nstech-logo.png"
  $logos = @($logoNstech, $logoSentinel) | Where-Object { Test-Path $_ }

  Add-TitleSlide -Presentation $presentation -Index 1 -Title $title -Subtitle $subtitle -Notes $notesTitle -LogoPaths $logos

  $commonLogo = $PrimaryLogoPath

  Add-TextSlide -Presentation $presentation -Index 2 -Title "Contexto e Dor (Operacoes)" -Bullets @(
    "Tempo alto para revisar chamadas e escrever relatorios",
    "Variacao de criterio entre analistas (inconsistencia)",
    "Baixa rastreabilidade: por que um item foi marcado",
    "Dificuldade de pesquisar: audio nao e indexavel como texto"
  ) -Notes "A dor e operacional: custo de tempo e perda de padrao. Isso impacta velocidade de resposta e qualidade do controle." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 3 -Title "Objetivo e Resultado Esperado" -Bullets @(
    "Transformar audio em texto confiavel e pesquisavel",
    "Gerar analises padronizadas: resumo, achados, riscos, recomendacoes",
    "Evidencia auditavel: trechos citados + timestamps",
    "Aumentar cobertura: mais chamadas avaliadas com o mesmo time"
  ) -Notes "Nao e substituir auditor. E aumentar produtividade e consistencia, com trilha de evidencia para revisao humana quando necessario." -LogoPath $commonLogo

  if ($DeckFocus -eq "Sentinel") {
    Add-TextSlide -Presentation $presentation -Index 4 -Title "O Que Entra e o Que Sai (Sentinel + Auditoria)" -Bullets @(
      "Entradas: audio (wav/mp3/mpeg), metadados (cliente, canal, operador, data, tipo)",
      "Saidas Sentinel: alertas, categorias de risco, severidade, resumo acionavel, recomendacoes",
      "Saidas Auditoria: checklist preenchido, pontuacao/score, nao conformidades, evidencias"
    ) -Notes "Para TI: outputs podem ser estruturados (JSON) para integracao com banco e dashboards." -LogoPath $commonLogo
  } else {
    Add-TextSlide -Presentation $presentation -Index 4 -Title "O Que Entra e o Que Sai (Auditoria + Sentinel)" -Bullets @(
      "Entradas: audio (wav/mp3/mpeg), metadados (cliente, canal, operador, data, tipo)",
      "Saidas Auditoria: checklist preenchido, pontuacao/score, nao conformidades, evidencias",
      "Saidas Sentinel: alertas, categorias de risco, severidade, resumo acionavel, recomendacoes"
    ) -Notes "Para TI: outputs podem ser estruturados (JSON) para integracao com banco e dashboards." -LogoPath $commonLogo
  }

  Add-TextSlide -Presentation $presentation -Index 5 -Title "Por que Whisper (API) para Transcricao" -Bullets @(
    "Foco em acuracia para linguagem natural e cenarios ruidosos",
    "Suporte a timestamps para evidencias e navegacao",
    "Pipeline escalavel (processamento por lotes ou fila)",
    "Resultado padrao para alimentar modelos e relatorios"
  ) -Notes "A transcricao e a fundacao. Se a transcricao for fraca, toda a analise fica fraca." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 6 -Title "Por que GPT no Azure para Analise" -Bullets @(
    "Extracao e sumarizacao: itens acionaveis a partir de texto longo",
    "Classificacao e padronizacao: aplicar criterios e gerar saidas consistentes",
    "Governanca: controle de acesso, auditoria de uso, integracao com Azure",
    "Flexibilidade: ajustar prompts e criterios sem reescrever codigo"
  ) -Notes "O GPT transforma transcricao em decisao e relatorio padronizado. Azure ajuda TI com governanca e integracao." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 7 -Title "Arquitetura Proposta (Alto Nivel)" -Bullets @(
    "1) Ingestao: upload do audio + metadados",
    "2) Transcricao: Whisper -> texto + timestamps",
    "3) Normalizacao: limpeza, segmentacao, opcional mascaramento de PII",
    "4) Analise: GPT (Azure) -> JSON de achados/score/evidencias",
    "5) Persistencia: DB/Storage + indexacao para busca + trilha de auditoria"
  ) -Notes "Componentes desacoplados e processamento via fila para controle de custo e priorizacao." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 8 -Title "Seguranca, Privacidade e Compliance" -Bullets @(
    "Dados minimizados: enviar apenas o necessario",
    "Segredos em Key Vault + identidade gerenciada (quando aplicavel)",
    "Criptografia em transito e repouso",
    "Retencao por politica: audio/transcricao/relatorio com prazos definidos",
    "PII: redacao/mascaramento antes de analises amplas (quando exigido)"
  ) -Notes "Foco em reduzir risco com controles de acesso, observabilidade e politica clara de retencao." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 9 -Title "Qualidade e Confiabilidade" -Bullets @(
    "Saidas com citacoes: cada achado aponta trecho e timestamp",
    "Respostas estruturadas (JSON) + validacao de schema",
    "Itens criticos com revisao humana",
    "Monitoramento de qualidade por canal/cliente"
  ) -Notes "O modelo sugere com evidencias; a decisao final em itens criticos permanece com o processo de auditoria." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 10 -Title "Custos e Controle" -Bullets @(
    "Custo variavel por minuto de audio (transcricao) + tokens (analise)",
    "Controles: limites por cliente/projeto, batch, cache de transcricoes",
    "Estrategia em camadas: triagem barata -> analise completa sob demanda",
    "Relatorio de consumo por unidade (time/cliente/canal)"
  ) -Notes "Governamos custo via fila, limites e processamento por camadas." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 11 -Title "Plano de Implantacao (30/60/90)" -Bullets @(
    "0-30 dias: MVP com transcricao + resumo + busca + exportacao",
    "31-60 dias: criterios automatizados + score + evidencias",
    "61-90 dias: alertas, governanca completa (PII/retencao), dashboards"
  ) -Notes "Entregas incrementais: valor cedo e evolucao controlada." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 12 -Title "Metricas de Sucesso" -Bullets @(
    "Operacoes: tempo por caso, cobertura, retrabalho",
    "Qualidade: concordancia com auditoria humana, falso positivo em alertas",
    "TI: custo por hora analisada, latencia, disponibilidade, auditoria de acesso"
  ) -Notes "Compromisso de acompanhamento e ajustes de criterios/prompt com base nas metricas." -LogoPath $commonLogo

  Add-TextSlide -Presentation $presentation -Index 13 -Title "Pedido de Aprovacao / Decisoes" -Bullets @(
    "Aprovar Whisper API para transcricao",
    "Aprovar Azure OpenAI (GPT) para analise",
    "Aprovar arquitetura com fila + storage + logs de auditoria",
    "Definir 1 piloto (cliente/canal/volume) para calibrar custo e qualidade"
  ) -Notes "Objetivo hoje: sim para piloto controlado e governado, com metricas claras." -LogoPath $commonLogo

  # Save as PPTX (24 = ppSaveAsOpenXMLPresentation)
  $outFull = (Resolve-Path $OutPath).Path
  $presentation.SaveAs($outFull, 24)
  $presentation.Close()
  $app.Quit()
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$exportDir = Join-Path $root "export"

$auditoriaOut = Join-Path $exportDir "proposta_auditoria_whisper_gpt_azure.pptx"
$sentinelOut = Join-Path $exportDir "proposta_sentinel_whisper_gpt_azure.pptx"

New-Deck -OutPath $auditoriaOut -DeckFocus "Auditoria" -PrimaryLogoPath (Join-Path $root "public\\nstech-logo.png")
New-Deck -OutPath $sentinelOut -DeckFocus "Sentinel" -PrimaryLogoPath (Join-Path $root "assets\\logo-sentinel.png")

Write-Output "Generated:"
Write-Output $auditoriaOut
Write-Output $sentinelOut
