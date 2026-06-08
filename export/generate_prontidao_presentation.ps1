$ErrorActionPreference = 'Stop'

function Add-Logo {
  param(
    [Parameter(Mandatory = $true)] $Slide,
    [Parameter(Mandatory = $true)] [string] $LogoPath
  )

  if (-not (Test-Path $LogoPath)) { return }

  try {
    $slideWidth = $Slide.Parent.PageSetup.SlideWidth
    $Slide.Shapes.AddPicture($LogoPath, 0, -1, $slideWidth - 120, 15, 95, -1) | Out-Null
  }
  catch {}
}

function Add-TitleSlide {
  param(
    [Parameter(Mandatory = $true)] $Presentation,
    [Parameter(Mandatory = $true)] [int] $Index,
    [Parameter(Mandatory = $true)] [string] $Title,
    [Parameter(Mandatory = $true)] [string] $Subtitle,
    [Parameter(Mandatory = $false)] [string] $LogoPath = ''
  )

  $slide = $Presentation.Slides.Add($Index, 1)
  $slide.Shapes.Title.TextFrame.TextRange.Text = $Title
  $slide.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = $Subtitle
  if ($LogoPath) { Add-Logo -Slide $slide -LogoPath $LogoPath }
}

function Add-TextSlide {
  param(
    [Parameter(Mandatory = $true)] $Presentation,
    [Parameter(Mandatory = $true)] [int] $Index,
    [Parameter(Mandatory = $true)] [string] $Title,
    [Parameter(Mandatory = $true)] [string[]] $Bullets,
    [Parameter(Mandatory = $false)] [string] $LogoPath = ''
  )

  $slide = $Presentation.Slides.Add($Index, 2)
  $slide.Shapes.Title.TextFrame.TextRange.Text = $Title
  $body = $slide.Shapes.Placeholders.Item(2).TextFrame.TextRange
  $body.Text = ($Bullets -join "`r`n")
  try { $body.ParagraphFormat.Bullet.Visible = -1 } catch {}
  if ($LogoPath) { Add-Logo -Slide $slide -LogoPath $LogoPath }
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$logo = Join-Path $root "public\\nstech-logo.png"
$today = Get-Date -Format "yyyy-MM-dd"
$outPath = Join-Path $root "export\\prontidao_apresentacao_nstech_$today.pptx"

$app = New-Object -ComObject PowerPoint.Application
$app.Visible = -1
$presentation = $app.Presentations.Add()

Add-TitleSlide -Presentation $presentation -Index 1 `
  -Title "Sistema de Auditoria nstech" `
  -Subtitle "Prontidao para apresentacao | Atualizado em $today" `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 2 `
  -Title "Resumo Executivo" `
  -Bullets @(
  "Status atual: pronto para apresentacao controlada",
  "Bloqueadores principais removidos",
  "Validacao tecnica concluida em arquitetura, testes e operacao local",
  "Recomendacao: apresentar com roteiro e arquivos reais separados"
) `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 3 `
  -Title "O Que Foi Corrigido" `
  -Bullets @(
  "Login local ajustado para manter sessao em HTTP",
  "Mocks automaticos removidos do dashboard",
  "Autenticacao endurecida com configuracao externa de usuarios",
  "Lint limitado ao escopo real do app",
  "Testes de auth estabilizados"
) `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 4 `
  -Title "Validacoes Executadas" `
  -Bullets @(
  "npm run test: frontend e backend aprovados",
  "npm run lint: aprovado",
  "npm run build: aprovado",
  "Smoke test local: health, frontend, login, sessao e logout aprovados"
) `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 5 `
  -Title "Arquitetura Avaliada" `
  -Bullets @(
  "Frontend: React + TypeScript + Vite",
  "Backend: FastAPI",
  "Persistencia local: SQLite",
  "Exportacoes: Excel, PDF e Word",
  "Integracoes externas: Gemini e Azure/OpenAI"
) `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 6 `
  -Title "Ressalvas Restantes" `
  -Bullets @(
  "Ensaiar a demo final com dados reais",
  "Conferir credenciais do ambiente que sera usado",
  "Levar roteiro curto de navegacao e contingencia",
  "Evitar improviso de base ou arquivos na hora da apresentacao"
) `
  -LogoPath $logo

Add-TextSlide -Presentation $presentation -Index 7 `
  -Title "Recomendacao Final" `
  -Bullets @(
  "Pode ser apresentado tecnicamente",
  "Preferir apresentacao controlada e previamente ensaiada",
  "Levar exemplos reais de auditoria e classificacao",
  "Usar este material como apoio executivo da demonstracao"
) `
  -LogoPath $logo

$presentation.SaveAs($outPath, 24)
$presentation.Close()
$app.Quit()

Write-Output $outPath
