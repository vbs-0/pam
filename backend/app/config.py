from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-only-secret-change-me-dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://pam:pam@localhost:5432/pam"
    test_database_url: str | None = None
    jwt_secret: str = DEFAULT_SECRET
    jwt_ttl_minutes: int = 60
    firebase_project_id: str | None = None
    admin_emails: str = ""
    demo_password: str | None = None
    cors_origins: str = "http://localhost:5173"
    data_dir: str = "../data"
    reports_dir: str = "../reports"

    def check(self) -> None:
        if self.env == "prod" and (self.jwt_secret == DEFAULT_SECRET or len(self.jwt_secret) < 32):
            raise RuntimeError("JWT_SECRET must be set to 32+ random characters in prod")

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


settings = Settings()
