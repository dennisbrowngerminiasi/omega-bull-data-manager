import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)
class NDJSONServer:
    """Simple NDJSON request/response server for ticker discovery and quotes."""

    def __init__(
        self,
        quote_cache: Dict[str, Dict[str, Any]],
        snapshot_state: Dict[str, int],
        shm_name: Optional[str],
        freshness_window_ms: int = 90_000,
        max_line_bytes: int = 65_536,
        idle_timeout_s: int = 60,
        req_timeout_s: int = 5,
    ):
        self.quote_cache = quote_cache
        self.snapshot_state = snapshot_state
        self.shm_name = shm_name
        self.freshness_window_ms = freshness_window_ms
        self.max_line_bytes = max_line_bytes
        self.idle_timeout_s = idle_timeout_s
        self.req_timeout_s = req_timeout_s

    # ------------------------------------------------------------------
    # Networking helpers
    # ------------------------------------------------------------------
    async def start(self, host: str = "0.0.0.0", port: int = 12345):
        """Start the TCP server and return the server instance."""
        server = await asyncio.start_server(self.handle_client, host, port)
        logger.info("NDJSON quote server listening on %s:%d", host, port)
        return server

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single client connection."""
        peer = writer.get_extra_info("peername")
        logger.info("Client connected: %s", peer)
        try:
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=self.idle_timeout_s)
                except asyncio.TimeoutError:
                    break
                except ValueError:
                    # Raised if the incoming line exceeds the stream limit.
                    await self.send_error(writer, None, "BAD_REQUEST", "Line too long", peer)
                    break
                if not line:
                    break
                if len(line) > self.max_line_bytes:
                    await self.send_error(writer, None, "BAD_REQUEST", "Line too long", peer)
                    continue
                try:
                    decoded = line.decode("utf-8").rstrip()
                    logger.info("recv from %s: %s", peer, decoded)
                    request = json.loads(decoded)
                except Exception:
                    await self.send_error(writer, None, "BAD_REQUEST", "Malformed JSON", peer)
                    continue

                req_id = request.get("id")
                missing = []
                if request.get("v") != 1:
                    missing.append("v")
                if req_id is None:
                    missing.append("id")
                if "type" not in request:
                    missing.append("type")
                if missing:
                    logger.warning("bad request from %s missing %s: %s", peer, missing, request)
                    await self.send_error(
                        writer,
                        req_id,
                        "BAD_REQUEST",
                        "Missing required fields: " + ", ".join(missing),
                        peer,
                        request,
                    )
                    continue

                req_type = request["type"]
                logger.info("handling from %s id=%s type=%s", peer, req_id, req_type)
                start = time.time()
                try:
                    if req_type == "list_tickers":
                        data = list(self.quote_cache.keys())
                        response = {"v": 1, "id": req_id, "type": "response",
                                    "op": "list_tickers", "data": data}
                        await self.send(writer, response, peer)
                    elif req_type == "get_quote":
                        ticker = request.get("ticker")
                        if not ticker:
                            await self.send_error(writer, req_id, "BAD_REQUEST", "Missing ticker", peer, request)
                            continue
                        quote = self.quote_cache.get(ticker)
                        if quote is None:
                            await self.send_error(writer, req_id, "NOT_FOUND", f"Unknown ticker {ticker}", peer, request)
                            continue
                        data = dict(quote)
                        data["ticker"] = ticker
                        now_ms = int(time.time() * 1000)
                        data["stale"] = now_ms - quote.get("ts_epoch_ms", 0) > self.freshness_window_ms
                        response = {"v": 1, "id": req_id, "type": "response",
                                    "op": "get_quote", "data": data}
                        await self.send(writer, response, peer)
                    elif req_type == "get_snapshot_epoch":
                        data = {"epoch": self.snapshot_state.get("epoch", 0),
                                "last_update_ms": self.snapshot_state.get("last_update_ms", 0)}
                        response = {"v": 1, "id": req_id, "type": "response",
                                    "op": "get_snapshot_epoch", "data": data}
                        await self.send(writer, response, peer)
                    elif req_type == "get_shm_name":
                        if self.shm_name is None:
                            await self.send_error(
                                writer,
                                req_id,
                                "NOT_FOUND",
                                "Shared memory not configured",
                                peer,
                                request,
                            )
                        else:
                            data = {"shm_name": self.shm_name}
                            response = {
                                "v": 1,
                                "id": req_id,
                                "type": "response",
                                "op": "get_shm_name",
                                "data": data,
                            }
                            await self.send(writer, response, peer)
                    else:
                        await self.send_error(writer, req_id, "BAD_REQUEST", "Unknown request type", peer, request)
                except Exception as exc:  # pragma: no cover - defensive
                    await self.send_error(writer, req_id, "INTERNAL", str(exc), peer, request)
                finally:
                    latency_ms = int((time.time() - start) * 1000)
                    logger.info("completed id=%s type=%s latency_ms=%d", req_id, req_type, latency_ms)
        finally:
            logger.info("Client disconnected: %s", peer)
            writer.close()
            await writer.wait_closed()

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    async def send(self, writer: asyncio.StreamWriter, message: Dict[str, Any], peer):
        logger.info("send to %s: %s", peer, message)
        writer.write(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()

    async def send_error(
        self,
        writer: asyncio.StreamWriter,
        req_id: Any,
        code: str,
        message: str,
        peer,
        request: Optional[Dict[str, Any]] = None,
    ):
        error_obj = {
            "v": 1,
            "id": req_id,
            "type": "error",
            "error": {"code": code, "message": message},
        }
        logger.warning("error to %s: %s (request=%s)", peer, error_obj, request)
        await self.send(writer, error_obj, peer)
