"""Scenario B: uses the pydantic 1 location of BaseSettings, which pydantic 2 moved to pydantic-settings."""
from pydantic import BaseSettings


class Settings(BaseSettings):
    environment: str = "dev"
