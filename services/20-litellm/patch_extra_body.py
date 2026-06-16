"""
Patch for https://github.com/BerriAI/litellm/issues/21891
Fixes TypeError: 'NoneType' object is not a mapping when extra_body is None
"""

import pathlib

# Find litellm install path dynamically
import litellm
base = pathlib.Path(litellm.__path__[0])
print(f"[patch] litellm found at: {base}")

patches = [
    # 1) utils.py — add_provider_specific_params_to_optional_params
    #    extra_body from passed_params can be None
    (
        base / "utils.py",
        'extra_body = passed_params.pop("extra_body", {})',
        'extra_body = passed_params.pop("extra_body", {}) or {}',
    ),
    # 2) utils.py — optional_params["extra_body"] can be None after setdefault
    #    setdefault doesn't replace an existing None value
    (
        base / "utils.py",
        'optional_params.setdefault("extra_body", {})',
        'optional_params["extra_body"] = optional_params.get("extra_body") or {}',
    ),
    # 3) openai_like chat handler — extra_body from optional_params can be None
    (
        base / "llms" / "openai_like" / "chat" / "handler.py",
        'extra_body = optional_params.pop("extra_body", {})',
        'extra_body = optional_params.pop("extra_body", {}) or {}',
    ),
]

for filepath, old, new in patches:
    if not filepath.exists():
        print(f"[patch] WARN: {filepath} not found, skipping")
        continue

    content = filepath.read_text()
    count = content.count(old)

    if count == 0:
        print(f"[patch] WARN: pattern not found in {filepath.name}: {old!r}")
        # Check if already patched
        if new in content:
            print(f"[patch]   -> already patched")
        continue

    content = content.replace(old, new)
    filepath.write_text(content)
    print(f"[patch] OK: {filepath.name} — replaced {count} occurrence(s)")

print("[patch] Done.")
