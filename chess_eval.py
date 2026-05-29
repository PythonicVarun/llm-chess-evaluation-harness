#!/usr/bin/env python3
"""
Background evaluation harness: any OpenAI-compatible LLM vs Stockfish,
mediated by a stateful chess MCP server.

Live dashboard
---------------------
While a game is running you see a full-terminal display that refreshes
after every half-move:

  ╔══ ♟ LLM Chess Evaluation │ Game 1/3 │ gpt-4o-mini (W) vs SF-1500 ══╗
  ║                                                                     ║
  ║   r n b q k b n r   │  #   White       Black                        ║
  ║   p p p p . p p p   │  1.  e4          e5                           ║
  ║   . . . . . . . .   │  2.  Nf3         Nc6                          ║
  ║   . . . . p . . .   │  3.  Bb5         a6                           ║
  ║   . . . . P . . .   │                                               ║
  ║   . . N . . . . .   │  ⠿  Asking gpt-4o-mini for move 4...          ║
  ║   P P P P . P P P   │                                               ║
  ║   R . B Q K B N R   │  Plies: 6  │  Illegal attempts: 0             ║
  ║                                                                     ║
  ╚═════════════════════════════════════════════════════════════════════╝

A spinner appears between moves so you can tell the process is alive even
when the LLM API is taking a few seconds.
"""

import asyncio
import json
import logging
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from rich import box as rbox
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from eval_config import EvalConfig

load_dotenv()

# Logging
log = logging.getLogger("harness")
console = Console(highlight=False)


def _setup_logging(level: str, log_file: str = "harness.log") -> None:
    """
    Send log records to a file (never to stdout/stderr) so they don't
    interfere with the Rich live display.
    """
    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(fh)


@dataclass
class GameResult:
    """Summary of a completed game."""

    game_index: int
    result_string: str  # "1-0" / "0-1" / "1/2-1/2" / "*"
    termination: str | None
    winner: str | None  # "white" / "black" / "draw" / None
    llm_color: str
    total_plies: int
    llm_illegal_attempts: int
    elapsed_seconds: float
    pgn_path: Path | None


@dataclass
class _DisplayState:
    """Mutable snapshot used by GameDisplay.render()."""

    game_index: int = 1
    total_games: int = 1
    board_str: str = ""
    turn: str = "white"
    move_num: int = 1
    is_check: bool = False
    moves_san: list = field(default_factory=list)  # flat SAN list
    status: str = "Initialising…"
    status_style: str = "yellow"
    plies: int = 0
    illegal: int = 0
    result: str = ""
    elapsed: float = 0.0


