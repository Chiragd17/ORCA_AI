from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App Settings
    PROJECT_NAME: str = "ORCA - Marine & Coastal Intelligence Platform"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Database Settings (PostgreSQL + Psycopg 3)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://orca_user:orca_password@localhost:5432/orca_db"
    )

    # AI LLM Settings
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct"

    # External Data Services
    OPEN_METEO_BASE_URL: str = "https://marine-api.open-meteo.com/v1/marine"
    GDACS_BASE_URL: str = "https://www.gdacs.org/datareport/resources"
    NOAA_IBTRACS_BASE_URL: str = (
        "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/access/csv"
    )

settings = Settings()
