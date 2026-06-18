from __future__ import annotations

import json
import subprocess
from pathlib import Path

from auto_check.app.security import AuthManager


ROOT = Path(__file__).resolve().parents[1]
CRYPTO_FALLBACK_JS = ROOT / "src" / "auto_check" / "web" / "crypto_fallback.js"


def test_js_rsa_oaep_fallback_encrypts_password_for_auth_manager(tmp_path: Path) -> None:
    auth = AuthManager(tmp_path / "config.json")
    password = "AdminPass123"
    script = f"""
const {{ encryptPasswordWithJwk }} = require({json.dumps(str(CRYPTO_FALLBACK_JS))});
const nodeCrypto = require("crypto").webcrypto;
globalThis.crypto = {{ getRandomValues: (target) => nodeCrypto.getRandomValues(target) }};
(async () => {{
  const encrypted = await encryptPasswordWithJwk({json.dumps(password)}, {json.dumps(auth.public_key_jwk())});
  console.log(encrypted);
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    encrypted = result.stdout.strip()
    assert encrypted
    assert auth.decrypt_transport_password(encrypted) == password