class GameDisplay:
    """
    Wraps a Rich Live context and exposes simple update methods that the
    game loop calls after every event (move applied, waiting for LLM, etc.).
    """

    def __init__(self, cfg: EvalConfig, total_games: int) -> None:
        self._cfg = cfg
        self._state = _DisplayState(total_games=total_games)
        self._live = Live(
            self._render(),
            console=console,
            refresh_per_second=8,
            transient=False,
        )

    def __enter__(self):
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        self._live.__exit__(*args)

    def new_game(self, game_index: int) -> None:
        s = self._state
        s.game_index = game_index
        s.board_str = ""
        s.turn = "white"
        s.move_num = 1
        s.is_check = False
        s.moves_san = []
        s.plies = 0
        s.illegal = 0
        s.result = ""
        s.elapsed = 0.0
        self.set_status(f"Game {game_index} starting…", "cyan")

    def update_from_state(self, state: dict, plies: int, illegal: int) -> None:
        s = self._state
        s.board_str = state.get("ascii_board", "")
        s.turn = state.get("turn", "white")
        s.move_num = state.get("fullmove_number", 1)
        s.is_check = state.get("is_check", False)
        s.moves_san = state.get("move_history_san", [])
        s.plies = plies
        s.illegal = illegal
        self._refresh()

    def set_status(self, msg: str, style: str = "yellow") -> None:
        self._state.status = msg
        self._state.status_style = style
        self._refresh()

    def set_result(self, result_str: str, elapsed: float) -> None:
        self._state.result = result_str
        self._state.elapsed = elapsed
        self._refresh()

    # Internal render
    def _refresh(self) -> None:
        self._live.update(self._render())

    def _render(self):
        s = self._cfg
        st = self._state
        llm_is_white = s.llm_color.lower() == "white"

        # Header title
        llm_side = "WHITE" if llm_is_white else "BLACK"
        sf_side = "BLACK" if llm_is_white else "WHITE"
        title = (
            f"[bold cyan]♟  LLM Chess Evaluation[/bold cyan]"
            f"  │  Game [bold]{st.game_index}/{st.total_games}[/bold]"
            f"  │  [green]{s.llm_model} ({llm_side})[/green]"
            f"  vs  [red]Stockfish {s.stockfish_elo} ({sf_side})[/red]"
        )

        # Board panel
        if st.board_str:
            board_lines = st.board_str.splitlines()
            # Colour rank labels and pieces for readability
            coloured: list[str] = []
            for line in board_lines:
                coloured.append(line)
            board_text = Text("\n".join(coloured), style="bold white")
        else:
            board_text = Text("(waiting for first move…)", style="dim")

        check_tag = "  [bold red]⚠ CHECK[/bold red]" if st.is_check else ""
        board_title = (
            f"[bold]Move {st.move_num}  │  "
            f"{'[green]▶ WHITE[/green]' if st.turn == 'white' else '[yellow]▶ BLACK[/yellow]'}"
            f" to move[/bold]{check_tag}"
        )
        board_border = (
            "red" if st.is_check else ("green" if st.turn == "white" else "yellow")
        )
        board_panel = Panel(
            board_text,
            title=board_title,
            border_style=board_border,
            padding=(0, 1),
        )

        # Move-history table
        history = st.moves_san
        move_table = Table(
            box=rbox.SIMPLE_HEAD,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
            expand=True,
        )
        move_table.add_column("#", style="dim", width=4, no_wrap=True)
        move_table.add_column("White", style="bright_white", width=10, no_wrap=True)
        move_table.add_column("Black", style="bright_yellow", width=10, no_wrap=True)

        # Build pairs; only show the last 14 to avoid overflow
        pairs: list[tuple[str, str]] = []
        for i in range(0, len(history), 2):
            w = history[i]
            b = history[i + 1] if i + 1 < len(history) else ""
            pairs.append((w, b))

        visible = pairs[-14:] if len(pairs) > 14 else pairs
        start_num = len(pairs) - len(visible) + 1
        last_row_idx = len(visible) - 1

        for row_i, (w, b) in enumerate(visible):
            # Highlight the most recent move pair
            if row_i == last_row_idx:
                w_cell = Text.from_markup(f"[bold bright_white]{w}[/bold bright_white]")
                b_cell = (
                    Text.from_markup(f"[bold bright_yellow]{b}[/bold bright_yellow]")
                    if b
                    else Text("")
                )
            else:
                w_cell = Text(w)
                b_cell = Text(b)
            move_table.add_row(str(start_num + row_i) + ".", w_cell, b_cell)

        # Status line below the move table
        status_text = Text.from_markup(f"\n{st.status}", style=st.status_style)

        # Stats footer
        elapsed_str = f"{st.elapsed:.1f}s" if st.elapsed else "…"
        stats_text = Text(
            f"\nPlies: {st.plies}   Illegal attempts: {st.illegal}   "
            f"Elapsed: {elapsed_str}",
            style="dim",
        )

        moves_panel = Panel(
            Group(move_table, status_text, stats_text),
            title="[bold]Move History[/bold]",
            border_style="blue",
            padding=(0, 1),
        )

        # Result banner (shown when game over)
        result_group: list = [
            Columns([board_panel, moves_panel], equal=True, expand=True)
        ]
        if st.result:
            result_text = Text(
                f"  ✔  Game {st.game_index} finished:  {st.result}",
                style="bold green",
                justify="center",
            )
            result_group.append(result_text)

        return Panel(
            Group(*result_group),
            title=title,
            border_style="cyan",
            padding=(0, 1),
        )


# MCP helper
async def mcp_call(session: ClientSession, tool: str, **kwargs: Any) -> dict:
    result = await session.call_tool(tool, arguments=kwargs)
    raw = result.content[0].text if result.content else "{}"  # type: ignore
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


