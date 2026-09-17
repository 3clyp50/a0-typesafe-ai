## typesafe_query
Ask TypeSafe's Jev model for fast typed judgments about supplied state. Returns JSON answers, probabilities, model, elapsed time, and token usage, with visual result cards in chat.

- Use for semantic classification, routing, verification, candidate selection, and rubric scoring. Jev does not generate prose, explanations, or unseen values.
- Read the official `typesafe-ai` skill with `skills_tool` for design guidance and live documentation. It is installed under `/a0/usr/skills/typesafe-ai`.
- Send independent questions over the same state together in ONE call. A question cannot see another question's answer. Use a later call only for a real dependency.
- `state`: text, a JSON object, or an array containing the evidence. Do not send unrelated chat history or secrets.
- `questions`: an object mapping unique IDs to `{type, instructions, criteria?}`. Instructions and descriptions may be strings, objects, or arrays. IDs are not model instructions; spell out the complete question.
- `choice`: criteria is an object with at least two named alternatives, mapped to descriptions or null. Include an other/no-match option when needed. Returns choice, probabilities, confidence.
- `noul`: probability of yes (0–1). Optional criteria has true/false descriptions. A value near 0.5 means uncertainty, not medium intensity. No separate confidence.
- `score`: criteria is an ordered array of at least two concrete levels, indexed from 0. Returns a probability-weighted score, legend, probabilities, confidence. Do not call this score a percentage unless you explicitly normalize it.
- Model, API key, and timeout are managed in plugin settings; never pass credentials as tool arguments. Confidence is distribution concentration, not a guarantee or authorization to act. Report uncertainty and retain raw judgments.

Input schema for tool_args:
```json
{
  "type": "object",
  "properties": {
    "state": {"type": ["string", "object", "array"]},
    "questions": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "properties": {
          "type": {"type": "string", "enum": ["choice", "noul", "score"]},
          "instructions": {"type": ["string", "object", "array"]},
          "criteria": {"type": ["object", "array", "null"]}
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
