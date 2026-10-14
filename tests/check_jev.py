"""Run in /a0: python -m usr.plugins.typesafe_ai.tests.check_jev (no network)."""

import asyncio
import base64
from copy import deepcopy
from email.parser import BytesParser
from email.policy import default
import io
import json
import sys
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx2
from PIL import Image, PngImagePlugin
from typesafe_sdk import AsyncTypeSafeClient, Image as ImageAsset, RetryPolicy, TypeSafeAuthenticationError, TypeSafeError

from usr.plugins.typesafe_ai import hooks
from usr.plugins.typesafe_ai.extensions.python.startup_migration import _20_typesafe_dependencies as startup
from usr.plugins.typesafe_ai.helpers.jev import prepare_images, query, result_cards, validate_config, validate_request


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


def request_body(request):
    content = request.content
    if request.headers.get("Content-Encoding") == "zstd":
        from backports.zstd import decompress
        content = decompress(content)
    content_type = request.headers["Content-Type"]
    if not content_type.startswith("multipart/"):
        return json.loads(content), {}
    message = BytesParser(policy=default).parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + content)
    parts = {part.get_param("name", header="Content-Disposition"): part.get_payload(decode=True)
             for part in message.iter_parts()}
    return json.loads(parts.pop("request")), parts


async def main():
    assert validate_config({}) == ("jev-1.14.0", 30)
    assert validate_config({"model": "jev-latest"}) == ("jev-1.14.0", 30)
    assert validate_config({"model": "jev-preview"}) == ("jev-1.14.0", 30)
    assert validate_config({"model": "jev-custom"}) == ("jev-custom", 30)
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
        calls.append(request_body(request)[0])
        assert request.url.path == "/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-only"
        assert request.headers["TypeSafe-Danger-Zone-Long-Context"] == "true"
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        return httpx2.Response(200, json=BODY)

    async with AsyncTypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(respond)) as client:
        result = await query(client, "Refund today", QUESTIONS, "jev-test")
    assert len(calls) == 1 and calls[0]["questions"] == QUESTIONS
    assert result["answers"]["refund"]["noul"] == .95
    cards = result_cards(result, QUESTIONS)["cards"]
    assert "confidence" not in cards[1]
    assert cards[2]["distribution"][1]["description"] == "Today"
    assert "test-only" not in json.dumps(result)

    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "scene.png"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private-comment", "must not upload")
        Image.new("RGB", (600, 400), "white").save(path, pnginfo=metadata)
        assets, previews = prepare_images({"image-id": str(path)})
        assert isinstance(assets["image-id"], ImageAsset)
        decoded = Image.open(io.BytesIO(assets["image-id"].data))
        assert decoded.size == (600, 400) and not decoded.info
        assert base64.b64decode(previews["image-id"]["src"].split(",")[1]) == assets["image-id"].data
        with patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            try:
                prepare_images({"image-id": str(path)})
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted unsafe image dimensions")

        oriented = Path(temporary) / "rotated.jpg"
        photo = Image.new("RGB", (400, 600), "white")
        exif = photo.getexif()
        exif[274] = 6
        photo.save(oriented, exif=exif)
        rotated, _ = prepare_images({"rotated-id": str(oriented)})
        upright = Image.open(io.BytesIO(rotated["rotated-id"].data))
        assert upright.size == (600, 400) and not upright.getexif()

        for filename, size in [("small.png", (256, 256)), ("wide.png", (1569, 400)), ("unsupported.gif", (600, 400))]:
            invalid = Path(temporary) / filename
            Image.new("RGB", size, "white").save(invalid)
            try:
                prepare_images({"image-id": str(invalid)})
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted unsupported image")

        box_questions = {"target": {"type": "box", "instructions": "The target in `photo`", "image": "image-id"}}
        box_body = {**deepcopy(BODY), "answers": {"target": {"type": "box", "box": {
            "left": .25, "right": .75, "top": .25, "bottom": .75}, "confidence": .9}}}
        def box_respond(request):
            body, parts = request_body(request)
            assert request.headers["Content-Type"].startswith("multipart/form-data")
            assert parts[body["assets"]["image-id"]["part"]] == assets["image-id"].data
            assert str(path).encode() not in request.content
            assert body["state"] == {"photo": "image-id"}
            assert body["model"] == "jev-1.14.0"
            assert body["questions"]["target"] == {"type": "box", "instructions": "The target in `photo`"}
            return httpx2.Response(200, json=box_body)
        for model in ["jev-latest", "jev-preview", "jev-1.14.0"]:
            async with AsyncTypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(box_respond)) as client:
                boxed = await query(client, {"photo": "image-id"}, box_questions, validate_config({"model": model})[0], assets)
        assert boxed["answers"]["target"]["box"]["left"] == .25
        assert result_cards(boxed, box_questions, previews)["cards"][0]["image"] == "image-id"
        single_question = {"target": {"type": "box", "instructions": "The target in `photo`"}}
        assert result_cards(boxed, single_question, previews)["cards"][0]["image"] == "image-id"
        no_confidence = deepcopy(box_body)
        no_confidence["answers"]["target"]["confidence"] = None
        async with AsyncTypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json=no_confidence))) as client:
            assert (await query(client, {"photo": "image-id"}, box_questions, "jev-1.14.0", assets))["answers"]["target"]["confidence"] is None
        for question, images in [(box_questions, None), (single_question, {"a": "x", "b": "y"}),
                                 ({"target": {**box_questions["target"], "criteria": None}}, assets),
                                 ({"target": {**box_questions["target"], "image": "missing"}}, assets)]:
            try:
                validate_request("state", question, images)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted ambiguous or malformed Box question")
        for edges in [{"left": -.1}, {"left": .9}, {"top": True}, {"right": 1.1}]:
            invalid_body = deepcopy(box_body)
            invalid_body["answers"]["target"]["box"].update(edges)
            async with AsyncTypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json=invalid_body))) as client:
                try:
                    await query(client, {"photo": "image-id"}, box_questions, "jev-1.14.0", assets)
                except (TypeSafeError, ValueError):
                    pass
                else:
                    raise AssertionError("Accepted invalid Box coordinates")

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
        (root / "requirements.txt").write_text("typesafe-sdk==0.7.5\npydantic>=2.12.0,<2.14\n")
        target = root / "installed"
        with patch.object(hooks, "ROOT", root), patch.object(hooks, "RECORD", root / ".skill-install.json"), patch.object(hooks.files, "get_abs_path", return_value=str(target)), patch.object(hooks.subprocess, "run") as install:
            hooks.install()
            hooks.install()
            assert install.call_count == 2
            install.assert_called_with(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(root / "requirements.txt")],
                check=True,
            )
            assert (target / "SKILL.md").read_text() == "official skill"
            (target / "SKILL.md").write_text("user edited skill")
            hooks.uninstall()
            assert (target / "SKILL.md").read_text() == "user edited skill"
            assert not (target / "LICENSE").exists()
    with patch.object(startup, "call_plugin_hook") as dependency_hook:
        startup.TypeSafeDependencies(None).execute()
        dependency_hook.assert_called_once_with("typesafe_ai", "ensure_dependencies", raise_on_error=False)
    with patch.object(startup, "call_plugin_hook", return_value=True), patch.object(startup, "version", return_value="changed"), patch.object(startup.process, "restart_process") as restart:
        startup.TypeSafeDependencies(None).execute()
        restart.assert_called_once()
    with patch.object(startup, "call_plugin_hook", return_value=False), patch.object(startup.process, "restart_process") as restart:
        startup.TypeSafeDependencies(None).execute()
        restart.assert_not_called()
    with patch.object(hooks.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")), patch.object(hooks.PrintStyle, "error"):
        assert hooks.ensure_dependencies(raise_on_error=False) is False
        try:
            hooks.install()
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError("Plugin installation ignored failed dependencies")
    print("PASS: validation, SDK headers/batches/Box, image limits/orientation/metadata, error propagation, startup/install hooks, safe cleanup")


if __name__ == "__main__":
    asyncio.run(main())
