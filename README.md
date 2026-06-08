# ♟️ LLM Chess Evaluation Harness

A sophisticated evaluation framework for testing the chess-playing capabilities of Large Language Models (LLMs) against Stockfish. 🤖 The harness uses a Model Context Protocol (MCP) server to maintain secure, stateful chess games and provides a rich live-updating terminal interface. 🖥️

It supports any OpenAI-compatible API endpoint, allowing you to test OpenAI models, Anthropic models (via proxies), or local LLMs (via vLLM, Ollama, etc.). 🌐

## ✨ Features

- **📺 Live Terminal Dashboard:** A beautiful, real-time TUI built with `rich`, displaying the board, move history, side-to-move, and live game status.
- **🛠️ MCP Backend:** Chess state and rules are fully mediated by a local MCP server (`chess_mcp_server.py`), providing robust move validation and state management.
- **🐟 Stockfish Integration:** Test against Stockfish with configurable ELO levels to find the exact rating of your LLM.
- **🛡️ Robust Error Handling:** Automatically detects illegal LLM moves and prompts the LLM to retry, tracking "illegal move attempts" as a metric.
- **💾 PGN Export:** Automatically saves all finished games to standard Portable Game Notation (PGN) files for later review in any chess GUI. Filenames include the model id and Stockfish ELO for easy sorting.

## 📋 Requirements

