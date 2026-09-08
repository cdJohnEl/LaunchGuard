"""Gate tests for the Firestore data layer against an in-memory fake db."""
import asyncio
import copy
from datetime import datetime

import pytest
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore import DELETE_FIELD, Increment
from google.cloud.firestore_v1.field_path import FieldPath

import config
import firebase_client
from firebase_client import FirebaseConfigError
from google.cloud.exceptions import NotFound


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


def _prune_empty_parents(doc: dict, parts: list) -> None:
    # After a leaf delete, Firestore drops map fields that became empty.
    chain = []
    cursor = doc
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            return
        chain.append((cursor, part, nxt))
        cursor = nxt
    for parent, key, node in reversed(chain):
        if node == {}:
            parent.pop(key, None)
        else:
            return


class FakeDocRef:
    def __init__(self, fs: "FakeFirestore", key: tuple):
        self._fs = fs
        self.key = key

    def get(self, transaction=None) -> FakeSnapshot:
        return FakeSnapshot(copy.deepcopy(self._fs.store.get(self.key)))

    def create(self, data: dict) -> None:
        self._fs.creates[self.key] = self._fs.creates.get(self.key, 0) + 1
        if self.key in self._fs.store:
            raise AlreadyExists("document already exists")
        self._fs.store[self.key] = copy.deepcopy(data)

    def set(self, data: dict, merge: bool = False) -> None:
        # Real SDK fidelity: set(merge=True) does NOT expand dotted string keys
        # (they become literal top-level field names) but DOES leaf-merge nested
        # dicts (mask = every leaf path, so sibling map entries survive).
        self._fs.sets[self.key] = copy.deepcopy(data)
        if merge:
            doc = copy.deepcopy(self._fs.store.get(self.key) or {})
            for segments, value in _leaf_walk(data, []):
                self._apply_segments(doc, segments, value)
            self._fs.store[self.key] = doc
        else:
            self._fs.store[self.key] = copy.deepcopy(data)

    def update(self, data: dict) -> None:
        if any(isinstance(k, FieldPath) for k in data):
            # Real SDK fidelity (2.29.0): update() cannot take FieldPath keys —
            # mixed key types fail sorting, pure FieldPath keys hit .strip().
            raise TypeError("update() rejects FieldPath keys on the pinned SDK")
        if self.key not in self._fs.store:
            raise NotFound("no such document")
        self._fs.updates[self.key] = self._fs.updates.get(self.key, []) + [copy.deepcopy(data)]
        doc = self._fs.store[self.key]
        for key, value in data.items():
            # Real SDK fidelity: update() expands dotted STRING keys.
            parts = key.split(".")
            self._apply_segments(doc, parts, value)

    @staticmethod
    def _apply_segments(doc: dict, parts: list, value) -> None:
        cursor = doc
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        leaf = parts[-1]
        if isinstance(value, Increment):
            cursor[leaf] = (cursor.get(leaf) or 0) + value.value
        elif value is DELETE_FIELD:
            cursor.pop(leaf, None)
            _prune_empty_parents(doc, parts)
        else:
            cursor[leaf] = copy.deepcopy(value)


class FakeCollection:
    def __init__(self, fs: "FakeFirestore", name: str):
        self._fs = fs
        self._prefix = (name,)

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._fs, self._prefix + (str(doc_id),))


def _leaf_walk(data: dict, prefix: list) -> list:
    segments_pairs = []
    for key, value in data.items():
        parts = prefix + [key]
        if isinstance(value, dict):
            segments_pairs.extend(_leaf_walk(value, parts))
        else:
            segments_pairs.append((parts, value))
    return segments_pairs


class FakeTransaction:
    def get(self, ref: "FakeDocRef") -> FakeSnapshot:
        return ref.get()

    def update(self, ref: "FakeDocRef", data: dict) -> None:
        ref.update(data)

    def get(self, ref: "FakeDocRef") -> FakeSnapshot:
        return ref.get()

    def update(self, ref: "FakeDocRef", data: dict) -> None:
        ref.update(data)


class FakeBatch:
    def __init__(self, fs: "FakeFirestore"):
        self._fs = fs
        self._ops: list = []

    def set(self, ref: "FakeDocRef", data: dict, merge: bool = False) -> None:
        self._ops.append((ref, data, merge))

    def commit(self) -> None:
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)


