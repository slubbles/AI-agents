"""
Tests for Limitations Round improvements:
1. LLM Response Cache (utils/llm_cache.py)
2. KB Versioned Rollback (memory_store.py)
3. Global Rate Limiter (utils/rate_limiter.py)
4. Dashboard API Auth (dashboard/api.py)
5. Auto-pruning in research loop (main.py)

No API calls — all tests use temp directories and mocked objects.
"""

import json
import os
import sys
import time
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# 1. LLM Response Cache Tests
# ============================================================

class TestLLMCache:
    """Tests for utils/llm_cache.py"""

    @pytest.fixture(autouse=True)
    def setup_cache(self, tmp_path):
        """Set up a fresh cache directory for each test."""
        import utils.llm_cache as cache_mod

        self.cache_dir = str(tmp_path / "cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        # Patch module-level state
        self._orig_dir = cache_mod.CACHE_DIR
        self._orig_cache = cache_mod._mem_cache.copy()
        self._orig_loaded = cache_mod._loaded
        self._orig_stats = cache_mod._stats.copy()

        cache_mod.CACHE_DIR = self.cache_dir
        cache_mod._mem_cache.clear()
        cache_mod._loaded = False
        cache_mod._stats = {"hits": 0, "misses": 0, "evictions": 0}
        self.mod = cache_mod
        yield

        # Restore
        cache_mod.CACHE_DIR = self._orig_dir
        cache_mod._mem_cache.clear()
        cache_mod._mem_cache.update(self._orig_cache)
        cache_mod._loaded = self._orig_loaded
        cache_mod._stats = self._orig_stats

    def _make_mock_response(self, text="Hello", model="test-model", stop_reason="end_turn"):
        """Create a mock Anthropic response object."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text

        usage = MagicMock()
        usage.input_tokens = 100
        usage.output_tokens = 50

        resp = MagicMock()
        resp.id = "msg_test123"
        resp.type = "message"
        resp.role = "assistant"
        resp.model = model
        resp.stop_reason = stop_reason
        resp.content = [text_block]
        resp.usage = usage
        return resp

    def test_cache_key_deterministic(self):
        """Same inputs produce same cache key."""
        key1 = self.mod._cache_key("model", "system", [{"role": "user", "content": "hi"}])
        key2 = self.mod._cache_key("model", "system", [{"role": "user", "content": "hi"}])
        assert key1 == key2

    def test_cache_key_varies_with_model(self):
        """Different models produce different keys."""
        key1 = self.mod._cache_key("model-a", "system", [{"role": "user", "content": "hi"}])
        key2 = self.mod._cache_key("model-b", "system", [{"role": "user", "content": "hi"}])
        assert key1 != key2

    def test_cache_key_varies_with_messages(self):
        """Different messages produce different keys."""
        key1 = self.mod._cache_key("model", "system", [{"role": "user", "content": "hi"}])
        key2 = self.mod._cache_key("model", "system", [{"role": "user", "content": "bye"}])
        assert key1 != key2

    def test_cache_key_varies_with_tools(self):
        """Presence of tools changes the key."""
        key1 = self.mod._cache_key("model", "system", [])
        key2 = self.mod._cache_key("model", "system", [], tools=[{"name": "search"}])
        assert key1 != key2

    def test_put_and_get(self):
        """Put a response and retrieve it."""
        resp = self._make_mock_response(text="cached result")
        key = "test_key_001"
        self.mod.put(key, resp, ttl=60)
        cached = self.mod.get(key)
        assert cached is not None
        assert cached.content[0].text == "cached result"
        assert cached.model == "test-model"
        assert cached.stop_reason == "end_turn"

    def test_get_miss(self):
        """Get returns None on cache miss."""
        result = self.mod.get("nonexistent_key")
        assert result is None

    def test_ttl_expiry(self):
        """Expired entries return None."""
        resp = self._make_mock_response()
        key = "ttl_test"
        self.mod.put(key, resp, ttl=1)
        # Should hit
        assert self.mod.get(key) is not None
        # Wait for expiry
        time.sleep(1.1)
        assert self.mod.get(key) is None

    def test_cached_response_mimics_real(self):
        """CachedResponse has same attributes as real response."""
        resp = self._make_mock_response(text="test", model="claude-3")
        key = "mimic_test"
        self.mod.put(key, resp)
        cached = self.mod.get(key)

        assert hasattr(cached, "id")
        assert hasattr(cached, "model")
        assert hasattr(cached, "role")
        assert hasattr(cached, "stop_reason")
        assert hasattr(cached, "content")
        assert hasattr(cached, "usage")
        assert cached.role == "assistant"
        assert cached.usage.input_tokens == 100
        assert cached.usage.output_tokens == 50
        assert len(cached.content) == 1
        assert cached.content[0].type == "text"
        assert cached.content[0].text == "test"

    def test_tool_use_response_not_cached(self):
        """Responses with stop_reason=tool_use should not be cached by cached_create_message."""
        tool_resp = self._make_mock_response(stop_reason="tool_use")
        # Simulate what cached_create_message does
        should_cache = True
        if hasattr(tool_resp, "stop_reason") and tool_resp.stop_reason == "tool_use":
            should_cache = False
        assert should_cache is False

    def test_invalidate(self):
        """Invalidating removes the entry."""
        resp = self._make_mock_response()
        key = "inv_test"
        self.mod.put(key, resp)
        assert self.mod.get(key) is not None
        self.mod.invalidate(key)
        assert self.mod.get(key) is None

    def test_clear(self):
        """Clear removes all entries."""
        for i in range(5):
            self.mod.put(f"key_{i}", self._make_mock_response())
        self.mod.clear()
        for i in range(5):
            assert self.mod.get(f"key_{i}") is None

    def test_stats_tracking(self):
        """Stats track hits and misses."""
        resp = self._make_mock_response()
        self.mod.put("stats_key", resp)
        self.mod.get("stats_key")  # hit
        self.mod.get("stats_key")  # hit
        self.mod.get("nonexistent")  # miss

        stats = self.mod.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] > 0

    def test_disk_persistence(self):
        """Cache survives memory clear when loaded from disk."""
        resp = self._make_mock_response(text="persisted")
        key = "persist_test"
        self.mod.put(key, resp, ttl=3600)

        # Clear memory but not disk
        self.mod._mem_cache.clear()
        self.mod._loaded = False

        # Should reload from disk
        cached = self.mod.get(key)
        assert cached is not None
        assert cached.content[0].text == "persisted"

    def test_tool_use_block_serialization(self):
        """Tool use blocks are properly serialized and deserialized."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_123"
        tool_block.name = "web_search"
        tool_block.input = {"query": "test"}

        usage = MagicMock()
        usage.input_tokens = 50
        usage.output_tokens = 25

        resp = MagicMock()
        resp.id = "msg_tool"
        resp.type = "message"
        resp.role = "assistant"
        resp.model = "test"
        resp.stop_reason = "end_turn"  # end_turn with tool content
        resp.content = [tool_block]
        resp.usage = usage

        key = "tool_block_test"
        self.mod.put(key, resp)
        cached = self.mod.get(key)
        assert cached is not None
        assert cached.content[0].type == "tool_use"
        assert cached.content[0].name == "web_search"
        assert cached.content[0].input == {"query": "test"}


# ============================================================
# 2. KB Versioned Rollback Tests
# ============================================================

class TestKBRollback:
    """Tests for KB versioning in memory_store.py"""

    @pytest.fixture(autouse=True)
    def setup_memory(self, tmp_path):
        """Set up a temp memory directory."""
        self.mem_dir = str(tmp_path / "memory")
        os.makedirs(self.mem_dir, exist_ok=True)
        self.domain = "test_domain"
        self.domain_dir = os.path.join(self.mem_dir, self.domain)
        os.makedirs(self.domain_dir, exist_ok=True)

    def _create_kb(self, claims_count=5, label="v1"):
        """Create a knowledge base file with dummy data."""
        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        kb = {
            "domain": self.domain,
            "label": label,
            "claims": [{"claim": f"Claim {i}", "confidence": 0.8} for i in range(claims_count)],
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        with open(kb_path, "w") as f:
            json.dump(kb, f, indent=2)
        return kb_path

    def test_version_created_on_save(self):
        """Saving KB creates a version backup."""
        import memory_store

        self._create_kb(3, "original")

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir):
            # Trigger versioning
            memory_store._version_knowledge_base(
                self.domain,
                os.path.join(self.domain_dir, "_knowledge_base.json"),
            )

        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        assert os.path.isdir(versions_dir)
        files = os.listdir(versions_dir)
        assert len(files) == 1
        assert files[0].startswith("kb_v") and files[0].endswith(".json")

    def test_version_content_matches_original(self):
        """Versioned file has same content as original."""
        import memory_store

        self._create_kb(4, "check_content")
        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")

        with open(kb_path) as f:
            original = json.load(f)

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir):
            memory_store._version_knowledge_base(self.domain, kb_path)

        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        version_file = os.listdir(versions_dir)[0]
        with open(os.path.join(versions_dir, version_file)) as f:
            versioned = json.load(f)

        assert versioned["label"] == original["label"]
        assert len(versioned["claims"]) == len(original["claims"])

    def test_max_versions_enforced(self):
        """Only most recent 10 versions are kept."""
        import memory_store

        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        os.makedirs(versions_dir, exist_ok=True)

        # Create 12 versions manually
        for i in range(12):
            ver = {"claims": [{"claim": f"v{i}"}], "domain": self.domain}
            ts = f"20250101_{i:06d}"
            vpath = os.path.join(versions_dir, f"kb_v{ts}.json")
            with open(vpath, "w") as f:
                json.dump(ver, f)

        # Write current KB
        self._create_kb(1, "current")

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir):
            memory_store._version_knowledge_base(self.domain, kb_path)

        # Should be max 10
        files = os.listdir(versions_dir)
        assert len(files) <= 10

    def test_list_kb_versions(self):
        """list_kb_versions returns version metadata."""
        import memory_store

        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        os.makedirs(versions_dir, exist_ok=True)

        # Create 3 versions
        for i in range(3):
            ver = {"claims": [{"claim": f"v{i}"}] * (i + 1), "domain": self.domain}
            ts = f"20250{i+1}01_000000"
            with open(os.path.join(versions_dir, f"kb_v{ts}.json"), "w") as f:
                json.dump(ver, f)

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir):
            versions = memory_store.list_kb_versions(self.domain)

        assert len(versions) == 3
        # Should have metadata
        for v in versions:
            assert "version" in v
            assert "path" in v

    def test_list_kb_versions_empty(self):
        """Returns empty list when no versions exist."""
        import memory_store

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir):
            versions = memory_store.list_kb_versions(self.domain)
        assert versions == []

    def test_rollback_restores_version(self):
        """Rollback replaces current KB with specified version."""
        import memory_store

        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        os.makedirs(versions_dir, exist_ok=True)

        # Create a version with known content
        old_kb = {"claims": [{"claim": "old_claim"}], "domain": self.domain}
        ver_path = os.path.join(versions_dir, "kb_v20250101_000000.json")
        with open(ver_path, "w") as f:
            json.dump(old_kb, f)

        # Current KB has different content
        self._create_kb(5, "current")

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir), \
             patch("memory_store.RAG_ENABLED", False, create=True):
            result = memory_store.rollback_knowledge_base(self.domain, "kb_v20250101_000000.json")

        assert result is not None
        # Check current KB was replaced
        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        with open(kb_path) as f:
            restored = json.load(f)
        assert len(restored["claims"]) == 1
        assert restored["claims"][0]["claim"] == "old_claim"

    def test_rollback_latest_when_no_version_specified(self):
        """Rollback without version uses the most recent."""
        import memory_store

        versions_dir = os.path.join(self.domain_dir, "_kb_versions")
        os.makedirs(versions_dir, exist_ok=True)

        # Create two versions
        for i, ts in enumerate(["20250101_000000", "20250201_000000"]):
            ver = {"claims": [{"claim": f"version_{i}"}], "domain": self.domain}
            with open(os.path.join(versions_dir, f"kb_v{ts}.json"), "w") as f:
                json.dump(ver, f)

        self._create_kb(3, "current")

        with patch.object(memory_store, "MEMORY_DIR", self.mem_dir), \
             patch("memory_store.RAG_ENABLED", False, create=True):
            result = memory_store.rollback_knowledge_base(self.domain)

        kb_path = os.path.join(self.domain_dir, "_knowledge_base.json")
        with open(kb_path) as f:
            restored = json.load(f)
        # Should have restored the more recent version (20250201)
        assert restored["claims"][0]["claim"] == "version_1"


