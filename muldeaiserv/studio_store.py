"""Private AI Studio conversation persistence.

Conversations are stored on the controller in SQLite as plaintext. The server
never generates demo responses: inference is performed by configured backends.
"""
from __future__ import annotations

import secrets
import time


class StudioStore:
    MAX_HISTORY = 120
    MAX_CONVERSATIONS = 200

    def __init__(self, store):
        self.store = store
        with self.store.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS studio_conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    system_prompt TEXT NOT NULL DEFAULT '',
                    temperature REAL NOT NULL DEFAULT 0.7,
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS studio_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL
                      REFERENCES studio_conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_studio_messages_conversation
                  ON studio_messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS idx_studio_conversations_updated
                  ON studio_conversations(updated DESC);
            """)

    def list(self):
        with self.store.connection() as db:
            rows = db.execute("""
                SELECT c.id, c.title, c.model_id, c.temperature, c.created, c.updated,
                    (SELECT COUNT(*) FROM studio_messages m WHERE m.conversation_id=c.id)
                    AS message_count
                FROM studio_conversations c
                ORDER BY c.updated DESC, c.id DESC LIMIT ?
            """, (self.MAX_CONVERSATIONS,)).fetchall()
        return [dict(row) for row in rows]

    def get(self, conversation_id):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM studio_conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if row is None:
                return None
            messages = db.execute("""
                SELECT id, role, content, created FROM studio_messages
                WHERE conversation_id=? ORDER BY id ASC
            """, (conversation_id,)).fetchall()
        return {**dict(row), "messages": [dict(message) for message in messages]}

    def create(self, title, model_id, system_prompt, temperature):
        now = time.time()
        result = {
            "id": secrets.token_hex(12),
            "title": title.strip(),
            "model_id": model_id,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "created": now,
            "updated": now,
            "messages": [],
        }
        if not result["title"]:
            raise ValueError("Conversation title is required.")
        with self.store.connection() as db:
            count = db.execute("SELECT COUNT(*) FROM studio_conversations").fetchone()[0]
            if count >= self.MAX_CONVERSATIONS:
                raise ValueError("Maximum saved conversations reached. Delete an old chat first.")
            db.execute("""
                INSERT INTO studio_conversations
                    (id,title,model_id,system_prompt,temperature,created,updated)
                VALUES (?,?,?,?,?,?,?)
            """, tuple(result[key] for key in (
                "id", "title", "model_id", "system_prompt",
                "temperature", "created", "updated"
            )))
        return result

    def update(self, conversation_id, **changes):
        allowed = {"title", "model_id", "system_prompt", "temperature"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError("Unsupported conversation field.")
        if "title" in changes:
            changes["title"] = changes["title"].strip()
            if not changes["title"]:
                raise ValueError("Conversation title is required.")
        with self.store.connection() as db:
            row = db.execute("SELECT id FROM studio_conversations WHERE id=?",
                             (conversation_id,)).fetchone()
            if row is None:
                return None
            if changes:
                changes["updated"] = time.time()
                columns = ", ".join(f"{key}=?" for key in changes)
                db.execute(
                    f"UPDATE studio_conversations SET {columns} WHERE id=?",
                    (*changes.values(), conversation_id)
                )
        return self.get(conversation_id)

    def add_message(self, conversation_id, role, content):
        if role not in ("user", "assistant"):
            raise ValueError("Only user and assistant messages can be saved.")
        if not content.strip() or len(content) > 32768:
            raise ValueError("Message must contain 1–32768 characters.")
        now = time.time()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM studio_conversations WHERE id=?",
                (conversation_id,)
            ).fetchone()
            if row is None:
                return None
            count = db.execute(
                "SELECT COUNT(*) FROM studio_messages WHERE conversation_id=?",
                (conversation_id,)
            ).fetchone()[0]
            if count >= self.MAX_HISTORY:
                raise ValueError("Conversation history limit reached; start a new chat.")
            cursor = db.execute("""
                INSERT INTO studio_messages(conversation_id,role,content,created)
                VALUES (?,?,?,?)
            """, (conversation_id, role, content, now))
            db.execute("UPDATE studio_conversations SET updated=? WHERE id=?",
                       (now, conversation_id))
        return {"id": cursor.lastrowid, "role": role, "content": content, "created": now}

    def delete(self, conversation_id):
        with self.store.connection() as db:
            cursor = db.execute("DELETE FROM studio_conversations WHERE id=?",
                                (conversation_id,))
            return cursor.rowcount > 0
