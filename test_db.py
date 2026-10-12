import os
from dotenv import load_dotenv # type: ignore
from sqlalchemy import create_engine, text # type: ignore

def main() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    print("🔍 Testando leitura do .env...")
    if not database_url:
        print("❌ ERRO: DATABASE_URL não encontrada no arquivo .env!")
        return

    print("✅ DATABASE_URL encontrada com sucesso!")
    print("\n⚡ Tentando conectar ao banco do Supabase...")
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            version = result.fetchone()
            print("\n🎉 CONEXÃO REALIZADA COM SUCESSO!")
            print(f"📌 Versão do PostgreSQL: {version[0]}")
    except Exception as error:
        print("\n❌ ERRO AO CONECTAR COM O BANCO DE DADOS:")
        print(error)


if __name__ == "__main__":
    main()
