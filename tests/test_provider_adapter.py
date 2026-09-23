"""Tests for OpenAIProviderAdapter structured extraction provider using mocks."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from recall.engine.extractor import (
    OpenAIProviderAdapter,
)


def test_openai_provider_adapter_mocked():
    adapter = OpenAIProviderAdapter(api_key="mock_key", model="gpt-4o-mini")

    mock_response_json = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "entities": [
                                {"temp_id": "temp_john", "type": "person", "canonical_name": "John", "aliases": ["JD"]}
                            ],
                            "facts": [
                                {
                                    "subject_ref": "temp_john",
                                    "predicate": "primary_employer",
                                    "object_value": "Google",
                                    "confidence": 1.0,
                                    "source_type": "direct_statement",
                                }
                            ],
                        }
                    )
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_json).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        turn = adapter.extract("User", "John works at Google", event_time=now)
        assert len(turn.entities) == 1
        assert turn.entities[0].canonical_name == "John"
        assert len(turn.facts) == 1
        assert turn.facts[0].object_value == "Google"
