import { renderResults } from "../webui/results.js";

export async function checkResults() {
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const canvas = document.createElement("canvas");
  canvas.width = 600;
  canvas.height = 400;
  const src = canvas.toDataURL("image/png");
  const data = {
    model: "jev-test", elapsed_ms: 1, usage: {},
    images: { first: { name: "<img onerror=alert(1)>", src }, second: { name: "Other image", src } },
    cards: [
      { id: "First target", type: "box", instructions: "Find it", image: "first", confidence: .9, box: { left: .25, top: .25, right: .75, bottom: .75 } },
      { id: "Second target", type: "box", instructions: "Find it", image: "second", confidence: .8, box: { left: .1, top: .2, right: .3, bottom: .4 } },
    ],
  };
  const root = renderResults(data, "{}");
  root.style.width = "800px";
  root.style.position = "fixed";
  root.style.top = "0";
  root.style.left = "0";
  document.body.append(root);
  try {
    const style = document.querySelector("link[data-typesafe-style]");
    if (!style.sheet) await new Promise((resolve, reject) => {
      style.addEventListener("load", resolve, { once: true });
      style.addEventListener("error", reject, { once: true });
    });
    const pictures = [...root.querySelectorAll(".typesafe-image-frame img")];
    await Promise.all(pictures.map((picture) => picture.decode()));
    const boxes = [...root.querySelectorAll(".typesafe-box")];
    assert(boxes.length === 2, "Missing boxes");
    assert(boxes[0].textContent === "First target" && boxes[1].textContent === "Second target", "Wrong image association");
    assert(root.querySelectorAll("img").length === 2, "Image name interpreted as HTML");
    for (const width of [800, 360]) {
      root.style.width = `${width}px`;
      const image = pictures[0].getBoundingClientRect();
      const box = boxes[0].getBoundingClientRect();
      assert(image.width > 100 && image.height > 50, "Image was not laid out");
      assert(Math.abs(box.left - image.left - image.width * .25) < 1, "Left edge shifted after resize");
      assert(Math.abs(box.top - image.top - image.height * .25) < 1, "Top edge shifted after resize");
      assert(Math.abs(box.width - image.width * .5) < 1 && Math.abs(box.height - image.height * .5) < 1, "Box dimensions shifted after resize");
    }
    const toggle = root.querySelector('input[type="checkbox"]');
    toggle.checked = false;
    toggle.dispatchEvent(new Event("change"));
    assert(getComputedStyle(boxes[0]).display === "none", "Hide boxes failed");
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    assert(getComputedStyle(boxes[0]).display !== "none", "Show boxes failed");
    const invalid = renderResults({ ...data, cards: [{ ...data.cards[0], box: { left: -.1, top: .2, right: .5, bottom: .8 } }] });
    assert(!invalid.querySelector(".typesafe-box"), "Invalid edges were drawn");
    const unknown = renderResults({ ...data, cards: [{ ...data.cards[0], confidence: null }] });
    assert(unknown.textContent.includes("Confidence unavailable"), "Missing confidence shown as zero");
    const unsafe = renderResults({ ...data, images: { first: { name: "unsafe", src: "https://example.com/pixel.png" } } });
    assert(!unsafe.querySelector("img"), "Remote preview URL accepted");
    return "PASS: image associations, responsive box geometry, show/hide, invalid edges, safe rendering";
  } finally {
    root.remove();
  }
}
