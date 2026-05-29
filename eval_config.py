import os
from dataclasses import dataclass, field
from pathlib import Path

# Pricing per 1,000,000 (1M) tokens: (input_cost_usd, output_cost_usd)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI latest models
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.5-pro": (30.00, 180.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-pro": (30.00, 180.00),

    # OpenAI GPT-5
    "gpt-5.2-pro": (21.00, 168.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5-pro": (15.00, 120.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),

    # OpenAI GPT-4.1
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),

    # OpenAI GPT-4o
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-2024-05-13": (5.00, 15.00),

    # OpenAI o-series Reasoning Models
    "o4-mini": (1.10, 4.40),
    "o3-pro": (20.00, 80.00),
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o1-pro": (150.00, 600.00),
    "o1": (15.00, 60.00),
    "o1-mini": (1.10, 4.40),

    # OpenAI Legacy GPT-4
    "gpt-4-turbo-2024-04-09": (10.00, 30.00),
    "gpt-4-0125-preview": (10.00, 30.00),
    "gpt-4-1106-preview": (10.00, 30.00),
    "gpt-4-1106-vision-preview": (10.00, 30.00),
    "gpt-4-0613": (30.00, 60.00),
    "gpt-4-0314": (30.00, 60.00),
    "gpt-4-32k": (60.00, 120.00),

    # OpenAI Legacy GPT-3.5
    "gpt-3.5-turbo-1106": (1.00, 2.00),
    "gpt-3.5-turbo-0613": (1.50, 2.00),
    "gpt-3.5-turbo-0125": (0.50, 1.50),
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-0301": (1.50, 2.00),
    "gpt-3.5-turbo-instruct": (1.50, 2.00),
    "gpt-3.5-turbo-16k-0613": (3.00, 4.00),

    # OpenAI Legacy Base Models
    "davinci-002": (2.00, 2.00),
    "babbage-002": (0.40, 0.40),

    # Google Gemini Models
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash": (1.50, 9.00),

    # Anthropic Claude Models
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-3-5": (0.80, 4.00),
}


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
    llm_reasoning_effort: str | None = None

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

    # Model costs dictionary mapping model_name -> (input_cost_per_1M, output_cost_per_1M)
    model_pricing: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(MODEL_PRICING)
    )

