"""Buffer GraphQL client for X-only testing.

This is intentionally small.

Current scope:
1. Verify Buffer account access
2. List connected channels
3. Filter connected X channels
4. Create a safe draft post for X testing
5. Support a supervised draft -> confirm -> send flow for X

Threads stays on the direct Threads API path.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from utils.atomic_write import atomic_json_write

logger = logging.getLogger(__name__)

BUFFER_GRAPHQL_URL = "https://api.buffer.com/graphql"
BUFFER_SUPERVISOR_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "logs",
    "buffer_supervisor_state.json",
)
MAX_PENDING_X_DRAFTS = 10
_DOTENV_ATTEMPTED = False


class BufferAPIError(Exception):
    """Raised when a Buffer API call fails."""


def _read_env_key_from_file(env_path: Path, key_name: str) -> str:
    """Read a single key directly from a .env file without relying on dotenv parsing."""
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() != key_name:
                    continue
                return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _get_buffer_api_key() -> str:
    """Return the Buffer API key from env, loading .env lazily if needed."""
    global _DOTENV_ATTEMPTED

    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    if api_key:
        return api_key

    if not _DOTENV_ATTEMPTED:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(env_path, override=False)
        _DOTENV_ATTEMPTED = True

        api_key = os.environ.get("BUFFER_API_KEY", "").strip()
        if api_key:
            return api_key

        file_key = _read_env_key_from_file(env_path, "BUFFER_API_KEY")
        if file_key:
            os.environ["BUFFER_API_KEY"] = file_key
            return file_key

    return os.environ.get("BUFFER_API_KEY", "").strip()


def is_configured() -> bool:
    """Return True when the Buffer API key is present."""
    return bool(_get_buffer_api_key())


def _load_supervisor_state() -> dict:
    """Load the persisted supervised X state."""
    if not os.path.exists(BUFFER_SUPERVISOR_STATE_FILE):
        return {}
    try:
        with open(BUFFER_SUPERVISOR_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_supervisor_state(state: dict):
    """Persist the supervised X state."""
    atomic_json_write(BUFFER_SUPERVISOR_STATE_FILE, state)


def _normalize_pending_queue(value: object) -> list[dict]:
    """Normalize persisted pending drafts into a list."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and value:
        return [value]
    return []


def get_pending_x_queue() -> list[dict]:
    """Return all pending supervised X drafts in FIFO order."""
    state = _load_supervisor_state()
    queue = _normalize_pending_queue(state.get("pending_x_queue"))
    if queue:
        return queue

    legacy_pending = state.get("pending_x_draft", {})
    return _normalize_pending_queue(legacy_pending)


def get_pending_x_supervision() -> dict:
    """Return the next pending supervised X draft, if any."""
    queue = get_pending_x_queue()
    return queue[0] if queue else {}


def _set_pending_x_queue(records: Iterable[dict], last_sent: dict | None = None):
    """Persist the full pending supervised X queue."""
    state = _load_supervisor_state()
    state["pending_x_queue"] = list(records)
    state["pending_x_draft"] = state["pending_x_queue"][0] if state["pending_x_queue"] else {}
    if last_sent is not None:
        state["last_sent_x"] = last_sent
    _save_supervisor_state(state)


def _set_pending_x_supervision(record: dict):
    """Append one supervised X draft to the local approval queue."""
    queue = get_pending_x_queue()
    if len(queue) >= MAX_PENDING_X_DRAFTS:
        raise BufferAPIError(f"Pending X draft queue is full ({MAX_PENDING_X_DRAFTS} max)")
    queue.append(record)
    _set_pending_x_queue(queue)


def _remove_pending_x_supervision(draft_id: str | None = None, *, last_sent: dict | None = None) -> dict:
    """Remove one pending supervised X draft from the queue."""
    queue = get_pending_x_queue()
    if not queue:
        return {}

    target_index = 0
    if draft_id:
        for index, item in enumerate(queue):
            if item.get("draft_id") == draft_id:
                target_index = index
                break
        else:
            raise BufferAPIError(f"Pending supervised X draft not found: {draft_id}")

    removed = queue.pop(target_index)
    _set_pending_x_queue(queue, last_sent=last_sent)
    return removed


