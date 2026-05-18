from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: SecretStr
    line_channel_access_token: SecretStr | None = None
    line_channel_secret: SecretStr | None = None
    responder_line_channel_access_token: SecretStr | None = None
    responder_line_channel_secret: SecretStr | None = None
    persona_archive_dir: str | None = None
    owner_line_user_id: str | None = None
    database_url: str = "sqlite:///./data/virtualme.db"
    session_max_minutes: int = 25
    energy_low_threshold: int = 3
    follow_up_max_depth: int = 3
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    use_ppa: bool = Field(False, validation_alias=AliasChoices("use_ppa", "VIRTUALME_USE_PPA"))
    adaptive_extraction: bool = Field(
        False,
        validation_alias=AliasChoices(
            "adaptive_extraction",
            "VIRTUALME_ADAPTIVE_EXTRACTION",
        ),
    )
    max_extraction_rounds: int = Field(
        3,
        validation_alias=AliasChoices(
            "max_extraction_rounds",
            "VIRTUALME_MAX_EXTRACTION_ROUNDS",
        ),
    )
    ppa_retrieval_threshold: float = Field(
        0.2,
        validation_alias=AliasChoices(
            "ppa_retrieval_threshold",
            "VIRTUALME_PPA_RETRIEVAL_THRESHOLD",
        ),
    )
    ppa_retrieval_k: int = Field(
        5,
        validation_alias=AliasChoices("ppa_retrieval_k", "VIRTUALME_PPA_RETRIEVAL_K"),
    )
    reinjection_interval: int = Field(
        20,
        validation_alias=AliasChoices("reinjection_interval", "VIRTUALME_REINJECTION_INTERVAL"),
    )
    byok_enabled: bool = Field(
        False,
        validation_alias=AliasChoices("byok_enabled", "VIRTUALME_BYOK_ENABLED"),
    )
    consent_required: bool = Field(
        True,
        validation_alias=AliasChoices("consent_required", "VIRTUALME_CONSENT_REQUIRED"),
    )
    byok_keys_dir: str = Field(
        "./data/keys",
        validation_alias=AliasChoices("byok_keys_dir", "VIRTUALME_BYOK_KEYS_DIR"),
    )
    persona_auto_export: bool = Field(
        False,
        validation_alias=AliasChoices("persona_auto_export", "VIRTUALME_PERSONA_AUTO_EXPORT"),
    )
    persona_export_dir: str = Field(
        "./data/personas",
        validation_alias=AliasChoices("persona_export_dir", "VIRTUALME_PERSONA_EXPORT_DIR"),
    )
    snapshot_export_dir: str = Field(
        "./exports",
        validation_alias=AliasChoices("snapshot_export_dir", "VIRTUALME_SNAPSHOT_EXPORT_DIR"),
    )
    line_snapshot_export_enabled: bool = Field(
        False,
        validation_alias=AliasChoices(
            "line_snapshot_export_enabled",
            "VIRTUALME_LINE_SNAPSHOT_EXPORT_ENABLED",
        ),
    )
    line_snapshot_export_user_ids: str = Field(
        "",
        validation_alias=AliasChoices(
            "line_snapshot_export_user_ids",
            "VIRTUALME_LINE_SNAPSHOT_EXPORT_USER_IDS",
        ),
    )


def sqlite_path(database_url: str) -> str:
    return database_url.removeprefix("sqlite:///")
