import argparse
import ctypes
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from PySide6 import QtCore, QtWebChannel, QtWebEngineCore, QtWebEngineWidgets, QtWidgets
    WebPage = QtWebEngineCore.QWebEnginePage
    WebProfile = QtWebEngineCore.QWebEngineProfile
except ImportError:
    from PySide2 import QtCore, QtWebChannel, QtWebEngineWidgets, QtWidgets
    WebPage = QtWebEngineWidgets.QWebEnginePage
    WebProfile = QtWebEngineWidgets.QWebEngineProfile


class Bridge(QtCore.QObject):
    stateChanged = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.floating = True

    @QtCore.Slot(result=str)
    def getState(self):
        return json.dumps(dict(asset="SM_ColorTest", status="pass", statusText="通过",
                               issues=[], candidates=[], selectedId="", feedback="",
                               hasSelection=True, canLocate=False, canRescan=True,
                               canPublish=True, floating=self.floating, tools={"platform": "pc"}))

    @QtCore.Slot(str, str)
    def dispatch(self, action, payload):
        pass


GEOMETRY = """
function box(node) {
    var r = node.getBoundingClientRect()
    return [r.left, r.top, r.right, r.bottom]
}
var rows = Array.from(document.querySelectorAll('[data-group-toggle]'), function(el) {
    return {key: el.dataset.groupToggle, label: el.textContent, expanded: el.getAttribute('aria-expanded'),
            rect: box(el), ink: box(el.querySelector('span')), color: getComputedStyle(el).color,
            cssBackground: getComputedStyle(el).backgroundColor}
})
var publish = document.querySelector('[data-action=publish]')
if (publish && publish.offsetHeight) {
    var range = document.createRange()
    range.selectNodeContents(publish)
    rows.push({key:'publish-action', rect:box(publish), ink:box(range), color:getComputedStyle(publish).color,
               cssBackground:getComputedStyle(publish).backgroundColor, disabled:publish.disabled})
}
return {rows:rows, viewport:[innerWidth,innerHeight], engine:navigator.userAgent,
        whereSupported:CSS.supports('selector(:where(button))')}
"""


def luminance(rgb):
    srgb = [c / 255 for c in rgb]
    linear = [v / 12.92 if v < .04045 else ((v + .055) / 1.055) ** 2.4 for v in srgb]
    return sum(c * k for c, k in zip(linear, (.2126, .7152, .0722)))


def pixel_colors(image, box, viewport):
    sx, sy = image.width() / viewport[0], image.height() / viewport[1]
    x1, y1, x2, y2 = [round(v*s) for v, s in zip(box, (sx, sy, sx, sy))]
    if not (0 <= x1 < x2 <= image.width() and 0 <= y1 < y2 <= image.height()):
        raise ValueError("Sample outside the captured renderer: %r" % (box,))
    return Counter(image.pixelColor(x, y).getRgb()[:3] for y in range(y1, y2) for x in range(x1, x2))


def sample(image, row, viewport):
    x1, y1, x2, y2 = row["rect"]
    primary = row["key"] == "publish-action"
    left = x1 + (x2 - x1) * (.13 if primary else .70)
    patch = (left, y1 + 6, left + 8, y2 - 6)
    background = pixel_colors(image, patch, viewport).most_common(1)[0][0]
    label = pixel_colors(image, row["ink"], viewport)
    expected = tuple(map(int, re.findall(r"\d+", row["color"])[:3]))
    # Solid or nearly solid glyph-interior pixels closest to the CSS foreground.
    ink = min(label, key=lambda candidate: sum((a-b)**2 for a, b in zip(candidate, expected)))
    low, high = sorted((luminance(background), luminance(ink)))
    ratio = (high + .05) / (low + .05)
    surface_ok = min(background) >= 225 if primary else max(background) <= 105
    return dict(background=background, ink=ink, contrast=round(ratio, 2),
                passes=surface_ok and ratio >= 4.5 and not row.get("disabled", False))


