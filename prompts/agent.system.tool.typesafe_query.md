## typesafe_query
Ask TypeSafe's Jev model for fast typed judgments about supplied text or images. Returns JSON answers, probabilities, bounding boxes, model, elapsed time, and token usage, with visual result cards and image overlays in chat.

- Use for semantic classification, routing, verification, candidate selection, and rubric scoring. Jev does not generate prose, explanations, or unseen values.
- Read the official `typesafe-ai` skill with `skills_tool` for design guidance and live documentation. It is installed under `/a0/usr/skills/typesafe-ai`.
- Send independent questions over the same state together in ONE call. A question cannot see another question's answer. Use a later call only for a real dependency.
- `state`: text, a JSON object, or an array containing the evidence. Do not send unrelated chat history or secrets.
- `images` (optional): map unique image placeholders (prefer UUIDs) to local PNG/JPEG file paths. Put each placeholder in state, instructions, or criteria where its image belongs. Every image must be referenced; keys are not replaced. URLs and OpenAI image blocks are not supported. Images are sent explicitly to TypeSafe and previewed in the result.
- Images must be still PNG/JPEG, at most 16 MiB, with each side 256–1568 pixels and at least 78,400 total pixels. Resize, crop, or pad other images before calling. The plugin rotates EXIF-oriented pixels upright and strips metadata; it does not resize. Image and long-context headers are enabled; provider size and token limits still apply.
- `questions`: an object mapping unique IDs to `{type, instructions, criteria?}`. Instructions and descriptions may be strings, objects, or arrays. IDs are not model instructions; spell out the complete question.
- `choice`: criteria is an object with at least two named alternatives, mapped to descriptions or null. Include an other/no-match option when needed. Returns choice, probabilities, confidence.
- `noul`: probability of yes (0–1). Optional criteria has true/false descriptions. A value near 0.5 means uncertainty, not medium intensity. No separate confidence.
- `score`: criteria is an ordered array of at least two concrete levels, indexed from 0. Returns a probability-weighted score, legend, probabilities, confidence. Do not call this score a percentage unless you explicitly normalize it.
- `box`: instructions name one target and its image, e.g. "the red rectangle in `photo`". No criteria. Optional `image` names the placeholder to display the box on; REQUIRED with multiple images. With one image it is inferred. This field is for the UI and is not sent to TypeSafe. Returns normalized `left`, `top`, `right`, `bottom` edges and confidence. The default model is `jev-1.14.0` for all requests; legacy aliases resolve to 1.14 and explicit version pins are honored. Ask a Noul presence question alongside Box: even an absent target receives a box. Images and Box are experimental; read https://docs.typesafe.ai/images and https://docs.typesafe.ai/primitives/box for the current contract.
- Model, API key, and timeout are managed in plugin settings; never pass credentials as tool arguments. Confidence is distribution concentration, not a guarantee or authorization to act. Report uncertainty and retain raw judgments.

Input schema for tool_args:
```json
{
  "type": "object",
  "properties": {
    "state": {"type": ["string", "object", "array"]},
    "images": {"type": "object", "additionalProperties": {"type": "string"}},
    "questions": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "properties": {
          "type": {"type": "string", "enum": ["choice", "noul", "score", "box"]},
          "instructions": {"type": ["string", "object", "array"]},
          "criteria": {"type": ["object", "array", "null"]},
          "image": {"type": "string", "description": "Box only: placeholder from images; required with multiple images."}
        },
        "required": ["type", "instructions"],
        "additionalProperties": false
      }
    }
  },
  "required": ["state", "questions"],
  "additionalProperties": false
}
```

Example:
```json
{
  "tool_name": "typesafe_query",
  "tool_args": {
    "state": {"message": "I was charged twice. Please refund the duplicate today."},
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle `message`?",
        "criteria": {"billing": "Payments or refunds", "technical": "Software problems", "other": "Neither team fits"}
      },
      "refund_requested": {"type": "noul", "instructions": "Does `message` request a refund?"},
      "urgency": {
        "type": "score",
        "instructions": "How time-sensitive is the request in `message`?",
        "criteria": ["No deadline expressed", "Requested within a week", "Requested today or immediately"]
      }
    }
  }
}
```
