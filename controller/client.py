"""HTTP client for the simulator: retries transport errors and 5xx, raises ApiError on 4xx.

Every mutating call we make is idempotent by key (proposal_id) except /sim/advance and the two
credit-spending endpoints; those are called with retries=1 and reconciled by the caller.
"""
from __future__ import annotations

import time

import httpx


class ApiError(Exception):
    def __init__(self, status: int, code, detail):
        super().__init__(f"{status} {code}: {detail}")
        self.status, self.code, self.detail = status, code, detail


class Sim:
    def __init__(self, url: str | None = None, http: httpx.Client | None = None):
        self.h = http or httpx.Client(base_url=url, timeout=httpx.Timeout(600, connect=10))

    def req(self, method: str, path: str, retries: int = 8, **kw) -> httpx.Response:
        delay = 0.5
        for i in range(retries):
            try:
                r = self.h.request(method, path, **kw)
            except httpx.TransportError:
                if i == retries - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 500 and i < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 400:
                try:
                    j = r.json()
                except ValueError:
                    j = {"error": f"http_{r.status_code}", "detail": r.text[:500]}
                raise ApiError(r.status_code, j.get("error") or j.get("detail"), j.get("detail"))
            return r
        raise RuntimeError("unreachable")

    def get(self, path, **kw):
        return self.req("GET", path, **kw).json()

    def post(self, path, body, retries=8):
        return self.req("POST", path, json=body, retries=retries).json()

    def put(self, path, body):
        return self.req("PUT", path, json=body).json()

    def wait_ready(self, timeout_s=600):
        t0 = time.time()
        while True:
            try:
                self.h.get("/health")
                return
            except httpx.TransportError:
                if time.time() - t0 > timeout_s:
                    raise
                time.sleep(1)

    def advance(self, minutes: int) -> dict:
        """Not idempotent: on a lost response, check the clock instead of blindly retrying."""
        before = self.get("/sim/state")
        for _ in range(8):
            try:
                return self.post("/sim/advance", {"minutes": minutes}, retries=1)
            except (httpx.TransportError, httpx.HTTPStatusError):
                st = self.get("/sim/state")
                if st["sim_minute"] > before["sim_minute"] or st["finished"]:
                    return {**st, "new_chunks": []}
                time.sleep(2)
        raise RuntimeError("advance failed repeatedly")

    def stream_chunk(self, n: int):
        with self.h.stream("GET", f"/events/chunks/{n}") as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    yield line
