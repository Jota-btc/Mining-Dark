"""Pydantic v2 settings — loads from YAML file + environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ScannerConfig(BaseModel):
    mode: str = "random"  # "random" | "hd"
    workers: int = 10
    queue_size: int = 500
    address_types: list[str] = ["p2pkh", "p2sh_p2wpkh", "p2wpkh", "p2tr"]
    min_balance_satoshis: int = 0

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in {"random", "hd"}:
            raise ValueError(f"mode must be 'random' or 'hd', got '{v}'")
        return v

    @field_validator("address_types")
    @classmethod
    def validate_address_types(cls, v: list[str]) -> list[str]:
        valid = {"p2pkh", "p2pkh_uncompressed", "p2sh_p2wpkh", "p2wpkh", "p2wsh", "p2tr"}
        for t in v:
            if t not in valid:
                raise ValueError(f"Unknown address type '{t}'. Valid: {valid}")
        return v


class HDWalletConfig(BaseModel):
    derivation_paths: list[str] = [
        "m/44'/0'/0'/0/{i}",
        "m/49'/0'/0'/0/{i}",
        "m/84'/0'/0'/0/{i}",
        "m/86'/0'/0'/0/{i}",
    ]
    child_count: int = 20


class OutputConfig(BaseModel):
    found_wallets_dir: str = "found_wallets"
    save_csv: bool = True
    json_indent: int = 2


class LoggingConfig(BaseModel):
    level: str = "INFO"
    logs_dir: str = "logs"
    rotation: str = "50 MB"
    retention: str = "7 days"


class UIConfig(BaseModel):
    refresh_fps: int = 4
    recent_table_rows: int = 15
    theme: str = "dark"


class Settings(BaseModel):
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    hd_wallet: HDWalletConfig = Field(default_factory=HDWalletConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


def load_settings(config_path: str = "config.yaml") -> Settings:
    """Load settings from a YAML file, falling back to defaults if not found."""
    path = Path(config_path)
    if not path.exists():
        return Settings()

    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return Settings.model_validate(raw)
