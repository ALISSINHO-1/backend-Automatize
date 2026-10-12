import os
from dotenv import load_dotenv # type: ignore
from sqlalchemy import create_engine, text # type: ignore

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("🔍 Testando leitura do .env...")
if not DATABASE_URL:
    print("❌ ERRO: DATABASE_URL não encontrada no arquivo .env!")
else:
    print("✅ DATABASE_URL encontrada com sucesso!")
    print("\n⚡ Tentando conectar ao banco do Supabase...")
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            version = result.fetchone()
            print("\n🎉 CONEXÃO REALIZADA COM SUCESSO!")
            print(f"📌 Versão do PostgreSQL: {version[0]}")
    except Exception as e:
        print("\n❌ ERRO AO CONECTAR COM O BANCO DE DADOS:")
        print(e)