def _graphql_request(query: str, variables: dict | None = None, timeout: int = 30) -> dict:
    """Send a GraphQL request to Buffer."""
    api_key = _get_buffer_api_key()
    if not api_key:
        raise BufferAPIError("Buffer API not configured. Set BUFFER_API_KEY in .env")

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BUFFER_GRAPHQL_URL, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise BufferAPIError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise BufferAPIError(f"Connection error: {exc.reason}") from exc
    except Exception as exc:
        raise BufferAPIError(f"Request failed: {exc}") from exc

    if result.get("errors"):
        messages = "; ".join(err.get("message", "Unknown GraphQL error") for err in result["errors"])
        raise BufferAPIError(messages)

    return result.get("data", {})


def get_account() -> dict:
    """Fetch the Buffer account and organization info."""
    query = """
    query {
      account {
        id
        email
        organizations {
          id
          name
          ownerEmail
          channelCount
        }
      }
    }
    """
    data = _graphql_request(query)
    return data.get("account", {})


def get_default_organization() -> dict:
    """Return the first organization on the account."""
    account = get_account()
    orgs = account.get("organizations", [])
    if not orgs:
        raise BufferAPIError("No Buffer organizations found for this account")
    return orgs[0]


def list_channels(organization_id: str | None = None) -> list[dict]:
    """List channels for an organization."""
    target_org_id = organization_id or get_default_organization().get("id")
    if not target_org_id:
        raise BufferAPIError("No organization ID available")

    query = """
    query ListChannels($input: ChannelsInput!) {
      channels(input: $input) {
        id
        name
        displayName
        service
        serviceId
        type
        isDisconnected
        isLocked
      }
    }
    """
    data = _graphql_request(query, {"input": {"organizationId": target_org_id}})
    return data.get("channels", [])


def get_x_channels(organization_id: str | None = None) -> list[dict]:
    """Return connected X/Twitter channels only."""
    channels = list_channels(organization_id)
    return [channel for channel in channels if channel.get("service") == "twitter"]


def get_recent_x_posts(limit: int = 10, organization_id: str | None = None) -> list[dict]:
        """Return recent X posts visible through Buffer for the default organization."""
        target_org_id = organization_id or get_default_organization().get("id")
        if not target_org_id:
                raise BufferAPIError("No organization ID available")

        x_channel_ids = {channel.get("id") for channel in get_x_channels(target_org_id)}
        if not x_channel_ids:
                return []

        first = max(5, min(limit * 4, 50))
        query = """
        query Posts($input: PostsInput!, $first: Int) {
            posts(input: $input, first: $first) {
                edges {
                    node {
                        id
                        status
                        text
                        createdAt
                        sentAt
                        channel {
                            id
                            name
                            service
                        }
                    }
                }
            }
        }
        """
        data = _graphql_request(query, {"input": {"organizationId": target_org_id}, "first": first})
        edges = data.get("posts", {}).get("edges", [])
        posts = []
        for edge in edges:
                node = edge.get("node") or {}
                channel = node.get("channel") or {}
                if channel.get("id") not in x_channel_ids and channel.get("service") != "twitter":
                        continue
                posts.append(node)
                if len(posts) >= limit:
                        break
        return posts


