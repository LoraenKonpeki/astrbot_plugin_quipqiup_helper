"""Minimal client for quipqiup.com's browser-facing solver endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any


BASE_URL = "https://www.quipqiup.com"
REQUEST_TIMEOUT_SECONDS = 120
MAX_POLL_INTERVAL_SECONDS = 3.0
MAX_CONSECUTIVE_POLL_ERRORS = 8
CURL_CONNECT_TIMEOUT_SECONDS = 10
CURL_REQUEST_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)


class QuipqiupError(Exception):
    """Raised when quipqiup cannot return a usable solving result."""


class _RetryableQuipqiupError(Exception):
    """A transient response failure while a task is still being processed."""


@dataclass(frozen=True)
class Solution:
    plaintext: str
    key: tuple[str, ...] | None
    score: float | None


async def solve(ciphertext: str, clues: str = "") -> list[Solution]:
    """Submit one substitution cipher and wait for quipqiup's final result."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request = {
        "ciphertext": ciphertext,
        "clues": clues,
        "mode": "auto",
        "was_auto": True,
        "was_clue": False,
    }

    try:
        started = await _post_json(f"{BASE_URL}/solve", request, headers)
        request_id = started.get("id")
        if request_id is None:
            raise QuipqiupError("求解服务没有返回任务编号。")

        interval = _poll_interval(started.get("poll_interval"))
        deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
        consecutive_errors = 0
        solutions_by_plaintext: dict[str, Solution] = {}
        while True:
            if time.monotonic() >= deadline:
                raise QuipqiupError("求解超时，请稍后重试或补充已知映射。")
            await asyncio.sleep(interval)
            try:
                status = await _post_json(
                    f"{BASE_URL}/status", {"id": request_id}, headers
                )
                consecutive_errors = 0
            except _RetryableQuipqiupError as exc:
                consecutive_errors += 1
                logger.warning("quipqiup status poll failed: %s", exc)
                if consecutive_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                    raise QuipqiupError("求解服务暂时不可用，请稍后重试。") from exc
                continue

            for solution in _parse_solutions(status.get("solutions", [])):
                previous = solutions_by_plaintext.get(solution.plaintext)
                if previous is None or _score(solution) > _score(previous):
                    solutions_by_plaintext[solution.plaintext] = solution

            if status.get("last"):
                return sorted(solutions_by_plaintext.values(), key=_score, reverse=True)
    except _RetryableQuipqiupError as exc:
        logger.warning("quipqiup request failed: %s", exc)
        raise QuipqiupError("求解服务暂时不可用，请稍后重试。") from exc


async def _post_json(url: str, payload: dict, headers: dict) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--connect-timeout",
            str(CURL_CONNECT_TIMEOUT_SECONDS),
            "--max-time",
            str(CURL_REQUEST_TIMEOUT_SECONDS),
            "-H",
            f"Content-Type: {headers['Content-Type']}",
            "--data-binary",
            json.dumps(payload),
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
    except OSError as exc:
        raise _RetryableQuipqiupError(str(exc)) from exc

    if process.returncode != 0:
        detail = (stderr or stdout).decode(errors="replace").strip()[-200:]
        raise _RetryableQuipqiupError(detail or f"curl exited {process.returncode}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise _RetryableQuipqiupError("response was not valid JSON") from exc


def _poll_interval(value: Any) -> float:
    try:
        return min(max(float(value), 0.2), MAX_POLL_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        return 1.0


def _parse_solutions(raw_solutions: list[dict[str, Any]]) -> list[Solution]:
    solutions = []
    for item in raw_solutions:
        plaintext = item.get("plaintext")
        if not isinstance(plaintext, str) or not plaintext.strip():
            continue
        raw_key = item.get("key")
        score = item.get("logp")
        key_chars = raw_key if isinstance(raw_key, str) else raw_key
        key = (
            tuple(key_chars)
            if isinstance(key_chars, (str, list))
            and len(key_chars) == 26
            and all(isinstance(letter, str) and len(letter) == 1 for letter in key_chars)
            else None
        )
        solutions.append(
            Solution(
                plaintext=plaintext.strip(),
                key=key,
                score=score if isinstance(score, (int, float)) else None,
            )
        )
    return solutions


def _score(solution: Solution) -> float:
    return solution.score if solution.score is not None else float("-inf")
