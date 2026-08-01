"""Minimal client for quipqiup.com's browser-facing solver endpoints."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp


BASE_URL = "https://www.quipqiup.com"
REQUEST_TIMEOUT_SECONDS = 120
MAX_POLL_INTERVAL_SECONDS = 3.0


class QuipqiupError(Exception):
    """Raised when quipqiup cannot return a usable solving result."""


@dataclass(frozen=True)
class Solution:
    plaintext: str
    key: tuple[str, ...] | None
    score: float | None


async def solve(ciphertext: str, clues: str = "") -> list[Solution]:
    """Submit one substitution cipher and wait for quipqiup's final result."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request = {
        "ciphertext": ciphertext,
        "clues": clues,
        "mode": "auto",
        "was_auto": True,
        "was_clue": False,
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{BASE_URL}/solve", data=json.dumps(request), headers=headers
            ) as response:
                response.raise_for_status()
                started = await response.json()

            request_id = started.get("id")
            if request_id is None:
                raise QuipqiupError("求解服务没有返回任务编号。")

            interval = _poll_interval(started.get("poll_interval"))
            solutions_by_plaintext: dict[str, Solution] = {}
            while True:
                await asyncio.sleep(interval)
                async with session.post(
                    f"{BASE_URL}/status",
                    data=json.dumps({"id": request_id}),
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    status = await response.json()

                for solution in _parse_solutions(status.get("solutions", [])):
                    previous = solutions_by_plaintext.get(solution.plaintext)
                    if previous is None or _score(solution) > _score(previous):
                        solutions_by_plaintext[solution.plaintext] = solution

                if status.get("last"):
                    return sorted(solutions_by_plaintext.values(), key=_score, reverse=True)
    except asyncio.TimeoutError as exc:
        raise QuipqiupError("求解超时，请稍后重试或补充已知映射。") from exc
    except aiohttp.ClientError as exc:
        raise QuipqiupError("无法连接 quipqiup 求解服务。") from exc


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
        key = (
            tuple(raw_key)
            if isinstance(raw_key, list)
            and len(raw_key) == 26
            and all(isinstance(letter, str) and len(letter) == 1 for letter in raw_key)
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
