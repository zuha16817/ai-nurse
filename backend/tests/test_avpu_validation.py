"""AVPU input validation on the vitals request (empty = not assessed, junk rejected)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from pydantic import ValidationError
from app.api.conversations import VitalSignsRequest


def test_empty_avpu_means_not_assessed():
    assert VitalSignsRequest(session_id="s", avpu="").avpu is None
    assert VitalSignsRequest(session_id="s", avpu="   ").avpu is None
    assert VitalSignsRequest(session_id="s").avpu is None


def test_avpu_is_normalised():
    assert VitalSignsRequest(session_id="s", avpu="unresponsive").avpu == "Unresponsive"


def test_invalid_avpu_rejected():
    with pytest.raises(ValidationError):
        VitalSignsRequest(session_id="s", avpu="Normal")
