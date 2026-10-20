"""Credential/model metadata check. No generation calls or credential output."""
import os
from workflow import Mesh


if __name__ == "__main__":
    try:
        payload = Mesh(metadata_only=True).client.get("/models", cast_to=object)
        rows = payload if isinstance(payload, list) else payload["data"]
        models = {m.get("id", m.get("name")) for m in rows}
        print("Mesh authenticated. Available model count:", len(models))
        for model in (os.getenv("MESH_TEXT_MODEL", "openai/gpt-4o"),
                      os.getenv("MESH_IMAGE_MODEL", "openai/gpt-image-1")):
            print(model, "listed" if model in models else "NOT LISTED; configure a supported identifier")
    except Exception as exc:
        print("Mesh metadata check failed:", type(exc).__name__)
        raise SystemExit(1)
