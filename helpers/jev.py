"""The TypeSafe SDK boundary, shared by the tool and its runnable check."""

import base64
import io
import json
import math
import time


def validate_request(state, questions, images=None):
    if not isinstance(state, (str, dict, list)):
        raise ValueError("state must be text, an object, or an array.")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a nonempty object keyed by question ID.")
    if images is not None and not isinstance(images, dict):
        raise ValueError("images must map image placeholders to local PNG or JPEG paths.")
    json.dumps({"state": state, "questions": questions}, allow_nan=False)
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each question needs a nonempty string ID.")
        if not isinstance(question, dict) or question.get("type") not in {"choice", "noul", "score", "box"}:
            raise ValueError(f"Question {name!r} needs type choice, noul, score, or box.")
        allowed = {"type", "instructions", "image"} if question["type"] == "box" else {"type", "instructions", "criteria"}
        if set(question) - allowed:
            raise ValueError(f"Question {name!r} accepts only {', '.join(sorted(allowed))}.")
        instructions = question.get("instructions")
        if not isinstance(instructions, (str, dict, list)) or not instructions:
            raise ValueError(f"Question {name!r} needs instructions as text, an object, or an array.")
        kind, criteria = question["type"], question.get("criteria")
        if kind == "box":
            image = question.get("image")
            if not images or (image is None and len(images) != 1):
                raise ValueError(f"Box {name!r} needs an image; with several images, set image to its placeholder.")
            if image is not None and (not isinstance(image, str) or image not in images):
                raise ValueError(f"Box {name!r} image must name a placeholder in images.")
            continue
        if kind == "choice" and (not isinstance(criteria, dict) or len(criteria) < 2):
            raise ValueError(f"Choice {name!r} needs at least two named criteria.")
        if kind == "score" and (not isinstance(criteria, list) or len(criteria) < 2):
            raise ValueError(f"Score {name!r} needs at least two ordered criteria.")
        if kind == "noul" and criteria is not None and (
            not isinstance(criteria, dict) or set(criteria) - {"true", "false"}
        ):
            raise ValueError(f"Noul {name!r} criteria may only describe true and false.")
        if isinstance(criteria, dict) and any(not isinstance(k, str) or not k.strip() for k in criteria):
            raise ValueError(f"Question {name!r} has an empty or non-string criterion name.")
        values = criteria.values() if isinstance(criteria, dict) else criteria or []
        if any(not isinstance(v, (str, dict, list)) and not (v is None and kind != "score") for v in values):
            raise ValueError(f"Question {name!r} criteria must be descriptions, not numbers or booleans.")


def validate_config(config):
    if not isinstance(config.get("api_key", ""), str):
        raise ValueError("TypeSafe API key must be text.")
    model = config.get("model", "jev-1.14.0")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Set a nonempty model name in TypeSafe AI settings.")
    timeout = config.get("timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 300:
        raise ValueError("TypeSafe timeout must be between 1 and 300 seconds.")
    model = model.strip()
    return ("jev-1.14.0" if model in {"jev-latest", "jev-preview"} else model), timeout


def prepare_images(images):
    if not images:
        return {}, {}
    from helpers.images import resolve_ref
    from PIL import Image, ImageOps
    from typesafe_sdk import Image as ImageAsset

    assets, previews = {}, {}
    for name, reference in (images or {}).items():
        if not isinstance(name, str) or not name.strip() or len(name.encode()) > 1024:
            raise ValueError("Each image needs a nonempty placeholder of at most 1,024 UTF-8 bytes.")
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"Image {name!r} needs a local PNG or JPEG path.")
        path = resolve_ref(reference)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"Image {name!r} exceeds the 16 MiB file limit.")
        try:
            original = Image.open(path)
        except Image.DecompressionBombError as error:
            raise ValueError(f"Image {name!r} exceeds safe image dimensions.") from error
        with original:
            if original.format not in {"PNG", "JPEG"} or getattr(original, "is_animated", False):
                raise ValueError(f"Image {name!r} must be a still PNG or JPEG.")
            width, height = original.size
            if not (256 <= width <= 1568 and 256 <= height <= 1568 and 78400 <= width * height <= 2458624):
                raise ValueError(f"Image {name!r} needs sides of 256–1568 pixels and at least 78,400 pixels in total. Resize or pad it first.")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.info.clear()
            buffer = io.BytesIO()
            image.save(buffer, format=original.format, **({"quality": 90} if original.format == "JPEG" else {}))
            fmt = "png" if original.format == "PNG" else "jpeg"
        content = buffer.getvalue()
        encoded = base64.b64encode(content).decode("ascii")
        assets[name] = ImageAsset(content)
        previews[name] = {"name": path.name, "src": f"data:image/{fmt};base64,{encoded}"}
    if sum(len(asset.data) for asset in assets.values()) > 32 * 1024 * 1024:
        raise ValueError("Image uploads exceed the 32 MiB request limit. Send fewer or smaller images.")
    return assets, previews


async def query(client, state, questions, model, assets=None):
    from typesafe_sdk import Box

    validate_request(state, questions, assets)
    wire_questions = {name: Box(instructions=question["instructions"]) if question["type"] == "box" else question
                      for name, question in questions.items()}
    start = time.monotonic()
    response = await client.system_one(
        state=state, questions=wire_questions, model=model,
        assets=assets or None,
        extra_headers={"TypeSafe-Danger-Zone-Long-Context": "true", "TypeSafe-Danger-Zone-Images": "true"},
    )
    result = response.model_dump(mode="json")
    if set(result["answers"]) != set(questions):
        raise ValueError("TypeSafe returned an incomplete set of answers; do not act on this result.")
    for name, question in questions.items():
        answer = result["answers"][name]
        if answer.get("type") != question["type"]:
            raise ValueError("TypeSafe returned an unexpected answer type.")
        if question["type"] == "box":
            box = answer.get("box")
            if not isinstance(box, dict) or set(box) != {"top", "bottom", "left", "right"}:
                raise ValueError("TypeSafe returned invalid box edges.")
            values = list(box.values())
            if answer.get("confidence") is not None:
                values.append(answer["confidence"])
            if any(type(v) not in {int, float} or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                raise ValueError("TypeSafe returned invalid box coordinates or confidence.")
            if box["left"] >= box["right"] or box["top"] >= box["bottom"]:
                raise ValueError("TypeSafe returned an empty or inverted box.")
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    return result


def result_cards(result, questions, images=None):
    images = images or {}
    cards = []
    for name, answer in result["answers"].items():
        card = {"id": name, "instructions": questions[name]["instructions"], **answer}
        if answer["type"] == "box":
            card["image"] = questions[name].get("image") or next(iter(images), None)
        legend = answer.get("legend", {})
        card["distribution"] = [
            {"label": str(label), "probability": probability,
             "description": legend.get(label, legend.get(str(label)))}
            for label, probability in answer.get("probabilities", {}).items()
        ]
        card.pop("probabilities", None)
        card.pop("legend", None)
        cards.append(card)
    return {"model": result["model"], "usage": result["usage"],
            "elapsed_ms": result["elapsed_ms"], "cards": cards, "images": images}
