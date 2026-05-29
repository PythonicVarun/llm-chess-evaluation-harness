import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalConfig:
    api_key: str = field(
        default_factory=lambda: (
            os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        )
    )

    base_url: str | None = field(
        default_factory=lambda: os.environ.get("LLM_BASE_URL") or None
    )

    llm_model: str = "gpt-4o-mini"

    llm_max_tokens: int = 256

    # Stockfish settings
    stockfish_path: str = field(
        default_factory=lambda: os.environ.get("STOCKFISH_PATH") or "stockfish"
    )
    # Stockfish UCI_Elo limit (1320–3190).  Lower = easier opponent.
    stockfish_elo: int = 1500
    stockfish_think_time: float = 0.1

    # Game / evaluation settings
    llm_color: str = "white"
    num_games: int = 3
    max_move_retries: int = 3
    # Hard cap on total half-moves (plies) before declaring a draw.
    max_plies: int = 200

    # Output settings
    output_dir: Path = field(default_factory=lambda: Path("pgn_output"))
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