# LLM client factory
def _build_llm_client(cfg: EvalConfig) -> AsyncOpenAI:
    kwargs: dict[str, Any] = {"api_key": cfg.api_key or "no-key-needed"}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url

    return AsyncOpenAI(**kwargs)


# LLM move prompting
_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a chess engine participating in an automated evaluation.
    You will be given the current board state and must respond with exactly
    one move in UCI notation (e.g. "e2e4", "g1f3", "e7e8q" for promotion).

    Strict rules:
    - Respond with a single JSON object: {"move": "<uci_string>", "reason": "<one sentence>"}
    - The move MUST appear in the provided legal_moves list.
    - Do NOT include any text outside the JSON object.
    - Do NOT wrap the JSON in markdown code fences.
    - For pawn promotions always include the piece suffix:
        queen → e7e8q  rook → e7e8r  bishop → e7e8b  knight → e7e8n
    - If you are in check you must play a move that escapes check.
""")


def _build_user_prompt(state: dict, llm_color: str, attempt: int) -> str:
    legal_uci = [m["uci"] for m in state.get("legal_moves", [])]
    legal_san = [m["san"] for m in state.get("legal_moves", [])]
    history = state.get("move_history_san", [])

    paired: list[str] = []
    for i in range(0, len(history), 2):
        w = history[i]
        b = history[i + 1] if i + 1 < len(history) else "..."
        paired.append(f"{i // 2 + 1}. {w} {b}")
    move_history_str = "  ".join(paired) if paired else "(game start)"

    check_notice = (
        "  *** YOU ARE IN CHECK — you must escape check ***"
        if state.get("is_check")
        else ""
    )
    retry_notice = (
        (
            f"\n  [Attempt {attempt + 1}: your previous move was ILLEGAL. "
            "You MUST pick a different move from the legal_moves list below.]"
        )
        if attempt > 0
        else ""
    )

    uci_display = ", ".join(legal_uci[:40]) + ("  [...]" if len(legal_uci) > 40 else "")
    san_display = ", ".join(legal_san[:40]) + ("  [...]" if len(legal_san) > 40 else "")

    return textwrap.dedent(f"""\
        You are playing as {llm_color.upper()}.
        {retry_notice}
        Move number : {state.get("fullmove_number", "?")}  \
