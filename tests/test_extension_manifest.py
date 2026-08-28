"""Structural checks on the browser extension's manifest.json — no test in
this repo checked it before the side-panel conversion added sidePanel/tabs
permissions and a background service worker, all real, user-visible
increases in what the extension can access. This locks the allowlist down
so a future accidental over-grant is caught in CI rather than code review.
"""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent.parent / "browser-extension" / "manifest.json"

ALLOWED_PERMISSIONS = {"activeTab", "scripting", "cookies", "sidePanel", "tabs", "storage"}
ALLOWED_HOST_PERMISSIONS = {"http://localhost:8000/*", "http://127.0.0.1:8000/*"}
# Requested at fill time via chrome.permissions.request, never granted at
# install. Confined to the two ATS vendors form-filling actually supports —
# the same hosts detect_ats_platform recognizes.
ALLOWED_OPTIONAL_HOST_PERMISSIONS = {"https://*.greenhouse.io/*", "https://*.lever.co/*"}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_is_valid_json_and_manifest_v3() -> None:
    manifest = _manifest()
    assert manifest["manifest_version"] == 3


def test_manifest_permissions_are_an_allowed_subset() -> None:
    manifest = _manifest()
    permissions = set(manifest.get("permissions", []))
    assert permissions <= ALLOWED_PERMISSIONS, permissions - ALLOWED_PERMISSIONS


def test_manifest_host_permissions_are_an_allowed_subset() -> None:
    manifest = _manifest()
    host_permissions = set(manifest.get("host_permissions", []))
    assert host_permissions <= ALLOWED_HOST_PERMISSIONS, host_permissions - ALLOWED_HOST_PERMISSIONS
    assert ALLOWED_HOST_PERMISSIONS <= host_permissions, ALLOWED_HOST_PERMISSIONS - host_permissions


def test_manifest_optional_host_permissions_are_an_allowed_subset() -> None:
    manifest = _manifest()
    optional = set(manifest.get("optional_host_permissions", []))
    assert optional <= ALLOWED_OPTIONAL_HOST_PERMISSIONS, optional - ALLOWED_OPTIONAL_HOST_PERMISSIONS


def test_manifest_never_requests_broad_host_access() -> None:
    """A bare "<all_urls>" or unscoped wildcard host permission would let the
    extension read every page the user visits — never acceptable here, since
    tab-URL awareness is deliberately scoped through the "tabs" permission
    (metadata only, not page content) plus activeTab (content, but only on
    an explicit user gesture).

    Optional host permissions are held to the same bar: they prompt at fill
    time rather than at install, but once granted they are exactly as broad
    as a declared one, so a wildcard slipped in there would be just as bad.
    """
    manifest = _manifest()
    for key in ("host_permissions", "optional_host_permissions"):
        perms = manifest.get(key, [])
        assert "<all_urls>" not in perms, key
        assert not any(perm.strip() in {"*://*/*", "https://*/*", "http://*/*"} for perm in perms), key


def test_manifest_declares_side_panel_default_path_that_exists() -> None:
    manifest = _manifest()
    side_panel = manifest.get("side_panel")
    assert side_panel is not None, "expected a side_panel entry after the popup-to-panel conversion"
    default_path = side_panel.get("default_path")
    assert default_path
    assert (MANIFEST_PATH.parent / default_path).exists() or (
        MANIFEST_PATH.parent / "dist" / default_path
    ).exists()
