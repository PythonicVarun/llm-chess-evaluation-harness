#!/usr/bin/env python3
"""
Stateful MCP server that manages a single chess game per session.
Exposes tools for board state inspection, move validation, move execution,
game status reporting, and PGN export.

Run directly via stdio (used as a subprocess by the harness):
    python chess_mcp_server.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any

import chess
import chess.pgn
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
log = logging.getLogger("chess_mcp_server")

# Global game state (one board per server process / session)
_board: chess.Board = chess.Board()
_move_history_san: list[str] = []  # SAN strings for human-readable history


# Helper utilities


def _parse_move(board: chess.Board, move_str: str) -> chess.Move | None:
    """
    Try to parse *move_str* as UCI first, then as SAN.
    Returns a legal chess.Move or None.
    """
    s = move_str.strip()
    # UCI  e.g. "e2e4", "g1f3", "e7e8q"
    try:
        m = chess.Move.from_uci(s)
        if m in board.legal_moves:
            return m
    except (ValueError, chess.InvalidMoveError):
        pass
    # SAN  e.g. "e4", "Nf3", "O-O", "Qxd5+"
    try:
        m = board.parse_san(s)
        if m in board.legal_moves:
            return m
    except (ValueError, chess.AmbiguousMoveError, chess.IllegalMoveError):
        pass
    return None


def _board_snapshot(board: chess.Board) -> dict:
    """Return a rich JSON-serialisable snapshot of the current position."""
    legal: list[dict] = []
    for m in board.legal_moves:
        try:
            san = board.san(m)
        except Exception:
            san = "?"
        legal.append({"uci": m.uci(), "san": san})

    outcome = board.outcome()
    winner = None
    if outcome is not None:
        winner = (
            "white"
            if outcome.winner is True
            else "black" if outcome.winner is False else "draw"
        )

    return {
        "fen": board.fen(),
        "ascii_board": str(board),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "fullmove_number": board.fullmove_number,
        "halfmove_clock": board.halfmove_clock,
        "is_check": board.is_check(),
        "is_checkmate": board.is_checkmate(),
        "is_stalemate": board.is_stalemate(),
        "is_insufficient_material": board.is_insufficient_material(),
        "is_game_over": board.is_game_over(),
        "legal_moves": legal,
        "move_count": len(_move_history_san),
        "move_history_san": _move_history_san.copy(),
        "winner": winner,
    }


# MCP server definition
app = Server("chess-mcp-server")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_board_state",
            description=(
                "Return the full current board state: FEN string, ASCII diagram, "
                "whose turn it is, all legal moves (UCI + SAN), move history, "
                "and game-over flags."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="validate_move",
            description=(
                "Check whether a proposed move is legal WITHOUT applying it. "
                "Accepts UCI notation (e2e4) or SAN notation (e4, Nf3, O-O)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "move": {
                        "type": "string",
                        "description": "Move string in UCI or SAN notation",
                    }
                },
                "required": ["move"],
            },
        ),
        types.Tool(
            name="make_move",
            description=(
                "Apply a legal move to the board. Accepts UCI or SAN notation. "
                "Returns the updated board state after the move. "
                "Returns an error dict if the move is illegal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "move": {
                        "type": "string",
                        "description": "Move string in UCI or SAN notation",
                    }
                },
                "required": ["move"],
            },
        ),
        types.Tool(
            name="get_game_status",
            description=(
                "Return a concise game-status object: is_game_over, "
                "termination reason, winner, and current check state."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="reset_game",
            description="Reset the board to the standard starting position.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="export_pgn",
            description="Export the complete game in PGN format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "white_name": {
                        "type": "string",
                        "description": "White player name",
                    },
                    "black_name": {
                        "type": "string",
                        "description": "Black player name",
                    },
                    "event": {
                        "type": "string",
                        "description": "Tournament / event name",
                    },
                    "site": {"type": "string", "description": "Site / location"},
                    "round": {"type": "string", "description": "Round number"},
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    global _board, _move_history_san

    # get_board_state
    if name == "get_board_state":
        snap = _board_snapshot(_board)
        return [types.TextContent(type="text", text=json.dumps(snap, indent=2))]

    # validate_move
    elif name == "validate_move":
        move_str = arguments.get("move", "").strip()
        move = _parse_move(_board, move_str)
        if move:
            result = {
                "valid": True,
                "uci": move.uci(),
                "san": _board.san(move),
                "message": f"'{move_str}' is a legal move.",
            }
        else:
            # Give back a few legal alternatives to help the caller
            sample = [
                {"uci": m.uci(), "san": _board.san(m)}
                for m in list(_board.legal_moves)[:8]
            ]
            result = {
                "valid": False,
                "uci": None,
                "san": None,
                "message": f"'{move_str}' is NOT a legal move in this position.",
                "sample_legal_moves": sample,
            }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # make_move
    elif name == "make_move":
        move_str = arguments.get("move", "").strip()
        move = _parse_move(_board, move_str)
        if move is None:
            sample = [
                {"uci": m.uci(), "san": _board.san(m)}
                for m in list(_board.legal_moves)[:8]
            ]
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": False,
                            "error": f"Illegal or unrecognised move: '{move_str}'",
                            "sample_legal_moves": sample,
                        },
                        indent=2,
                    ),
                )
            ]

        san = _board.san(move)
        _board.push(move)
        _move_history_san.append(san)

        snap = _board_snapshot(_board)
        snap["success"] = True
        snap["applied_move_uci"] = move.uci()
        snap["applied_move_san"] = san
        return [types.TextContent(type="text", text=json.dumps(snap, indent=2))]

    # get_game_status
    elif name == "get_game_status":
        outcome = _board.outcome()
        termination = None
        winner = None
        if outcome:
            termination = str(outcome.termination.name)
            winner = (
                "white"
                if outcome.winner is True
                else "black" if outcome.winner is False else "draw"
            )
        status = {
            "is_game_over": _board.is_game_over(),
            "is_checkmate": _board.is_checkmate(),
            "is_stalemate": _board.is_stalemate(),
            "is_insufficient_material": _board.is_insufficient_material(),
            "is_seventyfive_moves": _board.is_seventyfive_moves(),
            "is_fivefold_repetition": _board.is_fivefold_repetition(),
            "is_check": _board.is_check(),
            "turn": "white" if _board.turn == chess.WHITE else "black",
            "termination": termination,
            "winner": winner,
            "result_string": _board.result(),
            "fullmove_number": _board.fullmove_number,
        }
        return [types.TextContent(type="text", text=json.dumps(status, indent=2))]

    # reset_game
    elif name == "reset_game":
        _board = chess.Board()
        _move_history_san.clear()
        return [
            types.TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": True,
                        "message": "Board reset to starting position.",
                        "fen": _board.fen(),
                    }
                ),
            )
        ]

    # export_pgn
    elif name == "export_pgn":
        game = chess.pgn.Game()
        game.headers["Event"] = arguments.get("event", "LLM vs Stockfish Evaluation")
        game.headers["Site"] = arguments.get("site", "Local")
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = arguments.get("round", "1")
        game.headers["White"] = arguments.get("white_name", "LLM")
        game.headers["Black"] = arguments.get("black_name", "Stockfish")
        game.headers["Result"] = _board.result()

        # Replay the full move stack into the PGN tree
        node = game
        temp = chess.Board()
        for move in _board.move_stack:
            node = node.add_variation(move)
            temp.push(move)

        exporter = chess.pgn.StringExporter(
            headers=True, variations=False, comments=False
        )
        pgn_text = game.accept(exporter)
        return [types.TextContent(type="text", text=pgn_text)]

    # Unknown
    return [
        types.TextContent(
            type="text", text=json.dumps({"error": f"Unknown tool: '{name}'"})
        )
    ]


# Entry point
async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_main())