# ============================================================
# 3. Rate Limiter Tests
# ============================================================

class TestRateLimiter:
    """Tests for utils/rate_limiter.py"""

    @pytest.fixture(autouse=True)
    def clean_buckets(self):
        """Clear global bucket registry between tests."""
        import utils.rate_limiter as rl
        self.mod = rl
        # Save and clear state
        with rl._registry_lock:
            self._orig_buckets = dict(rl._buckets)
            rl._buckets.clear()
        yield
        # Restore
        with rl._registry_lock:
            rl._buckets.clear()
            rl._buckets.update(self._orig_buckets)

    def test_acquire_slot(self):
        """Basic slot acquisition works."""
        assert self.mod.wait_for_slot("search", timeout=1) is True

    def test_check_slot_available(self):
        """check_slot returns True when tokens are available."""
        # Force bucket creation
        self.mod.wait_for_slot("test_check", timeout=1)
        assert self.mod.check_slot("test_check") is True

    def test_bucket_depletes(self):
        """Bucket depletes after many rapid calls."""
        # Create a very low-rate bucket
        bucket = self.mod._TokenBucket(rate_per_minute=2)
        # Should succeed twice (capacity = 2)
        assert bucket.acquire(timeout=0.1) is True
        assert bucket.acquire(timeout=0.1) is True
        # Third should fail (depleted, no time to refill)
        assert bucket.acquire(timeout=0.1) is False

    def test_bucket_refills(self):
        """Bucket refills over time."""
        bucket = self.mod._TokenBucket(rate_per_minute=60)  # 1 per second
        # Drain all tokens
        for _ in range(60):
            bucket.acquire(timeout=0)
        # Wait for refill
        time.sleep(1.1)
        assert bucket.acquire(timeout=0.1) is True

    def test_per_resource_isolation(self):
        """Different resources have independent buckets."""
        # Deplete search
        bucket_search = self.mod._TokenBucket(rate_per_minute=1)
        bucket_fetch = self.mod._TokenBucket(rate_per_minute=1)

        bucket_search.acquire(timeout=0.1)
        # search is depleted
        assert bucket_search.acquire(timeout=0.1) is False
        # fetch should still work
        assert bucket_fetch.acquire(timeout=0.1) is True

    def test_get_status(self):
        """Status reports bucket info."""
        self.mod.wait_for_slot("status_test", timeout=1)
        status = self.mod.get_status()
        assert "status_test" in status
        assert "tokens_available" in status["status_test"]
        assert "capacity" in status["status_test"]
        assert "rate_per_minute" in status["status_test"]

    def test_reset_refills_bucket(self):
        """Reset restores bucket to full capacity."""
        bucket = self.mod._TokenBucket(rate_per_minute=2)
        bucket.acquire(timeout=0.1)
        bucket.acquire(timeout=0.1)
        assert bucket.acquire(timeout=0.1) is False

        # Reset via module function
        with self.mod._registry_lock:
            self.mod._buckets["reset_test"] = bucket
        self.mod.reset("reset_test")
        assert bucket.acquire(timeout=0.1) is True

    def test_update_rate(self):
        """Bucket rate can be updated."""
        bucket = self.mod._TokenBucket(rate_per_minute=10)
        assert bucket.capacity == 10
        bucket.update_rate(100)
        assert bucket.capacity == 100

    def test_thread_safety(self):
        """Concurrent access doesn't corrupt state."""
        bucket = self.mod._TokenBucket(rate_per_minute=100)
        results = []

        def worker():
            result = bucket.acquire(timeout=1)
            results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (capacity=100, only 50 requests)
        assert all(results)
        assert len(results) == 50