class FakeFirestore:
    def __init__(self):
        self.store: dict = {}
        self.sets: dict = {}
        self.creates: dict = {}
        self.updates: dict = {}
        self.batches: list = []

    def batch(self) -> FakeBatch:
        batch = FakeBatch(self)
        self.batches.append(batch)
        return batch

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)

    def doc_ref(self, chat_id: int) -> FakeDocRef:
        return self.collection("groups").document(str(chat_id))


@pytest.fixture(autouse=True)
def _firebase_state(monkeypatch):
    # Freeze the dotenv loader: a developer's real backend/.env must never
    # leak into tests that assert credential-missing behavior.
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setattr(firebase_client, "_transactional", lambda db: (lambda fn: fn))
    monkeypatch.setattr(firebase_client, "_count_active_docs", lambda db: 0)
    saved = (firebase_client._db, firebase_client._app)
    firebase_client._config_cache.clear()
    firebase_client._inflight_configs.clear()
    yield
    firebase_client._db, firebase_client._app = saved
    firebase_client._config_cache.clear()
    firebase_client._inflight_configs.clear()


def use_fake(fs: FakeFirestore) -> FakeFirestore:
    firebase_client._db = fs
    return fs


def seed_doc(fs: FakeFirestore, chat_id: int, data: dict) -> None:
    fs.store[("groups", str(chat_id))] = copy.deepcopy(data)


FULL_DOC = {
    "chat_id": -100123,
    "group_name": "Alpha Chat",
    "owner_uid": "user-1",
    "active": False,
    "subscription_status": "active",
    "scams_blocked": 7,
    "scam_keywords": ["rug\\d*"],
    "faq_pairs": {"contract address": "0xabc at docs.example.com"},
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
}


def test_is_ready_false_without_init():
    assert firebase_client.is_ready() is False


def test_is_ready_after_fake_injection():
    use_fake(FakeFirestore())
    assert firebase_client.is_ready() is True


def test_init_firebase_idempotent_when_ready():
    fs = use_fake(FakeFirestore())
    firebase_client.init_firebase()
    assert firebase_client._db is fs


def test_close_resets_state():
    fs = use_fake(FakeFirestore())
    firebase_client._config_cache["x"] = (0.0, {"scam_keywords": [], "faq_pairs": {}})
    firebase_client.close()
    assert firebase_client.is_ready() is False
    assert firebase_client._config_cache == {}


