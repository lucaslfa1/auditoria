# Exemplos de Treinamento (Golden Dataset)

Esta pasta oculta contém exemplos manuais curados de auditorias ("jurisprudências") para auxiliar no treinamento e direcionamento da IA avaliadora.
Em vez de a IA ler apenas regras secas, ela consultará estes arquivos para entender como julgar casos ambíguos.

## Como usar
Quando você identificar uma ligação que serve de exemplo perfeito (seja porque a IA errou e você quer corrigi-la, ou porque o operador agiu muito bem contornando um roteiro), salve um arquivo `.json` aqui dentro.

## Formato ideal para as amostras
Tente manter os arquivos JSON com a seguinte estrutura para facilitar a injeção no contexto do RAG:

```json
{
  "cenario": "O motorista já chega falando o problema antes do operador perguntar",
  "transcricao_resumida": [
    "Operador: Alô, bom dia.",
    "Motorista: O caminhão quebrou o teclado desde quinta e estou na oficina.",
    "Operador: Ah, entendi. Vou verificar aqui."
  ],
  "gabarito_avaliacao": {
    "criterio_local_homologado": "pass",
    "justificativa_ia": "Como o motorista já está parado na oficina por problemas técnicos, o operador não precisa dar advertência sobre parar em local homologado. Em conformidade com a regra de benevolência para critérios inaplicáveis, o status é 'pass' (Atende)."

  }
}
```

## Recomendação de Amostragem (15 a 30 exemplos)
Para não sobrecarregar a memória da IA e manter o sistema rápido, adicione:
- **3 a 5 Casos Perfeitos:** Seguiram o script.
- **3 a 5 Casos 'Pulo de Script':** O operador contornou bem uma situação fora do comum.
- **3 a 5 Casos de Áudio Ruim:** Como ignorar erros de transcrição que não afetam o contexto.
- **3 a 5 Casos de Zero/Falha Crítica:** Quebra inegociável de regra.
