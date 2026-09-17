import json
import os

from helpers.plugins import get_plugin_config
from helpers.secrets import get_secrets_manager
from helpers.tool import Response, Tool
from usr.plugins.typesafe_ai.helpers.jev import query, result_cards, validate_config, validate_request


class TypeSafeQuery(Tool):
    async def execute(self, state=None, questions=None, **kwargs):
        try:
            if kwargs:
                raise ValueError("Use only state and questions; model and credentials belong in plugin settings.")
            validate_request(state, questions)
            config = get_plugin_config("typesafe_ai", agent=self.agent) or {}
            model, timeout = validate_config(config)
            key = (config.get("api_key") or "").strip()
            key = key or get_secrets_manager(self.agent.context).load_secrets().get("TYPESAFE_API_KEY", "")
            key = key or os.environ.get("TYPESAFE_API_KEY", "")
            if not key.strip():
                raise ValueError("Add an API key in Plugins → TypeSafe AI → Settings, or set TYPESAFE_API_KEY in Agent Zero's environment/secrets.")
        except (TypeError, ValueError) as error:
            return Response(message=json.dumps({"error": str(error)}), break_loop=False)

        try:
            from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAPIError, TypeSafeError
        except ImportError:
            return Response(message=json.dumps({"error": "TypeSafe SDK is missing. Reinstall/update this plugin through Plugins to run its installation hook."}), break_loop=False)

        self.log.update(heading=f"Jev · Evaluating {len(questions)} questions")
        try:
            async with AsyncTypeSafeClient(
                api_key=key.strip(), model=model, timeout=timeout,
                base_url="https://api.typesafe.ai", retry=RetryPolicy(max_retries=1),
            ) as client:
                result = await query(client, state, questions, model)
        except TypeSafeAPIError as error:
            hint = {
                401: "Check your TypeSafe API key.", 403: "Check your TypeSafe account permissions.",
                402: "Check your TypeSafe account credit.", 404: "Check the configured model name.",
                422: "Check the question criteria and state against the TypeSafe skill.",
                429: "TypeSafe rate limit reached; try again later.",
            }.get(error.status, "TypeSafe could not complete the request; try again later.")
            return Response(message=json.dumps({"error": hint, "status": error.status}), break_loop=False)
        except (TypeSafeError, ValueError) as error:
            return Response(message=json.dumps({"error": "TypeSafe request failed or returned invalid answers.", "kind": type(error).__name__}), break_loop=False)

        self.log.update(
            heading=f"Jev · {len(questions)} judgments · {result['elapsed_ms']} ms",
            _typesafe_result=result_cards(result, questions),
        )
        return Response(message=json.dumps(result, ensure_ascii=False), break_loop=False)
