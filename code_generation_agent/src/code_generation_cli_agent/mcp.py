from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path


class MCPClient:
    """Minimal MCP stdio client using JSON-RPC framing."""

    def __init__(
        self,
        command: list[str],
        repo_path: Path,
        timeout_s: int = 30,
    ):
        self._command = command
        self._repo_path = repo_path
        self._timeout_s = timeout_s
        self._seq = 0
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return

        self._proc = subprocess.Popen(
            self._command,
            cwd=self._repo_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self._request("initialize", {"protocolVersion": "2025-03-26", "clientInfo": {"name": "cca", "version": "1.0.0"}})

    def _write_message(self, payload: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(payload)
        frame = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}"
        self._proc.stdin.write(frame)
        self._proc.stdin.flush()

    def _read_message(self) -> dict:
        assert self._proc is not None and self._proc.stdout is not None
        content_length = 0

        while True:
            line = self._proc.stdout.readline()
            if line == "":
                raise RuntimeError("MCP server closed the stream")
            line = line.strip("\r\n")
            if line == "":
                break
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        if content_length <= 0:
            raise RuntimeError("Invalid MCP frame: missing Content-Length")

        body = self._proc.stdout.read(content_length)
        return json.loads(body)

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._start()
            self._seq += 1
            req_id = self._seq
            self._write_message({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

            while True:
                msg = self._read_message()
                if msg.get("id") != req_id:
                    continue
                if "error" in msg:
                    raise RuntimeError(f"MCP error: {msg['error']}")
                return msg.get("result", {})

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        if not content:
            return ""
        text_blocks = [item.get("text", "") for item in content if item.get("type") == "text"]
        return "\n".join([t for t in text_blocks if t]).strip()

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
        self._proc = None
