#!/usr/bin/env python3
r"""fwgen GUI — a thin PyQt6 front-end over the headless fwgen library.

Homage to v25's "Pro Data Engine" (same toolkit, same QThread-worker +
log-stream pattern), but driving the v28 data-driven engine: pick a specs dir,
choose scenarios, a strategy and options, hit RUN. All real work lives in
`fwgen` / `fwgen_cli.generate_one`; the generation loop is factored into the
plain function `run_generation()` so it is testable WITHOUT Qt (and without a
display). The GUI is pure glue.

Run:        python3 fwgen_gui.py
Headless build-check:   QT_QPA_PLATFORM=offscreen python3 -c "import fwgen_gui; fwgen_gui.build_app()"
"""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

import fwgen as fg
from fwgen_cli import generate_one

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)


# ===========================================================================
# Headless core (no Qt) — testable directly
# ===========================================================================

def run_generation(p: dict, on_line=lambda s: None, should_stop=lambda: False):
    """Generate workbooks for the selected specs. `p` is the params dict the GUI
    builds; `on_line(str)` receives one line per scenario. Returns (results, bad)."""
    specs = fg.load_specs_dir(p["specs_dir"])
    sel = p.get("selected")
    if sel:
        specs = [s for s in specs if s.name in sel]
    out = Path(p["out"])
    fw_info = p.get("fw_info", "dup")
    clone_path = p.get("clone_path") or None
    if fw_info == "clone" and not clone_path:
        fw_info = "dup"
    results, bad = [], 0
    for spec in specs:
        if should_stop():
            on_line("… stopped.")
            break
        r = generate_one(spec, out, p["strategy"], p["n"], p["optimal"], p["budget"],
                         fw_info, clone_path, p["json"], materialize=p["materialize"],
                         chunk_rows=p["chunk_rows"], workers=p["workers"], autofit=p["autofit"])
        ok = r["valid"] == "OK"
        bad += 0 if ok else 1
        on_line(f"{r['base']:<38} rows={r['rows']:<6} chunks={r['chunks']:<3} "
                f"{r['mode']:<42} {'OK' if ok else 'INVALID: ' + '; '.join(r['valid'])}")
        results.append(r)
    return results, bad


def run_batch_json(p: dict, on_line=lambda s: None):
    jdir = fg.xlsx_dir_to_json_dir(p["out"], None, workers=p["workers"])
    n = len(list(Path(jdir).glob("*.json")))
    on_line(f"{n} JSON files → {jdir}")
    return jdir


# ===========================================================================
# Qt glue
# ===========================================================================

class _Emitter(QObject):
    """Marshals log text onto the GUI thread via a Qt signal."""
    text = pyqtSignal(str)


class _LogBridge(logging.Handler):
    """A PLAIN logging.Handler (kept separate from QObject so that interpreter
    shutdown's logging.shutdown() never touches a deleted C++ wrapper); it just
    forwards records through a QObject signal."""
    def __init__(self, emitter: "_Emitter"):
        super().__init__()
        self._emitter = emitter

    def emit(self, record):
        try:
            self._emitter.text.emit(self.format(record))
        except RuntimeError:
            pass   # Qt object already torn down (app exiting)


class Worker(QThread):
    line = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, task: str, params: dict):
        super().__init__()
        self.task = task
        self.params = params
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self.task == "gen":
                results, bad = run_generation(self.params, self.line.emit, lambda: self._stop)
                self.done.emit(f"{len(results)} workbook-set(s) → {self.params['out']}   "
                               f"{'ALL VALID' if not bad else f'{bad} INVALID'}")
            else:
                jdir = run_batch_json(self.params, self.line.emit)
                self.done.emit(f"Batch XLSX→JSON complete → {jdir}")
        except Exception:                                  # noqa: BLE001
            self.error.emit(traceback.format_exc())


class FwgenWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("fwgen — Core Input-Test Generator")
        self.resize(940, 760)
        self.worker: Worker | None = None
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        gen_tab = QWidget()
        lay = QVBoxLayout(gen_tab)

        # --- specs + output ---------------------------------------------------
        io = QGroupBox("Specs & output")
        form = QFormLayout(io)
        self.specs_edit = QLineEdit("specs")
        b_specs = QPushButton("Browse…"); b_specs.clicked.connect(self._pick_specs)
        b_load = QPushButton("Load"); b_load.clicked.connect(self._load_specs)
        row = QHBoxLayout(); row.addWidget(self.specs_edit); row.addWidget(b_specs); row.addWidget(b_load)
        form.addRow("Specs dir:", _wrap(row))
        self.out_edit = QLineEdit("out")
        b_out = QPushButton("Browse…"); b_out.clicked.connect(self._pick_out)
        orow = QHBoxLayout(); orow.addWidget(self.out_edit); orow.addWidget(b_out)
        form.addRow("Output dir:", _wrap(orow))
        lay.addWidget(io)

        # --- scenario list (checkable) ---------------------------------------
        sg = QGroupBox("Scenarios (check to include; empty = all)")
        sv = QVBoxLayout(sg)
        self.spec_list = QListWidget()
        self.spec_list.setMaximumHeight(150)
        sv.addWidget(self.spec_list)
        lay.addWidget(sg)

        # --- strategy & options ----------------------------------------------
        og = QGroupBox("Strategy & options")
        of = QFormLayout(og)
        self.strategy = QComboBox(); self.strategy.addItems(["full", "ablation", "reduce", "auto"])
        self.strategy.currentTextChanged.connect(self._sync_enabled)
        of.addRow("Strategy:", self.strategy)
        self.n = _spin(0, 0, 16); self.optimal = QCheckBox("optimal set-cover")
        nrow = QHBoxLayout(); nrow.addWidget(self.n); nrow.addWidget(self.optimal)
        of.addRow("reduce: N (2=pairwise):", _wrap(nrow))
        self.budget = _spin(64, 1, 10_000_000)
        of.addRow("auto: budget (max rows):", self.budget)
        self.fw_info = QComboBox(); self.fw_info.addItems(["dup", "skip", "clone"])
        self.fw_info.currentTextChanged.connect(self._sync_enabled)
        self.clone_edit = QLineEdit(); self.clone_edit.setPlaceholderText("reference .xlsx for FW_Info clone")
        b_clone = QPushButton("Browse…"); b_clone.clicked.connect(self._pick_clone)
        fwrow = QHBoxLayout(); fwrow.addWidget(self.fw_info); fwrow.addWidget(self.clone_edit); fwrow.addWidget(b_clone)
        of.addRow("FW_Info:", _wrap(fwrow))
        self.json = QCheckBox("write sibling .json per workbook")
        self.materialize = QCheckBox("materialize (pre-expand full product → chunkable)")
        of.addRow("", self.json); of.addRow("", self.materialize)
        self.chunk = _spin(0, 0, 10_000_000); self.workers = _spin(1, 1, 64); self.autofit = _spin(0, 0, 1000)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("chunk-rows:")); crow.addWidget(self.chunk)
        crow.addWidget(QLabel("workers:")); crow.addWidget(self.workers)
        crow.addWidget(QLabel("autofit %:")); crow.addWidget(self.autofit)
        of.addRow("Materialized output:", _wrap(crow))
        lay.addWidget(og)

        # --- actions ----------------------------------------------------------
        actions = QHBoxLayout()
        self.run_btn = QPushButton("RUN"); self.run_btn.setMinimumHeight(40); self.run_btn.clicked.connect(self._run_gen)
        self.json_btn = QPushButton("Batch XLSX→JSON (output dir)"); self.json_btn.clicked.connect(self._run_json)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self._stop)
        actions.addWidget(self.run_btn); actions.addWidget(self.json_btn); actions.addWidget(self.stop_btn)
        lay.addLayout(actions)
        lay.addStretch(1)

        # --- tabs: Generate (above) + Preview + Builder ----------------------
        self.tabs.addTab(gen_tab, "Generate")
        self.tabs.addTab(self._build_preview_tab(), "Preview (examples)")
        self.tabs.addTab(self._build_builder_tab(), "Builder (your params)")

        # --- log (shared across tabs) ----------------------------------------
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setStyleSheet("background:#111; color:#0f0; font-family: monospace;")
        outer.addWidget(self.log, 1)

        self._emitter = _Emitter()
        self._emitter.text.connect(self.log.append)
        self._bridge = _LogBridge(self._emitter)
        self._bridge.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("fwgen").addHandler(self._bridge)
        logging.getLogger("fwgen").setLevel(logging.INFO)

        self._sync_enabled()
        self._load_specs(silent=True)

    # -- helpers ----------------------------------------------------------------
    def _params(self) -> dict:
        sel = {self.spec_list.item(i).text().split("  ")[0]
               for i in range(self.spec_list.count())
               if self.spec_list.item(i).checkState() == Qt.CheckState.Checked}
        return dict(specs_dir=self.specs_edit.text() or "specs", out=self.out_edit.text() or "out",
                    selected=sel or None, strategy=self.strategy.currentText(),
                    n=self.n.value(), optimal=self.optimal.isChecked(), budget=self.budget.value(),
                    fw_info=self.fw_info.currentText(), clone_path=self.clone_edit.text(),
                    json=self.json.isChecked(), materialize=self.materialize.isChecked(),
                    chunk_rows=self.chunk.value(), workers=self.workers.value(), autofit=float(self.autofit.value()))

    def _sync_enabled(self, *_):
        s = self.strategy.currentText()
        self.n.setEnabled(s == "reduce"); self.optimal.setEnabled(s in ("reduce", "auto"))
        self.budget.setEnabled(s == "auto")
        self.clone_edit.setEnabled(self.fw_info.currentText() == "clone")

    def _append(self, text): self.log.append(text)

    def _pick_specs(self):
        d = QFileDialog.getExistingDirectory(self, "Specs dir")
        if d: self.specs_edit.setText(d); self._load_specs()

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Output dir")
        if d: self.out_edit.setText(d)

    def _pick_clone(self):
        f, _ = QFileDialog.getOpenFileName(self, "Reference .xlsx", filter="Excel (*.xlsx)")
        if f: self.clone_edit.setText(f)

    def _load_specs(self, silent=False):
        self.spec_list.clear()
        try:
            specs = fg.load_specs_dir(self.specs_edit.text() or "specs")
        except Exception as e:                              # noqa: BLE001
            if not silent: self._append(f"[load error] {e}")
            return
        for sp in specs:
            it = QListWidgetItem(f"{sp.name}  ({sp.combos} combos · {len(sp.slots)} slots)")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            self.spec_list.addItem(it)
        self._append(f"Loaded {len(specs)} specs from {self.specs_edit.text() or 'specs'}")
        self._refresh_spec_combos()

    # -- run --------------------------------------------------------------------
    def _start(self, task, params=None):
        if self.worker and self.worker.isRunning():
            return
        self.run_btn.setEnabled(False); self.json_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.worker = Worker(task, params or self._params())
        self.worker.line.connect(self._append)
        self.worker.done.connect(self._finish)
        self.worker.error.connect(lambda e: (self._append(f"[ERROR]\n{e}"), self._finish("failed")))
        self.worker.start()

    def _run_gen(self):
        self._append(f"\n=== RUN gen ({self.strategy.currentText()}) ===")
        self._start("gen")

    def _run_json(self):
        self._append("\n=== Batch XLSX→JSON ===")
        self._start("json")

    def _stop(self):
        if self.worker: self.worker.stop()

    def _finish(self, summary):
        self._append(summary)
        self.run_btn.setEnabled(True); self.json_btn.setEnabled(True); self.stop_btn.setEnabled(False)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(2000)
        logging.getLogger("fwgen").removeHandler(self._bridge)
        self._bridge.close()
        super().closeEvent(event)

    # -- Preview tab (examples; no FW_) ---------------------------------------
    def _build_preview_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        h = QHBoxLayout(); h.addWidget(QLabel("Scenario:"))
        self.preview_combo = QComboBox()
        b = QPushButton("Show"); b.clicked.connect(self._do_preview)
        h.addWidget(self.preview_combo, 1); h.addWidget(b)
        v.addLayout(h)
        self.preview_view = QTextEdit(); self.preview_view.setReadOnly(True)
        self.preview_view.setStyleSheet("font-family: monospace;")
        v.addWidget(self.preview_view, 1)
        self._refresh_spec_combos()
        return w

    def _do_preview(self):
        name = self.preview_combo.currentText()
        try:
            sp = next(s for s in fg.load_specs_dir(self.specs_edit.text() or "specs") if s.name == name)
            self.preview_view.setPlainText(fg.render_preview(sp, 8))
        except Exception as e:                               # noqa: BLE001
            self.preview_view.setPlainText(f"[preview error] {e}")

    def _refresh_spec_combos(self):
        try:
            names = [s.name for s in fg.load_specs_dir(self.specs_edit.text() or "specs")]
        except Exception:                                    # noqa: BLE001
            names = []
        for combo in (getattr(self, "preview_combo", None), getattr(self, "builder_from", None)):
            if combo is None:
                continue
            cur = combo.currentText()
            combo.blockSignals(True); combo.clear(); combo.addItems(names)
            if cur in names:
                combo.setCurrentText(cur)
            combo.blockSignals(False)

    # -- Builder tab (specialist lists their own params) ----------------------
    def _build_builder_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("List YOUR parameters. Baseline = first value; goals/format/FW_ auto-derived."))
        top = QHBoxLayout(); top.addWidget(QLabel("Start from example:"))
        self.builder_from = QComboBox()
        bl = QPushButton("Load into table"); bl.clicked.connect(self._builder_load_example)
        top.addWidget(self.builder_from, 1); top.addWidget(bl)
        v.addLayout(top)
        f = QHBoxLayout()
        f.addWidget(QLabel("Name:")); self.builder_name = QLineEdit("my_scenario"); f.addWidget(self.builder_name, 1)
        f.addWidget(QLabel("Goals (comma):")); self.builder_goals = QLineEdit(); f.addWidget(self.builder_goals, 1)
        v.addLayout(f)
        self.builder_table = QTableWidget(0, 3)
        self.builder_table.setHorizontalHeaderLabels(
            ["Slot (UPPER, no FW_)", "key (optional)", "values (comma; 1st = baseline)"])
        self.builder_table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.builder_table, 1)
        b = QHBoxLayout()
        for label, fn in (("+ slot", lambda: self._builder_add_row()),
                          ("− slot", self._builder_del_row),
                          ("Preview", self._builder_preview),
                          ("Save spec", self._builder_save),
                          ("Save + Generate", self._builder_save_generate)):
            btn = QPushButton(label); btn.clicked.connect(fn); b.addWidget(btn)
        v.addLayout(b)
        self._builder_add_row("PARAM1", "", "baseline, variant_a, variant_b")
        self._refresh_spec_combos()
        return w

    def _builder_add_row(self, sheet="", key="", values=""):
        t = self.builder_table; r = t.rowCount(); t.insertRow(r)
        for col, val in ((0, sheet), (1, key), (2, values)):
            t.setItem(r, col, QTableWidgetItem(val))

    def _builder_del_row(self):
        t = self.builder_table
        if not t.rowCount():
            return
        r = t.currentRow()
        t.removeRow(r if r >= 0 else t.rowCount() - 1)

    def _builder_load_example(self):
        name = self.builder_from.currentText()
        try:
            sp = next(s for s in fg.load_specs_dir(self.specs_edit.text() or "specs") if s.name == name)
        except Exception as e:                               # noqa: BLE001
            return self._append(f"[load error] {e}")
        self.builder_table.setRowCount(0)
        for s in sp.slots:
            self._builder_add_row(s.sheet, s.key, ", ".join(s.values))
        self.builder_name.setText(f"{name}_mine")
        self.builder_goals.setText(", ".join(g.key for g in sp.goals))

    def _builder_collect(self):
        t = self.builder_table; slots = []
        for r in range(t.rowCount()):
            def cell(c, r=r):
                return (t.item(r, c).text() if t.item(r, c) else "").strip()
            sheet = cell(0)
            if not sheet:
                continue
            vals = [x.strip() for x in cell(2).split(",") if x.strip()]
            if vals:
                slots.append((sheet, cell(1) or None, vals))
        name = self.builder_name.text().strip() or "my_scenario"
        goals = [g.strip() for g in self.builder_goals.text().split(",") if g.strip()]
        data = fg.build_spec_dict(name, slots, title=name, goals=goals or None)
        fg.parse_spec(data, name)                            # validate -> raises
        return name, data

    def _builder_preview(self):
        try:
            name, data = self._builder_collect()
            import tomllib
            sp = fg.parse_spec(tomllib.loads(fg.dump_spec_toml(data)), name)
            self.preview_view.setPlainText(fg.render_preview(sp, 8))
            self.tabs.setCurrentIndex(1)
        except Exception as e:                               # noqa: BLE001
            QMessageBox.warning(self, "Builder", f"Cannot preview:\n{e}")

    def _builder_save(self):
        try:
            name, data = self._builder_collect()
        except Exception as e:                               # noqa: BLE001
            QMessageBox.warning(self, "Builder", f"Invalid spec:\n{e}")
            return None
        sdir = Path(self.specs_edit.text() or "specs"); sdir.mkdir(parents=True, exist_ok=True)
        path = sdir / f"{name}.toml"
        path.write_text(fg.dump_spec_toml(data), encoding="utf-8")
        self._append(f"saved spec → {path}")
        self._load_specs(silent=True)
        return name

    def _builder_save_generate(self):
        name = self._builder_save()
        if not name:
            return
        p = self._params(); p["selected"] = {name}
        self._append(f"\n=== RUN gen ({p['strategy']}) for '{name}' ===")
        self.tabs.setCurrentIndex(0)
        self._start("gen", p)


def _spin(val, lo, hi):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val); return s


def _wrap(layout):
    w = QWidget(); w.setLayout(layout); return w


def build_app(argv=None):
    app = QApplication.instance() or QApplication(argv or [])
    return app, FwgenWindow()


def main():
    app, win = build_app(sys.argv)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
