import json

with open('backend/config/prompts.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

prompt = config['evaluation_user_prompt']

prompt = prompt.replace(
    '"summary": "Resumo textual clínico e direto da avaliação (2-4 frases)"',
    '"summary": "Resumo da avaliação em linguagem simples, natural e objetiva (2-4 frases). Evite usar o termo \'Resumo executivo\' e não enfeite com jargões corporativos."'
)

prompt = prompt.replace(
    '"ai_feedback": "Feedback curto, direto e acionável para o operador. Aja como um inspetor técnico."',
    '"ai_feedback": "Feedback técnico, direto e construtivo para o operador em linguagem simples. Sem frases prontas corporativas."'
)

prompt = prompt.replace(
    '"comment": "Justificativa técnica rigorosa baseada EXCLUSIVAMENTE no que foi falado."',
    '"comment": "Justificativa técnica objetiva. Utilize português simples: em vez de dizer \'FAIL nesse critério\', diga \'falha no critério\'."'
)

prompt = prompt.replace(
    'Retorne texto íntegro e corporativo.',
    'Retorne texto íntegro, técnico, simples e focado nos fatos, sem enfeitar.'
)

config['evaluation_user_prompt'] = prompt

with open('backend/config/prompts.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=4, ensure_ascii=False)

print('Prompts.json atualizado com sucesso!')