def test_init_firebase_error_names_both_env_options(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(FirebaseConfigError) as excinfo:
        firebase_client.init_firebase()
    message = str(excinfo.value)
    assert "GOOGLE_APPLICATION_CREDENTIALS" in message
    assert "FIREBASE_SERVICE_ACCOUNT_JSON" in message
    assert "Fix:" in message


def test_init_firebase_invalid_json(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_JSON", "{not-json")
    with pytest.raises(FirebaseConfigError) as excinfo:
        firebase_client.init_firebase()
    assert "not valid JSON" in str(excinfo.value)


def test_init_firebase_missing_cred_file(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent/path/sa.json")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(FirebaseConfigError) as excinfo:
        firebase_client.init_firebase()
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(excinfo.value)


async def test_ensure_chat_creates_doc_with_contract_defaults():
    fs = use_fake(FakeFirestore())
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["chat_id"] == -100123
    assert doc["group_name"] == "Alpha Chat"
    assert doc["owner_uid"] is None
    assert doc["active"] is True
    assert doc["subscription_status"] == "trial"
    assert doc["scams_blocked"] == 0
    assert doc["scam_keywords"] == []
    assert doc["faq_pairs"] == {}
    created = datetime.fromisoformat(doc["created_at"])
    updated = datetime.fromisoformat(doc["updated_at"])
    assert created.utcoffset().total_seconds() == 0
    assert updated.utcoffset().total_seconds() == 0


async def test_ensure_chat_preserves_existing_counters_and_pairs():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.ensure_chat(-100123, "Alpha Chat Renamed", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 7
    assert doc["faq_pairs"] == {"contract address": "0xabc at docs.example.com"}
    assert doc["scam_keywords"] == ["rug\\d*"]
    assert doc["owner_uid"] == "user-1"
    assert doc["subscription_status"] == "active"
    assert doc["active"] is True
    assert doc["group_name"] == "Alpha Chat Renamed"
    assert doc["updated_at"] > doc["created_at"]


async def test_ensure_chat_does_not_persist_chat_type():
    fs = use_fake(FakeFirestore())
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert "chat_type" not in doc


async def test_set_chat_active():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.set_chat_active(-100123, False)
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["active"] is False
    await firebase_client.set_chat_active(-100123, True)
    assert fs.doc_ref(-100123).get().to_dict()["active"] is True


async def test_increment_scams_blocked_uses_atomic_increment():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.increment_scams_blocked(-100123)
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 8
    sent = fs.sets[("groups", "-100123")]
    assert isinstance(sent["scams_blocked"], Increment)
    assert sent["scams_blocked"].value == 1
    await firebase_client.increment_scams_blocked(-100123, amount=4)
    assert fs.doc_ref(-100123).get().to_dict()["scams_blocked"] == 12


async def test_increment_on_missing_doc_creates_it():
    fs = use_fake(FakeFirestore())
    await firebase_client.increment_scams_blocked(-100999, amount=3)
    doc = fs.doc_ref(-100999).get().to_dict()
    assert doc["scams_blocked"] == 3
    assert doc["updated_at"]


async def test_get_chat_returns_copy_or_none():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    chat = await firebase_client.get_chat(-100123)
    assert chat["scams_blocked"] == 7
    chat["scams_blocked"] = 999
    assert fs.doc_ref(-100123).get().to_dict()["scams_blocked"] == 7
    assert await firebase_client.get_chat(-100777) is None


async def test_get_chat_config_returns_fields():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    config = await firebase_client.get_chat_config(-100123)
    assert config == {
        "scam_keywords": ["rug\\d*"],
        "faq_pairs": {"contract address": "0xabc at docs.example.com"},
    }


async def test_get_chat_config_missing_doc_gives_empty_defaults():
    use_fake(FakeFirestore())
    config = await firebase_client.get_chat_config(-100555)
    assert config == {"scam_keywords": [], "faq_pairs": {}}


async def test_get_chat_config_ttl_cache_returns_cached_copy():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    first = await firebase_client.get_chat_config(-100123)
    fs.store[("groups", "-100123")]["scam_keywords"] = ["changed"]
    second = await firebase_client.get_chat_config(-100123)
    assert second == first
    second["scam_keywords"].append("mutant")
    second["faq_pairs"]["injected"] = "x"
    third = await firebase_client.get_chat_config(-100123)
    assert third == first


async def test_get_chat_config_reloads_after_ttl_expiry():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.get_chat_config(-100123)
    fs.store[("groups", "-100123")]["scam_keywords"] = ["changed"]
    import time

    firebase_client._config_cache["-100123"] = (
        time.monotonic() - (firebase_client.CONFIG_TTL_SECONDS + 1),
        {"scam_keywords": ["stale"], "faq_pairs": {}},
    )
    fresh = await firebase_client.get_chat_config(-100123)
    assert fresh["scam_keywords"] == ["changed"]


async def test_get_chat_config_requires_init():
    assert firebase_client._db is None
    with pytest.raises(FirebaseConfigError):
        await firebase_client.get_chat_config(-100123)


async def test_set_faq_pair_writes_map_field_and_invalidates_cache():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.get_chat_config(-100123)
    await firebase_client.set_faq_pair(-100123, "wen tge", "after the audit")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"]["wen tge"] == "after the audit"
    assert doc["faq_pairs"]["contract address"] == "0xabc at docs.example.com"
    config = await firebase_client.get_chat_config(-100123)
    assert config["faq_pairs"]["wen tge"] == "after the audit"


async def test_set_faq_pair_creates_missing_doc():
    fs = use_fake(FakeFirestore())
    await firebase_client.set_faq_pair(-100123, "audit", "done by hacken")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"audit": "done by hacken"}


async def test_delete_faq_pair_removes_entry_and_invalidates_cache():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.get_chat_config(-100123)
    await firebase_client.delete_faq_pair(-100123, "contract address")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert "contract address" not in doc.get("faq_pairs", {})
    config = await firebase_client.get_chat_config(-100123)
    assert "contract address" not in config["faq_pairs"]


async def test_delete_faq_pair_on_missing_doc_is_noop():
    use_fake(FakeFirestore())
    await firebase_client.delete_faq_pair(-100123, "ghost")
    assert await firebase_client.get_chat(-100123) is None


async def test_increment_requires_init():
    assert firebase_client._db is None
    with pytest.raises(FirebaseConfigError):
        await firebase_client.increment_scams_blocked(-100123)


async def test_ensure_chat_uses_atomic_create_path():
    fs = use_fake(FakeFirestore())
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    assert fs.creates[("groups", "-100123")] == 1
    await firebase_client.ensure_chat(-100123, "Alpha Chat Renamed", "supergroup")
    assert fs.creates[("groups", "-100123")] == 2
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 0


async def test_ensure_chat_race_with_concurrent_increment_never_clobbers():
    # Worst-case interleave: create() loses the AlreadyExists race on an existing
    # doc that meanwhile gained a counter value. The merge fallback must not
    # touch scams_blocked or faq_pairs.
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 7
    assert doc["faq_pairs"] == {"contract address": "0xabc at docs.example.com"}
    assert doc["owner_uid"] == "user-1"


async def test_get_chat_config_single_flight_one_read_per_burst(monkeypatch):
    use_fake(FakeFirestore())
    reads = {"count": 0}

    async def counting_get(chat_id):
        reads["count"] += 1
        await asyncio.sleep(0.01)
        return None

    monkeypatch.setattr(firebase_client, "get_chat", counting_get)

    results = await asyncio.gather(
        *(firebase_client.get_chat_config(-100123) for _ in range(10))
    )
    assert reads["count"] == 1
    assert all(r == results[0] for r in results)


# --- critic round 2 regressions ---


async def test_ensure_chat_backfills_partial_docs():
    # Docs created by a counter increment or FAQ write before registration lack
    # contract fields; a later ensure_chat must backfill them without touching
    # real values.
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "scams_blocked": 5})
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 5
    assert doc["group_name"] == "Alpha Chat"
    assert doc["created_at"]
    assert doc["owner_uid"] is None
    assert doc["subscription_status"] == "trial"
    assert doc["scam_keywords"] == []
    assert doc.get("faq_pairs", {}) == {}


async def test_ensure_chat_backfill_never_clobbers_faq_pairs(monkeypatch):
    # Round-4 finding: set(merge=True) merges at top level only, so a backfill
    # payload containing faq_pairs would replace the whole map. The backfill
    # must go through update() and never name faq_pairs for an existing doc.
    fs = use_fake(FakeFirestore())
    seed_doc(
        fs,
        -100123,
        {"chat_id": -100123, "scams_blocked": 5, "faq_pairs": {"wen tge": "soon"}},
    )
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"wen tge": "soon"}
    assert doc["scams_blocked"] == 5
    assert fs.creates[("groups", "-100123")] == 1
    for payload in fs.updates[("groups", "-100123")]:
        assert "faq_pairs" not in payload
    assert ("groups", "-100123") not in fs.sets


async def test_single_flight_survives_waiter_cancellation(monkeypatch):
    use_fake(FakeFirestore())
    reads = {"count": 0}

    async def counting_get(chat_id):
        reads["count"] += 1
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(firebase_client, "get_chat", counting_get)

    import contextlib

    first = asyncio.ensure_future(firebase_client.get_chat_config(-100123))
    await asyncio.sleep(0.005)
    first.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await first

    second = await firebase_client.get_chat_config(-100123)
    assert reads["count"] == 1
    assert second == {"scam_keywords": [], "faq_pairs": {}}


# --- critic round 4 regressions ---


async def test_set_faq_pair_payload_leaf_merges_at_wire_level():
    # Round-4/5 findings: the Python SDK does NOT expand dots in
    # set(merge=True) (a dotted string becomes a literal top-level field) and
    # update() REJECTS FieldPath keys entirely on the pinned SDK. The only
    # correct form is a nested dict through merge-set, which leaf-merges.
    # This test proves the wire mask with the SDK's own extractor.
    from google.cloud.firestore_v1._helpers import DocumentExtractorForMerge

    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "faq_pairs": {"old": "pair"}})
    await firebase_client.set_faq_pair(-100123, "wen tge", "soon")

    payload = fs.sets[("groups", "-100123")]
    assert isinstance(payload["faq_pairs"], dict)  # nested dict, not a dotted string
    assert not any("." in k for k in payload)

    extractor = DocumentExtractorForMerge(payload)
    extractor.apply_merge(True)
    mask = sorted(p.to_api_repr() for p in extractor.merge)
    assert mask == ["faq_pairs.`wen tge`", "updated_at"]

    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"old": "pair", "wen tge": "soon"}  # sibling survives
    assert "faq_pairs.wen tge" not in doc  # the exact production bug


