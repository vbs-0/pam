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
    household_password: str | None = None
    allow_signup: bool = True
    cors_origins: str = "http://localhost:5173"
    data_dir: str = "../data"
    reports_dir: str = "../reports"
    max_job_transactions: int = 100_000      # admin jobs that generate data; the 1 GB server fits starter

    def check(self) -> None:
        if self.env == "prod" and (self.jwt_secret == DEFAULT_SECRET or len(self.jwt_secret) < 32):
            raise RuntimeError("JWT_SECRET must be set to 32+ random characters in prod")
        if self.env == "prod" and self.demo_password and (len(self.demo_password) < 12
                                                          or self.demo_password == self.household_password):
            raise RuntimeError("DEMO_PASSWORD guards staff logins: 12+ characters, not the shared household one")

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


settings = Settings()
