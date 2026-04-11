"""Configuration for Rekall."""
from pathlib import Path
from dataclasses import dataclass


@dataclass
class RekallConfig:
    data_dir: Path
    db_path: Path
    memory_md_path: Path | None
    model_name: str

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"


def get_config(
    data_dir: Path | None = None,
    memory_md_path: Path | None = None,
) -> RekallConfig:
    """Build config with defaults. Env vars override arguments."""
    import os
    data = Path(os.environ.get("REKALL_DATA_DIR", str(data_dir or Path.home() / ".rekall")))
    data.mkdir(parents=True, exist_ok=True)
    return RekallConfig(
        data_dir=data,
        db_path=data / "rekall.db",
        memory_md_path=memory_md_path,
        model_name="BAAI/bge-small-en-v1.5",
    )
