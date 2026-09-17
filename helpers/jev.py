"""The TypeSafe SDK boundary, shared by the tool and its runnable check."""

import json
import math
import time


def validate_request(state, questions):
    if not isinstance(state, (str, dict, list)):
        raise ValueError("state must be text, an object, or an array.")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a nonempty object keyed by question ID.")
    json.dumps({"state": state, "questions": questions}, allow_nan=False)
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each question needs a nonempty string ID.")
        if not isinstance(question, dict) or question.get("type") not in {"choice", "noul", "score"}:
            raise ValueError(f"Question {name!r} needs type choice, noul, or score.")
        if set(question) - {"type", "instructions", "criteria"}:
            raise ValueError(f"Question {name!r} accepts only type, instructions, and criteria.")
        instructions = question.get("instructions")
        if not isinstance(instructions, (str, dict, list)) or not instructions:
            raise ValueError(f"Question {name!r} needs instructions as text, an object, or an array.")
        kind, criteria = question["type"], question.get("criteria")
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
    model = config.get("model", "jev-latest")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Set a nonempty model name in TypeSafe AI settings.")
    timeout = config.get("timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 300:
        raise ValueError("TypeSafe timeout must be between 1 and 300 seconds.")
    return model.strip(), timeout


async def query(client, state, questions, model):
    import msgspec

    validate_request(state, questions)
    start = time.monotonic()
    response = await client.system_one(state=state, questions=questions, model=model)
    result = msgspec.to_builtins(response)
    if set(result["answers"]) != set(questions):
        raise ValueError("TypeSafe returned an incomplete set of answers; do not act on this result.")
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    return result


def result_cards(result, questions):
    cards = []
    for name, answer in result["answers"].items():
        card = {"id": name, "instructions": questions[name]["instructions"], **answer}
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
            "elapsed_ms": result["elapsed_ms"], "cards": cards}