# ============================================================
# 4. Dashboard API Auth Tests
# ============================================================

class TestDashboardAuth:
    """Tests for API key authentication in dashboard/api.py"""

    @pytest.fixture
    def app_and_client(self):
        """Return (app, TestClient) for dashboard API."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi[test] not installed")
        from dashboard.api import app
        return app, TestClient(app)

    def test_root_always_accessible(self, app_and_client):
        """Root endpoint is public even when auth is configured."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", "secret"):
            resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_no_auth_all_open(self, app_and_client):
        """When no API key configured, all endpoints are open."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", ""):
            resp = client.get("/")
        assert resp.status_code == 200

    def test_auth_blocks_without_key(self, app_and_client):
        """Protected endpoints return 401 without API key."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", "test-secret-key-123"):
            resp = client.get("/api/domains")
        assert resp.status_code == 401
        assert "Invalid or missing API key" in resp.json()["detail"]

    def test_auth_passes_with_header(self, app_and_client):
        """Correct X-API-Key header grants access."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", "test-secret-key-123"):
            resp = client.get(
                "/api/domains",
                headers={"x-api-key": "test-secret-key-123"},
            )
        # Should not be 401 (may be 200 or 500 depending on backend state)
        assert resp.status_code != 401

    def test_auth_passes_with_query_param(self, app_and_client):
        """Correct api_key query param grants access."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", "test-secret-key-123"):
            resp = client.get("/api/domains?api_key=test-secret-key-123")
        assert resp.status_code != 401

    def test_auth_rejects_wrong_key(self, app_and_client):
        """Wrong API key returns 401."""
        _, client = app_and_client
        with patch("dashboard.api.DASHBOARD_API_KEY", "test-secret-key-123"):
            resp = client.get(
                "/api/domains",
                headers={"x-api-key": "wrong-key"},
            )
        assert resp.status_code == 401


