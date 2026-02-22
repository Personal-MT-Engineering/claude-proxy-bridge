"""Claude CLI subprocess manager — runs `claude -p` and parses output."""

import asyncio
import json
import logging
import sys
from collections.abc import AsyncGenerator

from .config import settings

logger = logging.getLogger(__name__)


def _build_command(
    prompt: str,
    model_id: str,
    system_prompt: str | None = None,
    max_turns: int | None = None,
    stream: bool = False,
) -> list[str]:
    """Build the claude CLI command list."""
    cli = settings.resolve_claude_cli()
    cmd = [cli, "-p", prompt, "--model", model_id, "--dangerously-skip-permissions"]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])
    if stream:
        cmd.extend(["--output-format", "stream-json"])

    return cmd


def _extract_text_from_ndjson_line(line: str) -> str | None:
    """Parse a single NDJSON line from claude's stream-json output and extract text."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        # Not JSON — might be raw text output
        return line if line else None

    # Claude stream-json format: look for content blocks with text
    msg_type = data.get("type", "")

    # Content block delta with text
    if msg_type == "content_block_delta":
        delta = data.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text", "")

    # Result message with text content
    if msg_type == "result":
        result = data.get("result", "")
        if isinstance(result, str) and result:
            return result

    # Message with content array
    if msg_type == "message":
        content = data.get("content", [])
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            joined = "".join(texts)
            if joined:
                return joined

    return None


async def run_claude(
    prompt: str,
    model_id: str,
    system_prompt: str | None = None,
    max_turns: int | None = None,
) -> str:
    """Run claude CLI and return the full response text."""
    cmd = _build_command(prompt, model_id, system_prompt, max_turns, stream=False)

    logger.info("Running claude CLI: model=%s prompt_len=%d", model_id, len(prompt))
    logger.debug("Command: %s", " ".join(cmd[:6]) + " ...")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # On Windows, prevent console window from appearing
            **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.request_timeout,
        )

        output = stdout.decode("utf-8", errors="replace").strip()
        err_output = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error("Claude CLI exited with code %d: %s", process.returncode, err_output)
            raise RuntimeError(f"Claude CLI error (exit code {process.returncode}): {err_output or output}")

        if err_output:
            logger.debug("Claude CLI stderr: %s", err_output[:500])

        if not output:
            raise RuntimeError("Claude CLI returned empty output")

        logger.info("Claude CLI response: %d chars", len(output))
        return output

    except asyncio.TimeoutError:
        logger.error("Claude CLI timed out after %ds", settings.request_timeout)
        if process:
            process.kill()
            await process.wait()
        raise RuntimeError(f"Claude CLI timed out after {settings.request_timeout}s")


async def stream_claude(
    prompt: str,
    model_id: str,
    system_prompt: str | None = None,
    max_turns: int | None = None,
) -> AsyncGenerator[str, None]:
    """Run claude CLI with stream-json and yield text chunks as they arrive."""
    cmd = _build_command(prompt, model_id, system_prompt, max_turns, stream=True)

    logger.info("Streaming claude CLI: model=%s prompt_len=%d", model_id, len(prompt))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )

    try:
        assert process.stdout is not None

        while True:
            try:
                line_bytes = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=settings.request_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Stream read timed out")
                break

            if not line_bytes:
                # EOF
                break

            line = line_bytes.decode("utf-8", errors="replace")
            text = _extract_text_from_ndjson_line(line)
            if text:
                yield text

        # Wait for process to finish
        await process.wait()

        if process.returncode and process.returncode != 0:
            stderr_bytes = await process.stderr.read() if process.stderr else b""
            err = stderr_bytes.decode("utf-8", errors="replace").strip()
            logger.error("Claude CLI stream exited with code %d: %s", process.returncode, err)

    except Exception:
        process.kill()
        await process.wait()
        raise
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