def create_post(
    channel_id: str,
    text: str = "",
    *,
    mode: str = "addToQueue",
    scheduling_type: str = "automatic",
    save_to_draft: bool = False,
    source: str = "cortex-buffer",
    draft_id: str | None = None,
) -> dict:
    """Create a Buffer post for a channel."""
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess {
          post {
            id
            status
            text
            createdAt
            channel {
              id
              name
              service
            }
          }
        }
        ... on InvalidInputError { message }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message }
        ... on RestProxyError { message code link }
        ... on LimitReachedError { message }
        ... on NotFoundError { message }
      }
    }
    """

    variables = {
        "input": {
            "channelId": channel_id,
            "schedulingType": scheduling_type,
            "mode": mode,
            "saveToDraft": save_to_draft,
            "source": source,
        }
    }
    if text:
        variables["input"]["text"] = text
    if draft_id:
        variables["input"]["draftId"] = draft_id

    data = _graphql_request(mutation, variables)
    result = data.get("createPost", {})
    typename = result.get("__typename")

    if typename == "PostActionSuccess":
        post = result.get("post", {})
        logger.info("[BUFFER] Created post %s on %s", post.get("id"), post.get("channel", {}).get("service"))
        return {
            "ok": True,
            "mode": mode,
            "save_to_draft": save_to_draft,
            "post": post,
        }

    message = result.get("message", "Unknown Buffer mutation error")
    raise BufferAPIError(message)


def create_x_draft_test(text: str | None = None, organization_id: str | None = None) -> dict:
    """Create a safe draft post for the first connected X channel."""
    x_channels = get_x_channels(organization_id)
    if not x_channels:
        raise BufferAPIError("No connected X channels found in Buffer")

    channel = x_channels[0]
    post_text = text or (
        "Cortex Buffer API draft test "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    result = create_post(
        channel_id=channel["id"],
        text=post_text,
        mode="addToQueue",
        scheduling_type="automatic",
        save_to_draft=True,
        source="cortex-buffer-test",
    )
    result["channel"] = channel
    return result


def create_x_supervised_draft(text: str, organization_id: str | None = None) -> dict:
    """Create and persist a supervised X draft locally until it is confirmed."""
    if not text or not text.strip():
        raise BufferAPIError("Draft text is required")

    x_channels = get_x_channels(organization_id)
    if not x_channels:
        raise BufferAPIError("No connected X channels found in Buffer")

    channel = x_channels[0]
    pending = {
        "draft_id": f"xdraft_{uuid4().hex[:12]}",
        "draft_post_id": None,
        "channel_id": channel.get("id"),
        "channel_name": channel.get("displayName") or channel.get("name"),
        "text": text.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_confirmation",
    }
    _set_pending_x_supervision(pending)
    queue = get_pending_x_queue()
    return {
        "ok": True,
        "channel": channel,
        "pending": pending,
        "queue_size": len(queue),
        "queue_limit": MAX_PENDING_X_DRAFTS,
    }


def confirm_x_supervised_post(draft_id: str | None = None) -> dict:
    """Send the currently pending supervised X draft as a live X post."""
    queue = get_pending_x_queue()
    pending = queue[0] if queue and not draft_id else next((item for item in queue if item.get("draft_id") == draft_id), {})
    if not pending:
        raise BufferAPIError("No pending supervised X draft to confirm")

    result = create_post(
        channel_id=pending["channel_id"],
        text=pending["text"],
        mode="shareNow",
        scheduling_type="automatic",
        save_to_draft=False,
        source="cortex-buffer-supervised-confirm",
    )

    sent_record = {
        "source_draft_id": pending.get("draft_id"),
        "source_draft_post_id": pending.get("draft_post_id"),
        "sent_post_id": result.get("post", {}).get("id"),
        "channel_id": pending.get("channel_id"),
        "channel_name": pending.get("channel_name"),
        "text": pending.get("text"),
        "sent_at": result.get("post", {}).get("createdAt") or datetime.now(timezone.utc).isoformat(),
        "status": result.get("post", {}).get("status", "sent"),
    }
    removed = _remove_pending_x_supervision(draft_id=pending.get("draft_id"), last_sent=sent_record)
    result["confirmed_from"] = pending
    result["sent_record"] = sent_record
    result["removed_pending"] = removed
    result["remaining_queue_size"] = len(get_pending_x_queue())
    return result


def cancel_x_supervised_post(draft_id: str | None = None) -> dict:
    """Clear the pending supervised X draft without sending it."""
    queue = get_pending_x_queue()
    if not queue:
        return {"ok": True, "cleared": False, "reason": "no_pending_draft"}

    pending = _remove_pending_x_supervision(draft_id=draft_id)
    return {
        "ok": True,
        "cleared": True,
        "pending": pending,
        "remaining_queue_size": len(get_pending_x_queue()),
    }