async def test_set_faq_pair_keyword_with_dot_is_stored_verbatim():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "faq_pairs": {}})
    await firebase_client.set_faq_pair(-100123, "a.b", "value")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"a.b": "value"}
    assert "a" not in doc["faq_pairs"]


async def test_delete_faq_pair_keyword_with_dot_is_verbatim():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "faq_pairs": {"a.b": "value", "x": "y"}})
    await firebase_client.delete_faq_pair(-100123, "a.b")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"x": "y"}


async def test_set_faq_pair_creates_partial_doc_for_missing_chat():
    # merge-set creates the doc with only the written leaves; a later
    # ensure_chat backfills the contract defaults for it.
    fs = use_fake(FakeFirestore())
    await firebase_client.set_faq_pair(-100123, "audit", "done by hacken")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"audit": "done by hacken"}
    assert doc["updated_at"]
    await firebase_client.ensure_chat(-100123, "Alpha Chat", "supergroup")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["faq_pairs"] == {"audit": "done by hacken"}
    assert doc["subscription_status"] == "trial"
    assert doc["group_name"] == "Alpha Chat"


async def test_set_faq_pair_rejects_whitespace_only_keyword():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "faq_pairs": {}})
    await firebase_client.set_faq_pair(-100123, "   ", "ignored")
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc.get("faq_pairs", {}) == {}


