const text = (value) => typeof value === "string" ? value : JSON.stringify(value);
const percent = (value) => `${(value * 100).toFixed(1)}%`;

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = text(value);
  return element;
}

function probability(label, value) {
  const row = node("div", "typesafe-probability");
  row.append(node("span", "typesafe-label", label), node("span", "typesafe-percent", percent(value)));
  const meter = node("meter", "");
  meter.min = 0;
  meter.max = 1;
  meter.value = value;
  meter.setAttribute("aria-label", `${label}: ${percent(value)}`);
  row.append(meter);
  return row;
}

export function renderResults(data, raw = "") {
  if (!document.querySelector('link[data-typesafe-style]')) {
    const style = node("link", "");
    style.rel = "stylesheet";
    style.href = "/plugins/typesafe_ai/webui/results.css";
    style.dataset.typesafeStyle = "true";
    document.head.append(style);
  }
  const root = node("section", "typesafe-results");
  root.setAttribute("aria-label", "TypeSafe Jev judgments");
  const header = node("div", "typesafe-summary");
  header.append(node("strong", "", "Jev judgments"), node("span", "", `${data.model} · ${data.elapsed_ms} ms`));
  root.append(header);
  const grid = node("div", "typesafe-grid");
  for (const answer of data.cards) {
    const card = node("article", "typesafe-card");
    const heading = node("div", "typesafe-card-heading");
    heading.append(node("strong", "", answer.id), node("span", "typesafe-kind", answer.type));
    card.append(heading, node("p", "typesafe-question", answer.instructions));
    if (answer.type === "noul") {
      card.append(node("div", "typesafe-value", percent(answer.noul)), node("p", "typesafe-caption", "Probability of yes"));
      card.append(probability("Yes", answer.noul), probability("No", 1 - answer.noul));
    } else {
      const levels = answer.distribution.map((entry) => Number(entry.label));
      const value = answer.type === "choice" ? answer.choice : `${Number(answer.score.toFixed(3))} / ${Math.max(...levels)}`;
      card.append(node("div", "typesafe-value", value));
      if (answer.type === "score") card.append(node("p", "typesafe-caption", "Expected score · levels start at 0"));
      card.append(node("p", "typesafe-caption", `Confidence ${percent(answer.confidence)}`));
      for (const entry of answer.distribution) {
        const label = entry.description == null ? entry.label : `${entry.label} · ${text(entry.description)}`;
        card.append(probability(label, entry.probability));
      }
    }
    grid.append(card);
  }
  root.append(grid);
  const usage = data.usage || {};
  root.append(node("p", "typesafe-footnote", `Tokens: ${usage.input_tokens ?? "—"} input · ${usage.output_tokens ?? "—"} output. Confidence describes the answer distribution, not a guarantee of correctness.`));
  const detail = node("details", "typesafe-raw");
  detail.append(node("summary", "", "Raw result (JSON)"), node("pre", "", raw));
  root.append(detail);
  return root;
}