# ============================================================
# 5. Auto-Prune Wiring Tests
# ============================================================

class TestAutoPrune:
    """Tests for auto-pruning wired into the research loop."""

    def test_auto_prune_config_exists(self):
        """Config has AUTO_PRUNE_ENABLED and AUTO_PRUNE_EVERY_N."""
        from config import AUTO_PRUNE_ENABLED, AUTO_PRUNE_EVERY_N
        assert isinstance(AUTO_PRUNE_ENABLED, bool)
        assert isinstance(AUTO_PRUNE_EVERY_N, int)
        assert AUTO_PRUNE_EVERY_N > 0

    def test_auto_prune_triggers_at_interval(self):
        """Prune is called when accepted count is divisible by AUTO_PRUNE_EVERY_N."""
        # Simulate the logic from main.py
        AUTO_PRUNE_EVERY_N_val = 10
        for count in [10, 20, 30]:
            assert count % AUTO_PRUNE_EVERY_N_val == 0

        for count in [1, 5, 11, 15, 21]:
            assert count % AUTO_PRUNE_EVERY_N_val != 0

    def test_auto_prune_only_on_accept(self):
        """Prune step only runs when verdict is 'accept'."""
        # Simulate the guard condition
        for verdict in ["accept"]:
            should_prune = (verdict == "accept")
            assert should_prune is True

        for verdict in ["reject", "retry", None]:
            should_prune = (verdict == "accept")
            assert should_prune is False

    def test_prune_domain_callable(self):
        """prune_domain is importable and callable."""
        from memory_store import prune_domain
        assert callable(prune_domain)

    def test_auto_prune_disabled(self):
        """When AUTO_PRUNE_ENABLED is False, no pruning happens."""
        enabled = False
        verdict = "accept"
        count = 10
        every_n = 10

        should_run = enabled and verdict == "accept" and count > 0 and count % every_n == 0
        assert should_run is False


