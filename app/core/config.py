import os
from dotenv import load_dotenv # type: ignore

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    STORAGE_BUCKET_NAME: str = os.getenv("STORAGE_BUCKET_NAME", "evidencias-anexos")

settings = Settings()