def run(bundle, output):
    if sys.platform == "win32":
        ctypes.windll.ole32.CoInitializeEx(None, 2)
    app = QtWidgets.QApplication([])
    app.setApplicationName("AssetForgePaletteCheck")
    view = QtWebEngineWidgets.QWebEngineView()
    view.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
    view.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowDoesNotAcceptFocus)
    screens = app.screens()
    secondary = next((s for s in screens if s is not app.primaryScreen()), app.primaryScreen())
    view.move(secondary.availableGeometry().topLeft() + QtCore.QPoint(40, 35))
    view.resize(370, 970)
    profile = WebProfile(view)
    page = WebPage(profile, view)
    view.setPage(page)
    channel = QtWebChannel.QWebChannel(page)
    bridge = Bridge(channel)
    channel.registerObject("workbench", bridge)
    page.setWebChannel(channel)
    output.mkdir(parents=True, exist_ok=True)
    evidence = dict(qt=QtCore.qVersion(), css_sha256=hashlib.sha256((bundle/"app.css").read_bytes()).hexdigest(),
                    js_sha256=hashlib.sha256((bundle/"app.js").read_bytes()).hexdigest(), cases={})
    cases = iter((mode, opened) for mode in ("floating", "docked") for opened in (False, True))
    current = []
    failures = []
    timer = QtCore.QTimer.singleShot

    def finish(code):
        evidence.update(failures=failures, passed=(code == 0))
        (output/"contrast.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf8")
        print(json.dumps(dict(version=evidence["qt"], passed=(code == 0), failures=failures), ensure_ascii=True), flush=True)
        app.exit(code)

    def advance():
        try:
            mode, opened = next(cases)
        except StopIteration:
            finish(1 if failures else 0)
            return
        key = mode + ("_open" if opened else "_closed")
        current[:] = [key, opened]
        bridge.floating = mode == "floating"
        bridge.stateChanged.emit(bridge.getState())
        def toggle():
            page.runJavaScript("""
                Array.from(document.querySelectorAll('[data-group-toggle]')).forEach(function(e) {
                    if (e.getAttribute('aria-expanded') !== '%s') e.click()
                })
                var scroller = document.querySelector('[data-workbench-scroll]')
                if (scroller) scroller.scrollTop = 0
            """ % str(opened).lower())
            timer(350, lambda: page.runJavaScript("document.title='af-color:"+key+":'+JSON.stringify((function(){"+GEOMETRY+"})())"))
        timer(180, toggle)

    def result(title):
        if not title.startswith("af-color:"):
            return
        try:
            _, key, payload = title.split(":", 2)
            data = json.loads(payload)
            image = view.grab().toImage()
            if image.isNull() or not image.save(str(output/(key+".png"))):
                raise RuntimeError("Qt could not capture the local view")
            rows = data["rows"]
            expected = {"inspect", "locate", "publish", "textures", "preset", "log"}
            if current[1]:
                expected.add("publish-action")
            if {r["key"] for r in rows} != expected:
                raise AssertionError("Unexpected tool controls: %r" % rows)
            for row in rows:
                actual = sample(image, row, data["viewport"])
                row.update(actual)
                if not actual["passes"] or ("expanded" in row and row["expanded"] != str(current[1]).lower()):
                    failures.append(key+"/"+row["key"])
            evidence["cases"][key] = data
            timer(30, advance)
        except Exception as exc:
            failures.append(repr(exc))
            finish(2)

    view.titleChanged.connect(result)
    page.loadFinished.connect(lambda ok: timer(650, advance) if ok else finish(3))
    view.load(QtCore.QUrl.fromLocalFile(str((bundle/"index.html").resolve())))
    view.show()
    timer(30000, lambda: finish(4))
    return app.exec_()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render the shipped workbench with mayapy and check actual label contrast.")
    parser.add_argument("output", type=Path, help="Directory for four local Qt renderer PNGs and contrast.json")
    parser.add_argument("--bundle", type=Path,
                        default=Path(__file__).resolve().parents[2]/"Plugins/AssetForge/Resources/Workbench/web")
    args = parser.parse_args()
    sys.exit(run(args.bundle, args.output))
