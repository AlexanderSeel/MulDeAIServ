"""SQLite device registry with single-use enrollment and hashed bearer secrets."""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .security import digest, verify

HEARTBEAT_TIMEOUT = 75

class DeviceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS joins(
                    digest TEXT PRIMARY KEY,expires REAL NOT NULL,used REAL);
                CREATE TABLE IF NOT EXISTS devices(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,
                    os_version TEXT NOT NULL,cpu_count INTEGER NOT NULL,
                    ram_mb INTEGER NOT NULL,gpus TEXT NOT NULL,
                    agent_digest TEXT NOT NULL,created REAL NOT NULL,
                    seen REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS backends(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,model_id TEXT NOT NULL UNIQUE,
                    base_url TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS inference_keys(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,digest TEXT NOT NULL UNIQUE,
                    prefix TEXT NOT NULL,created REAL NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_join(self, minutes=15):
        if not 5 <= minutes <= 120:
            raise ValueError("Join token duration must be 5–120 minutes.")
        token = secrets.token_urlsafe(32)
        expiry = time.time() + minutes * 60
        with self.connection() as db:
            db.execute("DELETE FROM joins WHERE expires < ? OR used IS NOT NULL", (time.time(),))
            db.execute("INSERT INTO joins(digest,expires) VALUES (?,?)", (digest(token), expiry))
        return {"token": token, "expires_at": expiry}

    def enroll(self, join_token, hw):
        now = time.time()
        identifier = secrets.token_hex(12)
        bearer = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT expires,used FROM joins WHERE digest=?", (digest(join_token),)).fetchone()
            if row is None or row["used"] is not None or row["expires"] < now:
                raise ValueError("Join token expired, used or invalid.")
            db.execute("UPDATE joins SET used=? WHERE digest=?", (now, digest(join_token)))
            db.execute(
                "INSERT INTO devices VALUES(?,?,?,?,?,?,?,?,?,?)",
                (identifier, hw["name"],hw["platform"],hw["os_version"],
                 hw["cpu_count"],hw["ram_mb"],json.dumps(hw["gpus"]),
                 digest(bearer),now,now))
        return {"device_id":identifier,"agent_token":bearer,"heartbeat_interval_seconds":20}

    def heartbeat(self, identifier, bearer, hw):
        with self.connection() as db:
            row = db.execute("SELECT agent_digest FROM devices WHERE id=?", (identifier,)).fetchone()
            if row is None or not verify(row["agent_digest"], bearer):
                return False
            db.execute(
                """UPDATE devices SET name=?,platform=?,os_version=?,cpu_count=?,
                    ram_mb=?,gpus=?,seen=? WHERE id=?""",
                (hw["name"],hw["platform"],hw["os_version"],hw["cpu_count"],
                 hw["ram_mb"],json.dumps(hw["gpus"]),time.time(),identifier))
        return True

    def devices(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,name,platform,os_version,cpu_count,ram_mb,gpus,created,seen FROM devices ORDER BY name,id"
            ).fetchall()
        now = time.time()
        return [{**dict(row),"gpus":json.loads(row["gpus"]),
                 "online":now-row["seen"] <= HEARTBEAT_TIMEOUT} for row in rows]

    def overview(self):
        devices = self.devices()
        online = [d for d in devices if d["online"]]
        backends = self.backends()
        return {"devices": devices, "backends": backends, "stats":{
            "online_devices":len(online),"total_devices":len(devices),
            "cpu_ram_mb":sum(d["ram_mb"] for d in online),
            "gpu_vram_mb":sum(g["memory_mb"] for d in online for g in d["gpus"]),
            "gpu_count":sum(len(d["gpus"]) for d in online),
            "backends":len(backends)}}

    def backends(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM backends ORDER BY created DESC")]

    def backend_for_model(self, model_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM backends WHERE model_id=?", (model_id,)).fetchone()
            return dict(row) if row else None

    def create_backend(self, name, model_id, origin, kind):
        from .security import MODEL_ID, private_origin
        if kind not in ("vllm","ollama","openai-compatible","exo","llama-cpp"):
            raise ValueError("Unsupported backend type.")
        if not MODEL_ID.fullmatch(model_id):
            raise ValueError("Invalid model ID.")
        if not name.strip():
            raise ValueError("Backend name required.")
        item = {"id":secrets.token_hex(8),"name":name.strip(),"model_id":model_id,
                "base_url":private_origin(origin),"kind":kind,"created":time.time()}
        try:
            with self.connection() as db:
                db.execute("INSERT INTO backends VALUES(?,?,?,?,?,?)",
                           tuple(item[k] for k in ("id","name","model_id","base_url","kind","created")))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Model ID already registered.") from exc
        return item

    def delete_backend(self, identifier):
        with self.connection() as db:
            result = db.execute("DELETE FROM backends WHERE id=?", (identifier,))
            return result.rowcount > 0

    def revoke_device(self, identifier):
        with self.connection() as db:
            result = db.execute("DELETE FROM devices WHERE id=?", (identifier,))
            return result.rowcount > 0

    def create_inference_key(self, name):
        if not name.strip() or len(name) > 100:
            raise ValueError("Key name must be 1–100 characters.")
        token = "mda_" + secrets.token_urlsafe(32)
        item = {"id": secrets.token_hex(12), "name": name.strip(),
                "prefix": token[:12], "created": time.time()}
        with self.connection() as db:
            db.execute("INSERT INTO inference_keys VALUES (?,?,?,?,?)",
                       (item["id"], item["name"], digest(token), item["prefix"], item["created"]))
        return {**item, "token": token}

    def inference_keys(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,name,prefix,created FROM inference_keys ORDER BY created DESC")]

    def verify_inference_key(self, token):
        if not token.startswith("mda_") or len(token) > 128:
            return False
        with self.connection() as db:
            row = db.execute("SELECT id FROM inference_keys WHERE digest=?", (digest(token),)).fetchone()
            return row is not None

    def revoke_inference_key(self, identifier):
        with self.connection() as db:
            result = db.execute("DELETE FROM inference_keys WHERE id=?", (identifier,))
            return result.rowcount > 0
