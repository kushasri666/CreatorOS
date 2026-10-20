"""Initialize a local encryption key without printing credentials."""
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values

path = Path(__file__).resolve().parents[1] / ".env"
existing = dotenv_values(path) if path.exists() else {}
if existing.get("CREATOROS_TOKEN_KEY"):
    Fernet(existing["CREATOROS_TOKEN_KEY"].encode())
    print("Existing token encryption key preserved.")
else:
    with path.open("a", encoding="utf-8") as file:
        file.write("\nCREATOROS_TOKEN_KEY="+Fernet.generate_key().decode()+"\n")
    print("Local token encryption key added to gitignored .env. No key displayed.")
