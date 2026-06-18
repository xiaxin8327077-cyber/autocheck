import json
from pathlib import Path

out = Path.home() / "AppData" / "Roaming" / "auto-check" / "config.json"
out.parent.mkdir(parents=True, exist_ok=True)

config = {
    "configs": [
        {
            "name": "默认配置",
            "dws": {"type": "postgresql", "host": "127.0.0.1:5432", "database": "dws", "schema": "public", "user": "reader", "password": "***"},
            "business": {"type": "mysql", "host": "127.0.0.1:3306", "database": "biz", "schema": "", "user": "reader", "password": "***"},
            "is_default": True
        }
    ],
    "default_config_name": "默认配置"
}

with out.open("w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print(f"Config written to {out}")