Plies played : {state.get("move_count", "?")}
        {check_notice}

        Board (white pieces UPPERCASE, black pieces lowercase):
        {state.get("ascii_board", "")}

        FEN : {state.get("fen", "")}

        Move history : {move_history_str}

        Legal moves ({len(legal_uci)} total):
          UCI : {uci_display}
          SAN : {san_display}

        Respond with JSON only:
        {{"move": "<uci>", "reason": "<one sentence>"}}
    """)


def _parse_llm_response(raw: str) -> tuple[str | None, str]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines[1:] if l.strip() != "```").strip()
    try:
        parsed = json.loads(text)
        uci = parsed.get("move", "").strip()
        reason = parsed.get("reason", "")
        return (uci or None), reason
    except (json.JSONDecodeError, AttributeError):
        pass
    for tok in text.split():
        tok = tok.strip('",.')
        if (
            4 <= len(tok) <= 5
            and tok[0].isalpha()
            and tok[1].isdigit()
            and tok[2].isalpha()
            and tok[3].isdigit()
        ):
            return tok, "(extracted from malformed response)"
    return None, raw


async def _ask_llm_for_move(
    client: AsyncOpenAI,
    cfg: EvalConfig,
    state: dict,
    llm_color: str,
    attempt: int,
    display: GameDisplay,
    move_num: int,
) -> tuple[str | None, str]:
    # Show spinner in the status line while we wait for the API
    display.set_status(
        f"⠿  Asking [bold]{cfg.llm_model}[/bold] for move {move_num}"
        + (f"  (retry {attempt + 1})" if attempt > 0 else "")
        + "…",
        style="yellow",
    )

    user_msg = _build_user_prompt(state, llm_color, attempt)
    log.debug("LLM prompt (attempt %d):\n%s", attempt, user_msg)

    response = await client.chat.completions.create(
        model=cfg.llm_model,
        max_tokens=cfg.llm_max_tokens,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    raw_text = (
        (response.choices[0].message.content or "").strip() if response.choices else ""
    )
    log.debug("LLM raw response: %s", raw_text)

    uci, reason = _parse_llm_response(raw_text)
    if uci is None:
        log.warning("Could not parse a UCI move from: %s", raw_text)
    return uci, reason


# Single-game orchestration
async def play_one_game(
    session: ClientSession,
    llm_client: AsyncOpenAI,
    engine: chess.engine.UciProtocol,
    cfg: EvalConfig,
    game_index: int,
    display: GameDisplay,
) -> GameResult:

    llm_is_white = cfg.llm_color.lower() == "white"
    llm_illegal = 0
    ply = 0
    t_start = time.perf_counter()

    display.new_game(game_index)
    log.info("=" * 60)
    log.info(
        "GAME %d  LLM=%s  Stockfish=%s  ELO=%d  model=%s",
        game_index,
        "WHITE" if llm_is_white else "BLACK",
        "BLACK" if llm_is_white else "WHITE",
        cfg.stockfish_elo,
        cfg.llm_model,
    )
    log.info("=" * 60)

    await mcp_call(session, "reset_game")

    # Main game loop
    while True:
        state = await mcp_call(session, "get_board_state")
        display.update_from_state(state, ply, llm_illegal)

        if state.get("is_game_over"):
            log.info("Game-over flag set.")
            break

        if ply >= cfg.max_plies:
            log.info("Max plies (%d) reached — adjudicated draw.", cfg.max_plies)
            break

        turn = state.get("turn", "white")
        is_llm_turn = (turn == "white" and llm_is_white) or (
            turn == "black" and not llm_is_white
        )
        move_num = state.get("fullmove_number", "?")

        #  LLM turn
        if is_llm_turn:
            applied = False

            for attempt in range(cfg.max_move_retries):
                uci_candidate, reason = await _ask_llm_for_move(
                    llm_client,
                    cfg,
                    state,
                    cfg.llm_color,
                    attempt,
                    display,
                    move_num,
                )

                if not uci_candidate:
                    log.warning("[attempt %d] LLM gave no parseable move.", attempt + 1)
                    display.set_status(
                        f"⚠  No parseable move from LLM (attempt {attempt + 1})", "red"
                    )
                    llm_illegal += 1
                    continue

                # Validate (non-destructive)
                val = await mcp_call(session, "validate_move", move=uci_candidate)
                if not val.get("valid"):
                    log.warning(
                        "[attempt %d] Illegal: '%s'  %s",
                        attempt + 1,
                        uci_candidate,
                        val.get("message", ""),
                    )
                    display.set_status(
                        f"⚠  Illegal move [bold]{uci_candidate}[/bold]"
                        f" (attempt {attempt + 1}) — retrying…",
                        "red",
                    )
                    llm_illegal += 1
                    state = await mcp_call(session, "get_board_state")
                    display.update_from_state(state, ply, llm_illegal)
                    continue

                # Apply
                result = await mcp_call(session, "make_move", move=uci_candidate)
                if result.get("success"):
                    san = result.get("applied_move_san", uci_candidate)
                    log.info(
                        "Move %-3s  LLM [%s]  %-8s  %s",
                        move_num,
                        turn.upper()[:1],
                        san,
                        reason[:80],
                    )
                    display.set_status(
                        f"✔  LLM played [bold]{san}[/bold]  — {reason[:70]}",
                        "green",
                    )
                    applied = True
                    break
                else:
                    log.warning("make_move rejected '%s': %s", uci_candidate, result)
                    llm_illegal += 1
                    state = await mcp_call(session, "get_board_state")
                    display.update_from_state(state, ply, llm_illegal)

            if not applied:
                log.error("LLM exhausted %d retries — forfeit.", cfg.max_move_retries)
                display.set_status(
                    f"✘  LLM forfeited after {cfg.max_move_retries} failed attempts",
                    "red",
                )
                legal = state.get("legal_moves", [])
                if legal:
                    await mcp_call(session, "make_move", move=legal[0]["uci"])
                break

        #  Stockfish turn
        else:
            display.set_status("⠿  Stockfish is thinking…", "cyan")
            fen = state.get("fen", chess.STARTING_FEN)
            tmp_board = chess.Board(fen)

            try:
                sf_result = await engine.play(
                    tmp_board,
                    chess.engine.Limit(time=cfg.stockfish_think_time),
                )
                sf_uci = sf_result.move.uci()  # type: ignore
            except Exception as exc:
                log.error("Stockfish error: %s", exc)
                display.set_status(f"✘  Stockfish error: {exc}", "red")
                break

            result = await mcp_call(session, "make_move", move=sf_uci)
            if result.get("success"):
                san = result.get("applied_move_san", sf_uci)
                log.info("Move %-3s  SF  [%s]  %s", move_num, turn.upper()[:1], san)
                display.set_status(f"✔  Stockfish played [bold]{san}[/bold]", "cyan")
            else:
                log.error("Stockfish move '%s' rejected by MCP: %s", sf_uci, result)
                display.set_status(f"✘  Stockfish move rejected: {result}", "red")
                break

        ply += 1

        # Refresh board after every completed half-move
        state = await mcp_call(session, "get_board_state")
        display.update_from_state(state, ply, llm_illegal)

    # Final status
    elapsed = time.perf_counter() - t_start
    status = await mcp_call(session, "get_game_status")
    result_str = status.get("result_string", "*")

    log.info(
        "Result: %s  Termination: %s  Plies: %d  Illegal: %d  Time: %.1fs",
        result_str,
        status.get("termination", "n/a"),
        ply,
        llm_illegal,
        elapsed,
    )

    display.set_result(
        f"{result_str}  │  {status.get('termination') or 'max plies'}  │  "
        f"{elapsed:.1f}s  │  {llm_illegal} illegal attempt(s)",
        elapsed,
    )

    # Export PGN
    llm_is_white = cfg.llm_color.lower() == "white"
    white_name = cfg.llm_model if llm_is_white else f"Stockfish ELO{cfg.stockfish_elo}"
    black_name = f"Stockfish ELO{cfg.stockfish_elo}" if llm_is_white else cfg.llm_model

    pgn_data = await mcp_call(
        session,
        "export_pgn",
        white_name=white_name,
        black_name=black_name,
        event="LLM Chess Evaluation",
        site="Local",
        round=str(game_index),
    )
    pgn_text = pgn_data.get("raw") or pgn_data.get("text") or str(pgn_data)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pgn_path = cfg.output_dir / f"game_{game_index:03d}_{ts}.pgn"
    pgn_path.write_text(pgn_text, encoding="utf-8")
    log.info("PGN saved → %s", pgn_path)

    return GameResult(
        game_index=game_index,
        result_string=result_str,
        termination=status.get("termination"),
        winner=status.get("winner"),
        llm_color=cfg.llm_color,
        total_plies=ply,
        llm_illegal_attempts=llm_illegal,
        elapsed_seconds=elapsed,
        pgn_path=pgn_path,
    )


# Summary table (printed after Live exits)
def _print_summary(results: list[GameResult], llm_color: str) -> None:
    sf_color = "black" if llm_color == "white" else "white"
    llm_wins = sum(1 for r in results if r.winner == llm_color)
    sf_wins = sum(1 for r in results if r.winner == sf_color)
    draws = sum(1 for r in results if r.winner == "draw")
    total_ill = sum(r.llm_illegal_attempts for r in results)
    total_sec = sum(r.elapsed_seconds for r in results)

    tbl = Table(
        title=f"[bold cyan]Evaluation Summary — {len(results)} game(s)[/bold cyan]",
        box=rbox.DOUBLE_EDGE,
        show_header=True,
        header_style="bold",
        title_style="bold cyan",
    )
    tbl.add_column("#", style="dim", width=5, justify="right")
    tbl.add_column("Result", style="bold white", width=10)
    tbl.add_column("Plies", justify="right", width=6)
    tbl.add_column("Termination", style="dim", width=22)
    tbl.add_column("Illegal", justify="right", width=8)
    tbl.add_column("Time", justify="right", width=8)
    tbl.add_column("PGN file", style="dim", width=30)

    for r in results:
        res_style = (
            "green"
            if r.winner == llm_color
            else "red" if r.winner == sf_color else "yellow"
        )
        tbl.add_row(
            str(r.game_index),
            f"[{res_style}]{r.result_string}[/{res_style}]",
            str(r.total_plies),
            r.termination or "n/a",
            str(r.llm_illegal_attempts),
            f"{r.elapsed_seconds:.1f}s",
            r.pgn_path.name if r.pgn_path else "—",
        )

    tbl.add_section()
    tbl.add_row(
        "[bold]Total[/bold]",
        "",
        str(sum(r.total_plies for r in results)),
        "",
        str(total_ill),
        f"{total_sec:.1f}s",
        "",
    )

    console.print()
    console.print(tbl)
    console.print(
        f"  LLM wins: [green]{llm_wins}[/green]   "
        f"Stockfish wins: [red]{sf_wins}[/red]   "
        f"Draws: [yellow]{draws}[/yellow]"
    )
    console.print("  Detailed logs → [dim]harness.log[/dim]")
    console.print()


# Top-level orchestrator
async def run_evaluation(cfg: EvalConfig) -> list[GameResult]:
    import shutil

    if not cfg.api_key and not cfg.base_url:
        sys.exit(
            "ERROR: No API key found.\n"
            "  Set OPENAI_API_KEY (or LLM_API_KEY) in your environment,\n"
            "  or set api_key in eval_config.py."
        )

    if not shutil.which(cfg.stockfish_path) and not Path(cfg.stockfish_path).is_file():
        sys.exit(
            f"ERROR: Stockfish binary not found at '{cfg.stockfish_path}'.\n"
            "  Install Stockfish and set STOCKFISH_PATH, or edit eval_config.py."
        )

    log.info("LLM endpoint     : %s", cfg.base_url or "OpenAI default")
    log.info("LLM model        : %s", cfg.llm_model)
    log.info("LLM plays        : %s", cfg.llm_color.upper())
    log.info("Stockfish binary : %s", cfg.stockfish_path)
    log.info("Stockfish ELO    : %d", cfg.stockfish_elo)
    log.info("Games to play    : %d", cfg.num_games)
    log.info("Output directory : %s", cfg.output_dir.resolve())

    llm_client = _build_llm_client(cfg)
    server_script = Path(__file__).parent / "chess_mcp_server.py"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        env=None,
    )

    results: list[GameResult] = []

    with GameDisplay(cfg, cfg.num_games) as display:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tool_names = [t.name for t in (await session.list_tools()).tools]
                log.info("MCP session ready. Tools: %s", tool_names)
                display.set_status("MCP server ready — starting Stockfish…", "cyan")

                transport, engine = await chess.engine.popen_uci(cfg.stockfish_path)
                try:
                    await engine.configure(
                        {
                            "UCI_LimitStrength": True,
                            "UCI_Elo": cfg.stockfish_elo,
                        }
                    )
                    log.info("Stockfish engine ready.")
                    display.set_status("Stockfish ready — let's play!", "green")

                    for i in range(1, cfg.num_games + 1):
                        result = await play_one_game(
                            session, llm_client, engine, cfg, i, display
                        )
                        results.append(result)

                        # Brief pause between games so the result is readable
                        if i < cfg.num_games:
                            await asyncio.sleep(2)

                finally:
                    await engine.quit()
                    transport.close()
                    log.info("Stockfish engine shut down.")

    _print_summary(results, cfg.llm_color)
    return results


# CLI
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run LLM vs Stockfish chess evaluation (OpenAI-compatible API).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--color", choices=["white", "black"], default=None)
    parser.add_argument("--games", type=int, default=None)
    parser.add_argument("--elo", type=int, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--base-url", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--stockfish", type=str, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None
    )
    args = parser.parse_args()

    cfg = EvalConfig()
    if args.color:
        cfg.llm_color = args.color
    if args.games:
        cfg.num_games = args.games
    if args.elo:
        cfg.stockfish_elo = args.elo
    if args.model:
        cfg.llm_model = args.model
    if args.base_url:
        cfg.base_url = args.base_url
    if args.api_key:
        cfg.api_key = args.api_key
    if args.output_dir:
        cfg.output_dir = Path(args.output_dir)
    if args.stockfish:
        cfg.stockfish_path = args.stockfish
    if args.max_tokens:
        cfg.llm_max_tokens = args.max_tokens

    _setup_logging(args.log_level or cfg.log_level)
    asyncio.run(run_evaluation(cfg))


if __name__ == "__main__":
    main()
