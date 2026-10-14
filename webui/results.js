const text = (value) => typeof value === "string" ? value : JSON.stringify(value);
const percent = (value) => `${(value * 100).toFixed(1)}%`;
const boxConfidence = (value) => value == null ? "Confidence unavailable" : `Confidence ${percent(value)}`;

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

function imageResults(data) {
  const gallery = node("div", "typesafe-images");
  let boxCount = 0;
  for (const [id, image] of Object.entries(data.images || {})) {
    if (typeof image.src !== "string" || !/^data:image\/(png|jpeg);base64,[A-Za-z0-9+/]+=*$/.test(image.src)) continue;
    const figure = node("figure", "typesafe-image");
    const frame = node("div", "typesafe-image-frame");
    const picture = node("img", "");
    picture.src = image.src;
    picture.alt = image.name || id;
    frame.append(picture);
    for (const answer of data.cards) {
      if (answer.type !== "box" || answer.image !== id) continue;
      const edges = answer.box;
      if (!edges || ![edges.left, edges.right, edges.top, edges.bottom].every((v) => Number.isFinite(v) && v >= 0 && v <= 1) || edges.left >= edges.right || edges.top >= edges.bottom) continue;
      const box = node("div", "typesafe-box");
      box.style.left = `${edges.left * 100}%`;
      box.style.top = `${edges.top * 100}%`;
      box.style.width = `${(edges.right - edges.left) * 100}%`;
      box.style.height = `${(edges.bottom - edges.top) * 100}%`;
      box.title = `${answer.id} · ${boxConfidence(answer.confidence)}`;
      box.append(node("span", "typesafe-box-label", answer.id));
      frame.append(box);
      boxCount++;
    }
    figure.append(frame, node("figcaption", "typesafe-caption", image.name || id));
    gallery.append(figure);
  }
  const section = node("div", "typesafe-image-results");
  if (boxCount) {
    const label = node("label", "typesafe-box-toggle");
    const toggle = node("input", "");
    toggle.type = "checkbox";
    toggle.checked = true;
    toggle.addEventListener("change", () => gallery.classList.toggle("typesafe-hide-boxes", !toggle.checked));
    label.append(toggle, document.createTextNode("Show bounding boxes"));
    section.append(label);
  }
  section.append(gallery);
  return section;
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
  if (Object.keys(data.images || {}).length) root.append(imageResults(data));
  const grid = node("div", "typesafe-grid");
  for (const answer of data.cards) {
    const card = node("article", "typesafe-card");
    const heading = node("div", "typesafe-card-heading");
    heading.append(node("strong", "", answer.id), node("span", "typesafe-kind", answer.type));
    card.append(heading, node("p", "typesafe-question", answer.instructions));
    if (answer.type === "noul") {
      card.append(node("div", "typesafe-value", percent(answer.noul)), node("p", "typesafe-caption", "Probability of yes"));
      card.append(probability("Yes", answer.noul), probability("No", 1 - answer.noul));
    } else if (answer.type === "box") {
      card.append(node("div", "typesafe-value", "Bounding box"));
      card.append(node("p", "typesafe-caption", boxConfidence(answer.confidence)));
      const edges = answer.box;
      card.append(node("p", "typesafe-question", `Left ${percent(edges.left)} · Top ${percent(edges.top)} · Right ${percent(edges.right)} · Bottom ${percent(edges.bottom)}`));
      card.append(node("p", "typesafe-caption", "Edges are fractions of the image size. A box alone does not confirm the target is present."));
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
