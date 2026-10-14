import { drawProcessStep, drawMessageToolSimple } from "/js/messages.js";
import { renderResults } from "/plugins/typesafe_ai/webui/results.js";

export default function (context) {
  if (context.tool_name !== "typesafe_query") return;
  context.handler = (log) => {
    const data = log.kvps?._typesafe_result;
    if (!data?.cards) return drawMessageToolSimple({ ...log, code: "JEV" });
    const result = drawProcessStep({
      id: log.id, title: log.heading, code: "JEV", kvps: {}, content: "", log,
    });
    result.detail.querySelector(".typesafe-results")?.remove();
    if (!result.detailPending) result.detail.querySelector(":scope > .process-step-detail-scroll").prepend(renderResults(data, log.content));
    return result;
  };
}