# --- lockdown: public stats + batch writes ---


async def test_increment_writes_group_and_public_stats_in_one_batch():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, dict(FULL_DOC))
    await firebase_client.increment_scams_blocked(-100123, amount=2)
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["scams_blocked"] == 9
    stats = fs.store.get(("public", "stats"))
    assert stats["total_blocked"] == 2
    assert len(fs.batches) == 1 and len(fs.batches[0]._ops) == 2


async def test_refresh_active_groups_count_writes_public_doc(monkeypatch):
    fs = use_fake(FakeFirestore())
    monkeypatch.setattr(firebase_client, "_count_active_docs", lambda db: 7)
    await firebase_client.refresh_active_groups_count()
    stats = fs.store.get(("public", "stats"))
    assert stats["active_groups"] == 7


async def test_set_chat_active_refreshes_public_count(monkeypatch):
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, FULL_DOC)
    calls = []
    monkeypatch.setattr(
        firebase_client, "_count_active_docs", lambda db: calls.append(1) or 3
    )
    await firebase_client.set_chat_active(-100123, True)
    assert fs.doc_ref(-100123).get().to_dict()["active"] is True
    assert fs.store.get(("public", "stats"))["active_groups"] == 3
    assert len(calls) == 1


# --- proof-of-control claims ---


async def test_claim_group_binds_unowned_doc():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "owner_uid": None})
    result = await firebase_client.claim_group(-100123, "uid-abc")
    assert result == "claimed"
    doc = fs.doc_ref(-100123).get().to_dict()
    assert doc["owner_uid"] == "uid-abc"


async def test_claim_group_refuses_owned_doc():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "owner_uid": "founder-1"})
    result = await firebase_client.claim_group(-100123, "attacker-9")
    assert result == "taken"
    assert fs.doc_ref(-100123).get().to_dict()["owner_uid"] == "founder-1"


async def test_claim_group_not_found():
    use_fake(FakeFirestore())
    assert await firebase_client.claim_group(-100999, "uid-abc") == "not_found"


async def test_claim_group_reattach_by_same_owner_is_idempotent():
    # Re-running /claim with your own code must succeed, not "taken": a
    # rightful owner re-claiming after a page reload is normal.
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "owner_uid": "uid-abc"})
    result = await firebase_client.claim_group(-100123, "uid-abc")
    assert result == "claimed"
    assert fs.doc_ref(-100123).get().to_dict()["owner_uid"] == "uid-abc"


async def test_claim_group_invalidates_config_cache():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "owner_uid": None, "faq_pairs": {}})
    await firebase_client.get_chat_config(-100123)
    await firebase_client.claim_group(-100123, "uid-abc")
    assert "-100123" not in firebase_client._config_cache


async def test_unclaim_group_releases_ownership():
    fs = use_fake(FakeFirestore())
    seed_doc(fs, -100123, {"chat_id": -100123, "owner_uid": "founder-1"})
    assert await firebase_client.unclaim_group(-100123) == "cleared"
    assert fs.doc_ref(-100123).get().to_dict()["owner_uid"] is None


async def test_unclaim_group_missing_doc():
    use_fake(FakeFirestore())
    assert await firebase_client.unclaim_group(-100999) == "not_found"
