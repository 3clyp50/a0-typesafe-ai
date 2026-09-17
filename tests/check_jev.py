"""Run in /a0: python -m usr.plugins.typesafe_ai.tests.check_jev (no network)."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx2
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAuthenticationError

from usr.plugins.typesafe_ai import hooks
from usr.plugins.typesafe_ai.helpers.jev import query, result_cards, validate_config, validate_request


QUESTIONS = {
    "department": {"type": "choice", "instructions": "Which team handles this?", "criteria": {"billing": None, "other": None}},
    "refund": {"type": "noul", "instructions": {"question": "Is a refund requested?"}},
    "urgency": {"type": "score", "instructions": "How urgent?", "criteria": ["No deadline", "Today"]},
}
BODY = {"model": "jev-test", "usage": {"input_tokens": 25, "output_tokens": 10}, "answers": {
    "department": {"type": "choice", "choice": "billing", "confidence": .8, "probabilities": {"billing": .9, "other": .1}},
    "refund": {"type": "noul", "noul": .95},
    "urgency": {"type": "score", "score": .75, "confidence": .6, "legend": {"0": "No deadline", "1": "Today"}, "probabilities": {"0": .25, "1": .75}},
}}


async def main():
    validate_request("Refund today", QUESTIONS)
    for state, questions in [(None, QUESTIONS), ("x", {}), ("x", {"x": {"type": "score", "instructions": "x", "criteria": ["one"]}}), ("x", {"x": {"type": "noul", "instructions": "x", "criteria": {"yes": "x"}}})]:
        try:
            validate_request(state, questions)
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted malformed input")
    for timeout in [True, 0, float("nan"), 301]:
        try:
            validate_config({"timeout": timeout})
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted invalid timeout")

    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        assert request.url.path == "/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-only"
        return httpx2.Response(200, json=BODY)

    async with AsyncTypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(respond)) as client:
        result = await query(client, "Refund today", QUESTIONS, "jev-test")
    assert len(calls) == 1 and calls[0]["questions"] == QUESTIONS
    assert result["answers"]["refund"]["noul"] == .95
    cards = result_cards(result, QUESTIONS)["cards"]
    assert "confidence" not in cards[1]
    assert cards[2]["distribution"][1]["description"] == "Today"
    assert "test-only" not in json.dumps(result)

    async with AsyncTypeSafeClient(api_key="test-only", retry=RetryPolicy(max_retries=0), transport=httpx2.MockTransport(lambda r: httpx2.Response(401, json={"error": "invalid key"}))) as client:
        try:
            await query(client, "x", QUESTIONS, "jev-test")
        except TypeSafeAuthenticationError:
            pass
        else:
            raise AssertionError("Authentication failure treated as success")

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "resources/typesafe-ai"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("official skill")
        (source / "LICENSE").write_text("license")
        (root / "requirements.txt").write_text("typesafe-sdk==0.6.0")
        target = root / "installed"
        with patch.object(hooks, "ROOT", root), patch.object(hooks, "RECORD", root / ".skill-install.json"), patch.object(hooks.files, "get_abs_path", return_value=str(target)), patch.object(hooks.subprocess, "run") as install:
            hooks.install()
            hooks.install()
            install.assert_not_called()
            assert (target / "SKILL.md").read_text() == "official skill"
            (target / "SKILL.md").write_text("user edited skill")
            hooks.uninstall()
            assert (target / "SKILL.md").read_text() == "user edited skill"
            assert not (target / "LICENSE").exists()
    print("PASS: validation, SDK batch request, typed output, error propagation, repeat install, safe cleanup")


if __name__ == "__main__":
    asyncio.run(main())