- **🐍 Python 3.12+**
- **⚙️ Stockfish:** The Stockfish chess engine binary must be installed on your system.
    - _🐧 Ubuntu/Debian:_ `sudo apt install stockfish`
    - _🍎 macOS:_ `brew install stockfish`
    - _🪟 Windows:_ Download from the [Stockfish website](https://stockfishchess.org/download/) and add it to your `PATH`, or specify the path via configuration.
- **🔑 API Key:** An API key for your chosen LLM provider (e.g., OpenAI).

## 🚀 Installation

1. 📥 Clone this repository.
2. 📦 Install the required dependencies:

```bash
pip install -r requirements.txt
# or using uv:
# uv sync
```

3. 🔧 Configure your environment variables. You can create a `.env` file in the project root:

```env
LLM_API_KEY=your_api_key_here
# Optional:
# LLM_BASE_URL=https://api.your-custom-provider.com/v1
# STOCKFISH_PATH=/path/to/custom/stockfish
```

## ⚡ Direct Execution (No Cloning/Installation Required)

You can run the harness or the MCP server directly from the GitHub repository using **`uv`** or **`uvx`** without cloning the project.

### 1. Using `uv run`

Run the evaluation harness command directly:

```bash
uv run --with git+https://github.com/PythonicVarun/llm-chess-evaluation-harness.git eval [options]
```

### 2. Using `uvx` (or `uv tool run`)

Run the evaluation harness:

```bash
uvx --from git+https://github.com/PythonicVarun/llm-chess-evaluation-harness.git eval [options]
```

Or start the standalone MCP Chess server:

```bash
uvx --from git+https://github.com/PythonicVarun/llm-chess-evaluation-harness.git mcp
```

> [!NOTE]
> Make sure your `OPENAI_API_KEY` (or `LLM_API_KEY`) and `STOCKFISH_PATH` environment variables are exported in your terminal before running the direct command.

## 🎮 Usage

Run the evaluation harness using the main script:

```bash
python chess_eval.py
```

By default, this will play a 3-game match using `gpt-4o-mini` as White against Stockfish (1500 ELO) as Black. ⚔️

### 🎛️ Command Line Arguments

You can override the default configuration using CLI arguments:

- `--model <name>`: 🧠 LLM model name (default: `gpt-4o-mini`).
- `--reasoning-effort <low|medium|high>`: 🧠 Reasoning effort for supported models.
- `--color <white|black>`: 🎨 The color the LLM will play (default: `white`).
- `--games <n>`: 🔢 Number of games to play in the match (default: `3`).
- `--elo <n>`: 📈 Stockfish target ELO (default: `1320`).
- `--base-url <url>`: 🔗 Custom OpenAI-compatible endpoint URL.
- `--api-key <key>`: 🗝️ Override the API key explicitly.
- `--stockfish <path>`: 📍 Path to the Stockfish binary.
- `--output-dir <path>`: 📁 Directory to save PGN files (default: `pgn_output`).
- `--temperature <n>`: 🌡️ Model temperature (default: `0.2`).
- `--log-level <DEBUG|INFO|WARNING|ERROR>`: 📝 Set internal logging verbosity (saved to `logs/<model>_elo<stockfish-elo>.log`).

### 💡 Example: Testing a local model via vLLM

If you are running a local model server compatible with the OpenAI API:

```bash
python chess_eval.py --model meta-llama/Meta-Llama-3-8B-Instruct --reasoning-effort medium --base-url http://localhost:8000/v1 --games 5 --elo 1320
```

## 📊 Evaluation Results

Below is a summary of the matches played between various LLM models and Stockfish at different target ELO levels. The table shows the number of wins, losses, draws, total games played, and the resulting win rate for each model at each ELO level.

| Model                     | Reasoning | Stockfish ELO | Wins | Losses | Draws | Total Games | Win Rate |
| :------------------------ | :-------: | :-----------: | :--: | :----: | :---: | :---------: | :------: |
| **gemini-3.5-flash**      |  default  |     2000      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.5**               |   none    |     2000      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.5**               |   none    |     1900      |  0   |   2    |   1   |      3      |   0.0%   |
| **gemini-3.5-flash**      |  default  |     1800      |  1   |   1    |   1   |      3      |  33.3%   |
| **gpt-5.5**               |   none    |     1700      |  0   |   2    |   1   |      3      |   0.0%   |
| **gpt-5.5**               |    low    |     1700      |  0   |   3    |   0   |      3      |   0.0%   |
| **gemini-3.5-flash**      |  default  |     1600      |  1   |   2    |   0   |      3      |  33.3%   |
| **gemini-3.5-flash**      |  default  |     1500      |  2   |   1    |   0   |      3      |  66.7%   |
| **gpt-5.4-mini**          |   high    |     1500      |  0   |   2    |   0   |      2      |   0.0%   |
| **gpt-5.4-nano**          |  default  |     1500      |  0   |   2    |   0   |      2      |   0.0%   |
| **gpt-5.4-nano**          |   none    |     1500      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-nano**          |    low    |     1500      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-nano**          |  medium   |     1500      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.5**               |   none    |     1500      |  0   |   2    |   1   |      3      |   0.0%   |
| **gpt-5.5**               |    low    |     1500      |  1   |   1    |   1   |      3      |  33.3%   |
| **gemini-3.5-flash**      |  default  |     1450      |  1   |   2    |   0   |      3      |  33.3%   |
| **gemini-3.5-flash**      |  default  |     1400      |  1   |   1    |   1   |      3      |  33.3%   |
| **gemini-3.1-flash-lite** |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gemini-3.5-flash**      |  default  |     1320      |  2   |   1    |   0   |      3      |  66.7%   |
| **gpt-4.1**               |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-4.1-mini**          |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-4.1-nano**          |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-4o**                |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-4o-mini**           |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4**               |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-mini**          |  default  |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-mini**          |   none    |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-mini**          |    low    |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-mini**          |  medium   |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-mini**          |   high    |     1320      |  0   |   2    |   1   |      3      |   0.0%   |
| **gpt-5.4-nano**          |  default  |     1320      |  0   |   6    |   0   |      6      |   0.0%   |
| **gpt-5.4-nano**          |   none    |     1320      |  0   |   2    |   1   |      3      |   0.0%   |
| **gpt-5.4-nano**          |    low    |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.4-nano**          |  medium   |     1320      |  0   |   4    |   2   |      6      |   0.0%   |
| **gpt-5.4-nano**          |   high    |     1320      |  0   |   3    |   0   |      3      |   0.0%   |
| **gpt-5.5**               |  default  |     1320      |  3   |   0    |   0   |      3      |  100.0%  |
| **gpt-5.5**               |   none    |     1320      |  0   |   1    |   1   |      2      |   0.0%   |
| **gpt-5.5**               |    low    |     1320      |  1   |   1    |   1   |      3      |  33.3%   |
| **gpt-5.5**               |  medium   |     1320      |  2   |   0    |   1   |      3      |  66.7%   |
| **gpt-5.5**               |   high    |     1320      |  1   |   0    |   0   |      1      |  100.0%  |

## 🪙 Token & Cost Summarization

At the end of each evaluation match, the harness prints a detailed **Token Usage & Cost Summary** in your terminal. This shows the total prompt (input) tokens, completion (output) tokens, and the estimated total cost in USD for the model run.

Model costs are independently stored in `eval_config.py` and are based on the following official developer pricing guides:

- **OpenAI Models**: Pricing is retrieved from the official [OpenAI Developer Pricing](https://developers.openai.com/api/docs/pricing).
- **Google Gemini Models**: Pricing is retrieved from the official [Google Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing).
- **Anthropic Claude Models**: Pricing is retrieved from the official [Anthropic Claude Pricing](https://platform.claude.com/docs/en/about-claude/pricing).

For custom or local models where pricing is not known, the estimated cost defaults to `$0.00000`. You can configure or override custom model costs by editing the `model_pricing` dictionary in `eval_config.py` or overriding it in your custom code.

## 🏗️ Architecture

- 🎬 `chess_eval.py`: The orchestrator and UI layer. It starts the MCP server, initializes Stockfish, queries the LLM for moves, and updates the dashboard.
- ⚙️ `chess_mcp_server.py`: A stateless script running as an MCP server over stdio. It wraps the `python-chess` library, exposing tools to read the board (`get_board_state`), validate moves (`validate_move`), apply moves (`make_move`), and export the game (`export_pgn`).
- 📝 `eval_config.py`: Centralized dataclass for evaluation settings and defaults.

## 📜 License

This project is licensed under the [MIT License](LICENSE). ⚖️