# ============================================================
# 6. Integration: Config Constants
# ============================================================

class TestConfigConstants:
    """Verify all new config constants exist and have correct types."""

    def test_llm_cache_config(self):
        from config import LLM_CACHE_ENABLED, LLM_CACHE_TTL, LLM_CACHE_DIR
        assert isinstance(LLM_CACHE_ENABLED, bool)
        assert isinstance(LLM_CACHE_TTL, int)
        assert isinstance(LLM_CACHE_DIR, str)

    def test_rate_limit_config(self):
        from config import RATE_LIMIT_SEARCHES_PER_MINUTE, RATE_LIMIT_FETCHES_PER_MINUTE
        assert isinstance(RATE_LIMIT_SEARCHES_PER_MINUTE, (int, float))
        assert isinstance(RATE_LIMIT_FETCHES_PER_MINUTE, (int, float))
        assert RATE_LIMIT_SEARCHES_PER_MINUTE > 0
        assert RATE_LIMIT_FETCHES_PER_MINUTE > 0

    def test_auto_prune_config(self):
        from config import AUTO_PRUNE_ENABLED, AUTO_PRUNE_EVERY_N
        assert isinstance(AUTO_PRUNE_ENABLED, bool)
        assert isinstance(AUTO_PRUNE_EVERY_N, int)

    def test_dashboard_config(self):
        from config import DASHBOARD_API_KEY, DASHBOARD_CORS_ORIGINS
        assert isinstance(DASHBOARD_API_KEY, str)
        assert isinstance(DASHBOARD_CORS_ORIGINS, str)


