from sqlalchemy import create_engine, text

engine = create_engine('postgresql://postgres:postgres@localhost:5432/auditoria')
with engine.connect() as conn:
    print("Searching in arquivos_salvos:")
    try:
        res = conn.execute(text("SELECT id, arquivo, tipo FROM arquivos_salvos WHERE conteudo LIKE '%wellington%' OR arquivo LIKE '%wellington%' LIMIT 5"))
        for row in res:
            print("arquivos_salvos:", dict(row))
    except Exception as e:
        print(e)
        
    print("Searching in audits:")
    try:
        res = conn.execute(text("SELECT id, operator_name, source_type, cast(transcription_json as text) as trans FROM audits WHERE cast(transcription_json as text) LIKE '%wellington%' LIMIT 5"))
        for row in res:
            print("audits:", row[0], row[1], row[2], str(row[3])[:100])
    except Exception as e:
        print(e)
