"""Centralised application configuration.

All values are sourced from environment variables (optionally via a .env file)
so that no secret or deployment-specific value is hard-coded in the codebase.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Runtime settings for the KONE ELEVATE backend."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ app
    APP_NAME: str = "KONE ELEVATE"
    APP_DESCRIPTION: str = (
        "Component Passport - AI-Powered Circular Economy Platform for "
        "elevator component lifecycle management. PROTOTYPE."
    )
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    #: "json" (default - structured, one object per line, request-id
    #: correlated) or "human" (the original single-line format, for a
    #: developer tailing a terminal). See app.core.logging_config.
    LOG_FORMAT: str = "json"
    DEBUG: bool = False

    # ------------------------------------------------------------- database
    DATABASE_URL: str = "sqlite:///./kone_elevate.db"
    SQL_ECHO: bool = False

    # ------------------------------------------------------------ frontend
    FRONTEND_URL: str = "http://localhost:5173"
    #: NoDecode: pydantic-settings otherwise tries to JSON-parse any env var
    #: mapped onto a List[str] field before our own comma-split validator
    #: below ever runs, and raises SettingsError on a plain comma-separated
    #: string - exactly the format docker-compose.yml and .env.example use.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
        ]
    )

    # ------------------------------------------------------------------- qr
    QR_BASE_URL: str = "http://localhost:5173"
    QR_PASSPORT_PATH: str = "/passport"

    # ------------------------------------------------------------------- ml
    MODEL_PATH: str = "models/random_forest.joblib"
    MODEL_METRICS_PATH: str = "models/metrics.json"
    MODEL_IMPORTANCE_PATH: str = "models/feature_importance.json"
    MODEL_VERSION: str = "RF-v1.0-synthetic"

    # ------------------------------------------------------- forecasting
    FORECAST_MODEL_PATH: str = "models/survival_model.joblib"
    FORECAST_METRICS_PATH: str = "models/forecast_metrics.json"
    FORECAST_MODEL_VERSION: str = "WeibullAFT-v1.0-synthetic"

    #: PROTOTYPE ESTIMATES. Component-recovery labour hours per component type
    #: (dismantling, then inspecting and testing the recovered sub-components) -
    #: the input that turns a forecast of removals into a capacity plan.
    #: These are illustrative figures, NOT KONE workshop standards, and must
    #: be replaced with real routing/standard-time data before any planning use.
    COMPONENT_RECOVERY_LABOUR_HOURS: dict = Field(
        default_factory=lambda: {
            "Motor": 16.0,
            "Steel Rope": 4.0,
            "Brake": 9.0,
            "Governor": 7.5,
            "Door Operator": 11.0,
            "Sheave": 12.0,
        }
    )

    #: Declared component-recovery workshop capacity, in labour hours per quarter.
    #: One workshop, one shift pattern; override per deployment.
    WORKSHOP_CAPACITY_HOURS_PER_QUARTER: float = 1200.0

    #: Share of forecast removals from which sub-components are realistically
    #: recovered, rather than going straight to material recovery or disposal.
    #: Illustrative.
    COMPONENT_RECOVERY_ROUTING_RATE: float = 0.45
    DATASET_PATH: str = "data/synthetic/dataset.csv"
    DATASET_RECORDS: int = 10_000
    DATASET_SEED: int = 42

    # ------------------------------------------------------------- security
    SECRET_KEY: str = "dev-only-insecure-key-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    AUDIT_ACTOR_DEFAULT: str = "system"

    #: PBKDF2-HMAC-SHA256 iteration count for password hashing. The work
    #: factor is the whole point: it costs an attacker the same per guess as
    #: it costs us per sign-in. Configurable only so the test suite can drop
    #: it - a suite that spends most of its time deliberately burning CPU
    #: tests nothing. Never lower it in a real deployment.
    PBKDF2_ROUNDS: int = 240_000

    # ------------------------------------------------- signup verification
    #: How long an emailed one-time code stays valid.
    OTP_TTL_MINUTES: int = 10
    #: Wrong guesses allowed before a code is burned and must be resent.
    #: Six digits is a million combinations; without this cap an attacker
    #: gets to try all of them.
    OTP_MAX_ATTEMPTS: int = 5
    #: Minimum gap between resend requests for one address, in seconds.
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    #: Role a self-registered account receives once its email is verified.
    #: Deliberately the lowest-privilege role: verifying that someone owns an
    #: inbox says nothing about what they should be allowed to do, so anything
    #: above this is granted by a supervisor, never claimed at signup.
    SIGNUP_DEFAULT_ROLE: str = "technician"

    # ------------------------------------------------------------ smtp
    #: Leave SMTP_HOST empty to run without a mail server: codes are written
    #: to the log and to data/outbox/ instead of being sent. That keeps signup
    #: demonstrable with no credentials, and the API says which mode it used
    #: rather than pretending an email went out.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_FROM: str = "KONE ELEVATE <no-reply@kone-elevate.demo>"
    SMTP_TIMEOUT_SECONDS: int = 15
    #: Where codes are written when no SMTP server is configured.
    MAIL_OUTBOX_PATH: str = "data/outbox"

    @property
    def smtp_configured(self) -> bool:
        """True only when there is enough here to actually send.

        A host with a username but no password is *half* configured - the
        state a deployment sits in between pasting the server address and
        pasting the credential. Treating that as configured would make every
        signup fail authentication; treating it as unconfigured falls back to
        the outbox, which is what the deployment effectively is until the
        credential arrives.

        This is not the same as a fully configured server that is failing -
        that still raises, because it is an incident rather than a fallback.
        """
        if not self.SMTP_HOST.strip():
            return False
        if self.SMTP_USERNAME.strip() and not self.SMTP_PASSWORD:
            return False
        return True

    @property
    def kone_api_configured(self) -> bool:
        """Whether real KONE API credentials are present.

        False is the expected state for this build and is not an error: the
        integration registry falls back to the recorded fixtures and every
        response says which it used. Half-configured (one of the two set)
        counts as not configured, the same way SMTP does - a request that
        would certainly 401 is worse than an honest fallback.
        """
        return bool(self.KONE_CLIENT_ID.strip() and self.KONE_CLIENT_SECRET.strip())

    # --------------------------------------------------- prototype impact
    # PROTOTYPE ESTIMATES ONLY - these are illustrative figures chosen for the
    # demo. They are NOT official KONE cost, mass or emission factors and must
    # be replaced with validated engineering data before any real reporting.
    IMPACT_CURRENCY: str = "INR"
    IMPACT_CURRENCY_SYMBOL: str = "Rs."

    #: Illustrative replacement cost of a NEW component, by component type.
    IMPACT_NEW_PART_COST: dict = Field(
        default_factory=lambda: {
            "Motor": 185_000.0,
            "Steel Rope": 42_000.0,
            "Brake": 96_000.0,
            "Governor": 78_000.0,
            "Door Operator": 120_000.0,
            "Sheave": 88_000.0,
        }
    )

    #: Price of each material grade relative to IMPACT_NEW_PART_COST, which is
    #: the price of the type's reference grade (life factor 1.0). ILLUSTRATIVE
    #: prototype ratios for the grade cost comparison - replace with supplier
    #: quotes before quoting any saving.
    IMPACT_GRADE_PRICE_FACTOR: dict = Field(
        default_factory=lambda: {
            "Motor": {
                "pmsm_class_f": 1.0,
                "pmsm_class_h": 1.08,
                "induction_cu_class_f": 0.85,
                "induction_al_class_b": 0.70,
            },
            "Steel Rope": {
                "steel_fibre_core": 1.0,
                "steel_iwrc": 1.2,
                "steel_compacted_iwrc": 1.45,
            },
            "Sheave": {
                "ductile_iron": 1.0,
                "grey_iron": 0.8,
                "hardened_steel": 1.45,
            },
            "Governor": {
                "cast_iron_centrifugal": 1.0,
                "steel_centrifugal": 1.15,
                "aluminium_compact": 1.05,
            },
        }
    )

    #: Illustrative cost of fitting one replacement (labour, rigging, lift
    #: out of service), by component type. Paid again at every replacement,
    #: so it is what makes a longer-lived grade worth a higher part price.
    IMPACT_REPLACEMENT_FITTING_COST: dict = Field(
        default_factory=lambda: {
            "Motor": 45_000.0,
            "Steel Rope": 18_000.0,
            "Sheave": 30_000.0,
            "Governor": 12_000.0,
        }
    )

    # --- KONE API Portal (P5 / K-1) --------------------------------------
    #: Credentials for KONE's published APIs (https://dev.kone.com). Empty by
    #: default, and empty is the honest state: obtaining them needs an
    #: organisation to nominate an owner on the KONE API Portal, which this
    #: build has never had. While they are empty the integration registry
    #: keeps serving the fixture adapters and says so in every response -
    #: see app/integrations/registry.py.
    KONE_API_HOSTNAME: str = "dev.kone.com"
    KONE_CLIENT_ID: str = ""
    KONE_CLIENT_SECRET: str = ""
    KONE_API_TIMEOUT_SECONDS: int = 15

    #: Material Circularity Indicator (Ellen MacArthur Foundation) process
    #: efficiencies. E_C is the yield of the end-of-life recycling process;
    #: E_F the yield of the process that produced any recovered-material feedstock.
    #: Both are ILLUSTRATIVE prototype values, not measured KONE or supplier
    #: figures - see app/services/circularity_service.py, which reports them
    #: alongside every MCI it computes so the number can be re-derived.
    MCI_RECYCLING_EFFICIENCY: float = 0.9
    MCI_RECYCLED_FEEDSTOCK_EFFICIENCY: float = 0.9

    #: Illustrative component mass in kilograms, by component type.
    IMPACT_COMPONENT_MASS_KG: dict = Field(
        default_factory=lambda: {
            "Motor": 260.0,
            "Steel Rope": 95.0,
            "Brake": 55.0,
            "Governor": 40.0,
            "Door Operator": 48.0,
            "Sheave": 130.0,
        }
    )

    #: Illustrative embodied-carbon intensity (kg CO2e per kg of material).
    IMPACT_CO2_PER_KG: dict = Field(
        default_factory=lambda: {
            "Steel": 1.9,
            "Cast Iron": 1.6,
            "Aluminum": 8.2,
            "Copper": 4.1,
            "Electronic": 21.0,
            "Composite": 5.4,
        }
    )

    #: Fraction of a new part's value retained or recovered, by category.
    #: CONTINUE_USING retains value in place (a replacement is avoided).
    #: COMPONENT_RECOVERY recovers only the value of usable sub-components - never
    #: a complete component - so it sits well below the old whole-component
    #: figure. DEFER_TO_INSPECTION is 0.0: nothing has been decided yet.
    IMPACT_VALUE_RECOVERY_FACTOR: dict = Field(
        default_factory=lambda: {
            "CONTINUE_USING": 0.70,
            "COMPONENT_RECOVERY": 0.20,
            "MATERIAL_RECOVERY": 0.08,
            "DISPOSE": 0.0,
            "DEFER_TO_INSPECTION": 0.0,
        }
    )

    #: Fraction of embodied carbon avoided, by category.
    IMPACT_CO2_AVOIDANCE_FACTOR: dict = Field(
        default_factory=lambda: {
            "CONTINUE_USING": 0.92,
            "COMPONENT_RECOVERY": 0.35,
            "MATERIAL_RECOVERY": 0.30,
            "DISPOSE": 0.0,
            "DEFER_TO_INSPECTION": 0.0,
        }
    )

    IMPACT_CO2_PER_KG_STEEL: float = 1.9  # kept for .env compatibility

    # ------------------------------------------------------- compliance (P3)
    #: Mass fraction of EU-listed critical raw materials within each material,
    #: keyed material -> substance -> fraction of total component mass.
    #: Backs the simplified-ESRS critical-raw-materials metric, which points
    #: straight at electronic assemblies.
    #:
    #: PROTOTYPE ESTIMATES. These are order-of-magnitude figures for a demo,
    #: not a bill of materials. A filed CRM disclosure must come from supplier
    #: declarations per article, not from a per-material average.
    CRM_MASS_FRACTION: dict = Field(
        default_factory=lambda: {
            "Electronic": {
                "Copper": 0.200,
                "Aluminium": 0.040,
                "Rare earth elements": 0.0050,
                "Palladium": 0.00012,
                "Gallium": 0.00004,
            },
            "Copper": {"Copper": 0.950},
            "Aluminum": {"Aluminium": 0.960},
            "Steel": {"Nickel": 0.008, "Manganese": 0.012},
            "Cast Iron": {"Manganese": 0.006},
            "Composite": {"Aluminium": 0.020},
        }
    )

    #: Substances above that are on the EU Critical Raw Materials Act (EU)
    #: 2024/1252 list. Recorded so the report can name its own basis.
    CRM_LIST_REFERENCE: str = "Regulation (EU) 2024/1252 (Critical Raw Materials Act), Annex I"

    #: Persistent-identifier namespace for the Digital Product Passport.
    #: A passport whose link dies when the demo server stops is not a passport,
    #: so the identifier is a URN that never changes, and resolution is a
    #: separate, replaceable concern (DPP_RESOLVER_BASE_URL).
    DPP_ID_NAMESPACE: str = "urn:kone:dpp"
    DPP_SCHEMA_VERSION: str = "1"

    #: Where a scanned passport identifier resolves. Deliberately NOT
    #: localhost: the QR payload printed on a component label outlives any
    #: development server. Until a real resolver is registered this points at
    #: a documented placeholder host and the export says so.
    DPP_RESOLVER_BASE_URL: str = "https://dpp.kone-elevate.example/v1"
    DPP_RESOLVER_REGISTERED: bool = False

    #: CPR (EU) 2024/3110 economic-operator identification. The economic
    #: operator is who a market-surveillance authority contacts about this
    #: product; a DPP without one is not conformant.
    DPP_ECONOMIC_OPERATOR: str = "KONE ELEVATE prototype - economic operator not yet assigned"
    DPP_ECONOMIC_OPERATOR_ID: str = ""
    DPP_ECONOMIC_OPERATOR_ROLE: str = "MANUFACTURER"
    DPP_ECONOMIC_OPERATOR_ADDRESS: str = ""

    #: Optional external append-only store the daily audit-chain head hash is
    #: published to. Empty means anchoring records locally only, which does NOT
    #: survive a database administrator - the anchor report says so explicitly.
    CHAIN_ANCHOR_WEBHOOK_URL: str = ""
    CHAIN_ANCHOR_LOG_PATH: str = "data/anchors/chain_anchors.jsonl"

    # --------------------------------------------------------- observability (P4)
    #: Emits one trace span per request and per SQL statement (hand-rolled
    #: in app.core.telemetry - see requirements.txt for why not the
    #: auto-instrumentation packages). Off costs nothing; on with no
    #: exporter configured below still costs nothing - spans are created and
    #: silently dropped, never sent anywhere.
    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "kone-elevate-backend"
    #: Empty means "no real collector configured" - spans are created but not
    #: exported anywhere unless OTEL_CONSOLE_EXPORT is also set. Point this at
    #: an OTLP/HTTP collector (Jaeger, Tempo, a vendor) to actually see traces.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    #: Print spans to stdout as they finish. Useful for seeing tracing work
    #: with no collector at all; noisy, so off by default even with DEBUG.
    OTEL_CONSOLE_EXPORT: bool = False

    #: Posted to (a Slack/Teams incoming webhook, PagerDuty events endpoint,
    #: or anything else that accepts a JSON POST) when scripts/check_drift.py
    #: finds a significant feature shift. Empty means "print only" - the
    #: same "record the gap rather than hide it" pattern as
    #: CHAIN_ANCHOR_WEBHOOK_URL above.
    DRIFT_ALERT_WEBHOOK_URL: str = ""
    #: Same, for scripts/verify_chain.py finding a broken audit chain link.
    #: Kept separate from the drift webhook because these page different
    #: people (ML/data vs. security/compliance) in a real deployment.
    CHAIN_VERIFY_ALERT_WEBHOOK_URL: str = ""

    # ------------------------------------------------------------- rate limiting
    #: Requests allowed per window per client (IP, or bearer subject when
    #: authenticated) before a 429. Applied only to the endpoints named in
    #: app.core.rate_limit.SENSITIVE_LIMITS - login and signup, where the
    #: cost of a miss is credential stuffing / OTP-guessing, not every
    #: endpoint indiscriminately.
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_LOGIN_MAX: int = 10
    RATE_LIMIT_SIGNUP_MAX: int = 5

    # ------------------------------------------------------------ validators
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Allow CORS_ORIGINS to be given as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        """Resolve a relative SQLite path against backend/, not the process cwd.

        Otherwise a server started from the repo root and a script run from
        backend/ silently open two different database files.
        """
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value
        raw = value[len(prefix):]
        if not raw or raw.startswith(":memory:") or raw.startswith("file:"):
            return value
        if Path(raw).is_absolute() or raw.startswith("/"):
            return value
        return prefix + (BACKEND_ROOT / raw).resolve().as_posix()

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    # -------------------------------------------------------------- helpers
    @property
    def model_file(self) -> Path:
        """Absolute path to the serialised ML pipeline."""
        return self._resolve(self.MODEL_PATH)

    @property
    def metrics_file(self) -> Path:
        return self._resolve(self.MODEL_METRICS_PATH)

    @property
    def importance_file(self) -> Path:
        return self._resolve(self.MODEL_IMPORTANCE_PATH)

    @property
    def forecast_model_file(self) -> Path:
        return self._resolve(self.FORECAST_MODEL_PATH)

    @property
    def forecast_metrics_file(self) -> Path:
        return self._resolve(self.FORECAST_METRICS_PATH)

    @property
    def dataset_file(self) -> Path:
        return self._resolve(self.DATASET_PATH)

    @property
    def qr_passport_base(self) -> str:
        return f"{self.QR_BASE_URL.rstrip('/')}{self.QR_PASSPORT_PATH}"

    @staticmethod
    def _resolve(raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else (BACKEND_ROOT / path)


def _apply_secrets_provider(instance: "Settings") -> None:
    """Override the sensitive fields a configured Vault actually returns.

    A no-op with the default ``EnvSecretsProvider`` - ``.get()`` on it just
    reads back the same environment variable pydantic-settings already used,
    so this changes nothing unless VAULT_ADDR/VAULT_TOKEN are set. See
    app.core.secrets for what is and is not sourced this way yet.
    """
    from app.core.secrets import EnvSecretsProvider, get_secrets_provider

    provider = get_secrets_provider()
    if isinstance(provider, EnvSecretsProvider):
        return
    instance.SECRET_KEY = provider.get("SECRET_KEY", instance.SECRET_KEY)
    instance.SMTP_PASSWORD = provider.get("SMTP_PASSWORD", instance.SMTP_PASSWORD)
    instance.SMTP_USERNAME = provider.get("SMTP_USERNAME", instance.SMTP_USERNAME)
    instance.KONE_CLIENT_SECRET = provider.get("KONE_CLIENT_SECRET", instance.KONE_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton settings object."""
    instance = Settings()
    _apply_secrets_provider(instance)
    return instance


settings = get_settings()

# Ensure data/model directories exist so first-run scripts never fail.
for _directory in (
    settings.model_file.parent,
    settings.dataset_file.parent,
    BACKEND_ROOT / "data" / "processed",
):
    os.makedirs(_directory, exist_ok=True)