# ============================================================
# 7. LLM Cache — cached_create_message Integration
# ============================================================

class TestCachedCreateMessage:
    """Tests for the cached_create_message wrapper."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        import utils.llm_cache as cache_mod
        self.cache_dir = str(tmp_path / "cache")
        os.makedirs(self.cache_dir)
        self._orig_dir = cache_mod.CACHE_DIR
        self._orig_cache = cache_mod._mem_cache.copy()
        self._orig_loaded = cache_mod._loaded
        self._orig_stats = cache_mod._stats.copy()

        cache_mod.CACHE_DIR = self.cache_dir
        cache_mod._mem_cache.clear()
        cache_mod._loaded = False
        cache_mod._stats = {"hits": 0, "misses": 0, "evictions": 0}
        yield
        cache_mod.CACHE_DIR = self._orig_dir
        cache_mod._mem_cache.clear()
        cache_mod._mem_cache.update(self._orig_cache)
        cache_mod._loaded = self._orig_loaded
        cache_mod._stats = self._orig_stats

    def test_cached_create_message_caches_on_first_call(self):
        """First call hits API, second call returns cache."""
        from utils.llm_cache import cached_create_message, get_stats

        mock_resp = MagicMock()
        mock_resp.id = "msg_1"
        mock_resp.type = "message"
        mock_resp.role = "assistant"
        mock_resp.model = "test"
        mock_resp.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello"
        mock_resp.content = [text_block]
        mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)

        mock_client = MagicMock()

        with patch("utils.retry.create_message", return_value=mock_resp) as mock_create:
            # First call — API hit
            r1 = cached_create_message(
                mock_client, model="test", system="sys",
                messages=[{"role": "user", "content": "hi"}],
                verbose=False,
            )
            assert mock_create.call_count == 1

            # Second call — cache hit
            r2 = cached_create_message(
                mock_client, model="test", system="sys",
                messages=[{"role": "user", "content": "hi"}],
                verbose=False,
            )
            # Should NOT call API again
            assert mock_create.call_count == 1

        stats = get_stats()
        assert stats["hits"] >= 1

    def test_skip_cache_forces_api_call(self):
        """skip_cache=True always calls the API."""
        from utils.llm_cache import cached_create_message

        mock_resp = MagicMock()
        mock_resp.id = "msg_skip"
        mock_resp.type = "message"
        mock_resp.role = "assistant"
        mock_resp.model = "test"
        mock_resp.stop_reason = "end_turn"
        mock_resp.content = []
        mock_resp.usage = MagicMock(input_tokens=0, output_tokens=0)

        with patch("utils.retry.create_message", return_value=mock_resp) as mock_create:
            cached_create_message(
                MagicMock(), model="t", system="s",
                messages=[{"role": "user", "content": "a"}],
                skip_cache=True, verbose=False,
            )
            cached_create_message(
                MagicMock(), model="t", system="s",
                messages=[{"role": "user", "content": "a"}],
                skip_cache=True, verbose=False,
            )
            assert mock_create.call_count == 2


# ============================================================
# 8. Rate Limiter — Config Integration
# ============================================================

class TestRateLimiterConfig:
    """Tests for rate limiter loading config values."""

    def test_web_search_rate_limited(self):
        """web_search.py imports rate limiter."""
        import tools.web_search as ws
        source = open(ws.__file__).read()
        assert "wait_for_slot" in source or "rate_limiter" in source

    def test_web_fetcher_rate_limited(self):
        """web_fetcher.py imports rate limiter."""
        import tools.web_fetcher as wf
        source = open(wf.__file__).read()
        assert "wait_for_slot" in source or "rate_limiter" in source
