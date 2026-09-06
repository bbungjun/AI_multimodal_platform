#!/usr/bin/env python3
"""Capture current UI using the owned, credential-free browser QA runtime."""
from __future__ import annotations

import json
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from browser_acceptance_support import BrowserRuntime, FRONTEND_ORIGIN, port_available
from mock_auth_support import HarnessError, MemoryIdentity, ROOT


def write_manifest(output, receipt):
    images = []
    for name in ("studio", "prompt-review", "generation-result", "usage", "master"):
        data = (output / f"{name}.png").read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise HarnessError("invalid_capture_image")
        width, height = struct.unpack(">II", data[16:24])
        images.append({"file": f"{name}.png", "width": width, "height": height,
                       "sha256": hashlib.sha256(data).hexdigest()})
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise HarnessError("invalid_source_revision")
    manifest = {"source_revision": revision, "captured_on": datetime.now(timezone.utc).date().isoformat(),
                "provider": "mock", "browser": "Chromium", "viewport": {"width": 1440, "height": 900},
                "receipt": receipt, "images": images}
    (output / "capture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if sys.argv[1:]:
        print('{"complete":false,"error":"arguments_refused"}')
        return 2
    runtime = BrowserRuntime(ROOT / ".env.example")
    identity = MemoryIdentity()
    receipt = None
    phase = "preflight"
    try:
        with tempfile.TemporaryDirectory(prefix="creativeops-readme-") as directory:
            try:
                runtime.preflight()
                phase = "runtime_start"
                runtime.start(directory)
                phase = "fixture_seed"
                runtime.seed(identity)
                phase = "browser_capture"
                # Ephemeral fixture Sessions travel via stdin, never arguments or files.
                result = subprocess.run(
                    ["node", "scripts/capture-readme.mjs"], cwd=ROOT / "frontend",
                    env=runtime.env, input=json.dumps({
                        "backend_url": runtime.base_url,
                        "frontend_origin": FRONTEND_ORIGIN,
                        "secrets": {key: identity._secrets[key] for key in ("a", "master")},
                    }), capture_output=True, text=True, encoding="utf-8", timeout=150,
                )
                # Never surface raw child stderr/HTTP responses.
                receipt = json.loads(result.stdout)
                if (receipt.get("complete") is False
                        and re.fullmatch(r"[a-z_]{1,32}", receipt.get("phase", ""))):
                    phase = "browser_" + receipt["phase"]
                if result.returncode or receipt != {
                    "complete": True, "screenshots": 5, "external_requests": 0,
                    "mock_generations": 1, "prompt_reviews": 1,
                }:
                    raise HarnessError("capture_failed")
            finally:
                runtime.cleanup()
                if not port_available():
                    raise HarnessError("frontend_port_not_released")
        receipt["cleanup"] = 0
        output = ROOT / "output/playwright/readme"
        write_manifest(output, receipt)
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))
        return 0
    except (HarnessError, OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"complete": False, "phase": phase, "error": "capture_or_cleanup_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
