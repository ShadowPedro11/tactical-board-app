from pathlib import Path

PATCH = """
<style id="canvas-quality-fix">
  html, body {
    margin: 0 !important;
    padding: 0 !important;
    background: #20602e !important;
    overflow: auto !important;
  }

  canvas {
    max-width: none !important;
    max-height: none !important;
    image-rendering: auto !important;
  }
</style>

<script id="canvas-quality-fix-script">
(function () {
  function fixCanvasSize() {
    const canvas = document.querySelector("canvas");
    if (!canvas) return;

    const w = canvas.width;
    const h = canvas.height;

    if (!w || !h) return;

    canvas.style.setProperty("width", w + "px", "important");
    canvas.style.setProperty("height", h + "px", "important");
    canvas.style.setProperty("max-width", "none", "important");
    canvas.style.setProperty("max-height", "none", "important");
  }

  window.addEventListener("load", fixCanvasSize);
  window.addEventListener("resize", fixCanvasSize);

  const observer = new MutationObserver(fixCanvasSize);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true
  });

  setInterval(fixCanvasSize, 500);
})();
</script>
"""

possible_files = [
    Path("build/web/index.html"),
    Path("build/index.html"),
]

possible_files += list(Path(".").glob("**/build/**/index.html"))

patched = False

for path in possible_files:
    if not path.exists():
        continue

    html = path.read_text(encoding="utf-8")

    if "canvas-quality-fix" in html:
        print(f"Already patched: {path}")
        patched = True
        continue

    if "</head>" in html:
        html = html.replace("</head>", PATCH + "\n</head>")
    else:
        html = PATCH + "\n" + html

    path.write_text(html, encoding="utf-8")
    print(f"Patched: {path}")
    patched = True

if not patched:
    raise SystemExit("Could not find pygbag index.html")