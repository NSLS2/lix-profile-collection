from enum import Enum
from typing import Callable, Optional

import bluesky.plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.utils import RunEngineInterrupted, install_qt_kicker
from matplotlib.backends.backend_qt5 import _create_qApp
from matplotlib.backends.qt_compat import QtCore, QtWidgets
from qmicroscope.microscope import Microscope
from qmicroscope.plugins import CrossHairPlugin

install_qt_kicker()

# Adjust this URL if the camES2 MJPG endpoint differs at this beamline.
CAM_ES2_MJPG_URL = "http://10.68.25.94/mjpg/1/video.mjpg"


class RunEngineState(str, Enum):
    idle = "idle"
    running = "running"
    paused = "paused"


class QMicroscope(QtWidgets.QWidget):
    def __init__(self, url: str = ""):
        super().__init__()
        self._url = url

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        plugins = [CrossHairPlugin]
        self.microscope = Microscope(self, viewport=False, plugins=plugins)
        self.microscope.scale = [0, 400]
        self.microscope.fps = 30
        if self._url:
            self.microscope.url = self._url
        layout.addWidget(self.microscope, 0, 0)

    def start_acquisition(self):
        try:
            self.microscope.acquire(True)
        except Exception:
            pass

    def stop_acquisition(self):
        try:
            self.microscope.acquire(False)
        except Exception:
            pass


class RunEngineControls(QtWidgets.QGroupBox):
    def __init__(self, RE, plan_factory: Optional[Callable] = None):
        super().__init__("RunEngine Controls")
        self.RE = RE
        self.plan_factory = plan_factory

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        self.label = QtWidgets.QLabel("Idle")
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.label, 0, 0, 1, 2)

        self.button_run = QtWidgets.QPushButton("Run")
        self.button_run.clicked.connect(self.run)
        layout.addWidget(self.button_run, 1, 0)

        self.button_pause = QtWidgets.QPushButton("Pause")
        self.button_pause.clicked.connect(self.pause)
        layout.addWidget(self.button_pause, 1, 1)

        self.RE.state_hook = self.handle_state_change
        self.handle_state_change(self.RE.state, None)

    def run(self):
        try:
            state = RunEngineState(self.RE.state)
            if state == RunEngineState.paused:
                self.RE.resume()
                return

            if state == RunEngineState.idle and self.plan_factory is not None:
                plan = self.plan_factory()
                if plan is not None:
                    self.RE(plan)
        except RunEngineInterrupted:
            pass
        except Exception as exc:
            print(f"RunEngine run failed: {type(exc).__name__}: {exc}")

    def pause(self):
        state = RunEngineState(self.RE.state)
        if state == RunEngineState.running:
            self.RE.request_pause()
        elif state == RunEngineState.paused:
            self.RE.stop()

    def handle_state_change(self, new, old):
        if new == "idle":
            color = "green"
            run_enabled = True
            pause_enabled = False
            run_text = "Run"
            pause_text = "Pause"
        elif new == "paused":
            color = "blue"
            run_enabled = True
            pause_enabled = True
            run_text = "Resume"
            pause_text = "Stop"
        elif new == "running":
            color = "red"
            run_enabled = False
            pause_enabled = True
            run_text = "Run"
            pause_text = "Pause"
        else:
            color = "darkGray"
            run_enabled = False
            pause_enabled = False
            run_text = "Run"
            pause_text = "Stop"

        self.label.setStyleSheet(f"QLabel {{background-color: {color}; color: white;}}")
        self.label.setText(str(new).capitalize())
        self.button_run.setEnabled(run_enabled)
        self.button_run.setText(run_text)
        self.button_pause.setEnabled(pause_enabled)
        self.button_pause.setText(pause_text)


class TomoAlignmentPanel(QtWidgets.QGroupBox):
    def __init__(self, RE):
        super().__init__("Tomo Alignment Controls")
        self.RE = RE
        self.ss = globals().get("ss", None)

        self.active_tilt_motor_name = "tx"
        self.active_translation_motor_name = "sz"

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label, 0, 0, 1, 4)

        self.btn_set_minus55 = QtWidgets.QPushButton("Set ss.ry = -55 (tx/sz)")
        self.btn_set_minus55.clicked.connect(lambda: self.set_ry_mode(-55, "tx", "sz"))
        layout.addWidget(self.btn_set_minus55, 1, 0, 1, 2)

        self.btn_set_35 = QtWidgets.QPushButton("Set ss.ry = 35 (tz/sx)")
        self.btn_set_35.clicked.connect(lambda: self.set_ry_mode(35, "tz", "sx"))
        layout.addWidget(self.btn_set_35, 1, 2, 1, 2)

        self.active_pair_label = QtWidgets.QLabel("Active pair: tilt=ss.tx, translation=ss.sz")
        layout.addWidget(self.active_pair_label, 2, 0, 1, 4)

        layout.addWidget(QtWidgets.QLabel("Tilt fine step"), 3, 0)
        self.tilt_fine = QtWidgets.QDoubleSpinBox()
        self.tilt_fine.setDecimals(4)
        self.tilt_fine.setRange(0, 100)
        self.tilt_fine.setValue(0.01)
        layout.addWidget(self.tilt_fine, 3, 1)

        layout.addWidget(QtWidgets.QLabel("Tilt coarse step"), 3, 2)
        self.tilt_coarse = QtWidgets.QDoubleSpinBox()
        self.tilt_coarse.setDecimals(4)
        self.tilt_coarse.setRange(0, 100)
        self.tilt_coarse.setValue(0.1)
        layout.addWidget(self.tilt_coarse, 3, 3)

        self.btn_tilt_minus_fine = QtWidgets.QPushButton("Tilt - (fine)")
        self.btn_tilt_minus_fine.clicked.connect(lambda: self.move_tilt(-self.tilt_fine.value()))
        layout.addWidget(self.btn_tilt_minus_fine, 4, 0)

        self.btn_tilt_plus_fine = QtWidgets.QPushButton("Tilt + (fine)")
        self.btn_tilt_plus_fine.clicked.connect(lambda: self.move_tilt(self.tilt_fine.value()))
        layout.addWidget(self.btn_tilt_plus_fine, 4, 1)

        self.btn_tilt_minus_coarse = QtWidgets.QPushButton("Tilt - (coarse)")
        self.btn_tilt_minus_coarse.clicked.connect(lambda: self.move_tilt(-self.tilt_coarse.value()))
        layout.addWidget(self.btn_tilt_minus_coarse, 4, 2)

        self.btn_tilt_plus_coarse = QtWidgets.QPushButton("Tilt + (coarse)")
        self.btn_tilt_plus_coarse.clicked.connect(lambda: self.move_tilt(self.tilt_coarse.value()))
        layout.addWidget(self.btn_tilt_plus_coarse, 4, 3)

        layout.addWidget(QtWidgets.QLabel("Translation fine step"), 5, 0)
        self.trans_fine = QtWidgets.QDoubleSpinBox()
        self.trans_fine.setDecimals(4)
        self.trans_fine.setRange(0, 100)
        self.trans_fine.setValue(0.01)
        layout.addWidget(self.trans_fine, 5, 1)

        layout.addWidget(QtWidgets.QLabel("Translation coarse step"), 5, 2)
        self.trans_coarse = QtWidgets.QDoubleSpinBox()
        self.trans_coarse.setDecimals(4)
        self.trans_coarse.setRange(0, 100)
        self.trans_coarse.setValue(0.1)
        layout.addWidget(self.trans_coarse, 5, 3)

        self.btn_trans_minus_fine = QtWidgets.QPushButton("Translation <- (fine)")
        self.btn_trans_minus_fine.clicked.connect(
            lambda: self.move_translation(-self.trans_fine.value())
        )
        layout.addWidget(self.btn_trans_minus_fine, 6, 0)

        self.btn_trans_plus_fine = QtWidgets.QPushButton("Translation -> (fine)")
        self.btn_trans_plus_fine.clicked.connect(
            lambda: self.move_translation(self.trans_fine.value())
        )
        layout.addWidget(self.btn_trans_plus_fine, 6, 1)

        self.btn_trans_minus_coarse = QtWidgets.QPushButton("Translation <- (coarse)")
        self.btn_trans_minus_coarse.clicked.connect(
            lambda: self.move_translation(-self.trans_coarse.value())
        )
        layout.addWidget(self.btn_trans_minus_coarse, 6, 2)

        self.btn_trans_plus_coarse = QtWidgets.QPushButton("Translation -> (coarse)")
        self.btn_trans_plus_coarse.clicked.connect(
            lambda: self.move_translation(self.trans_coarse.value())
        )
        layout.addWidget(self.btn_trans_plus_coarse, 6, 3)

        self.record_button = QtWidgets.QPushButton("Record")
        self.record_button.clicked.connect(self.record_clip)
        layout.addWidget(self.record_button, 7, 0, 1, 2)

        self.plan_button = QtWidgets.QPushButton("Run Tomo Workflow Plan")
        self.plan_button.clicked.connect(self.run_tomo_workflow)
        layout.addWidget(self.plan_button, 7, 2, 1, 2)

        layout.addWidget(QtWidgets.QLabel("Workflow start angle"), 8, 0)
        self.start_angle = QtWidgets.QDoubleSpinBox()
        self.start_angle.setDecimals(3)
        self.start_angle.setRange(-360, 360)
        self.start_angle.setValue(-55)
        layout.addWidget(self.start_angle, 8, 1)

        layout.addWidget(QtWidgets.QLabel("Workflow end angle"), 8, 2)
        self.end_angle = QtWidgets.QDoubleSpinBox()
        self.end_angle.setDecimals(3)
        self.end_angle.setRange(-360, 360)
        self.end_angle.setValue(125)
        layout.addWidget(self.end_angle, 8, 3)

        self._update_status()

    def _get_motor(self, name: str):
        if self.ss is None:
            return None
        return getattr(self.ss, name, None)

    def _update_status(self, message: Optional[str] = None):
        if self.ss is None:
            self.status_label.setText("`ss` device not available in namespace yet.")
            return
        if message:
            self.status_label.setText(message)
            return
        self.status_label.setText(
            f"Ready. Active pair: tilt=ss.{self.active_tilt_motor_name}, "
            f"translation=ss.{self.active_translation_motor_name}"
        )

    def _run_re_plan(self, plan):
        if self.RE.state != "idle":
            self._update_status("RunEngine not idle; cannot execute motor move.")
            return
        try:
            self.RE(plan)
        except Exception as exc:
            self._update_status(f"Move failed: {type(exc).__name__}: {exc}")

    def set_ry_mode(self, target_angle: float, tilt_name: str, translation_name: str):
        if self.ss is None:
            self._update_status()
            return
        ry = self._get_motor("ry")
        if ry is None:
            self._update_status("ss.ry is not available.")
            return

        self.active_tilt_motor_name = tilt_name
        self.active_translation_motor_name = translation_name
        self.active_pair_label.setText(
            f"Active pair: tilt=ss.{tilt_name}, translation=ss.{translation_name}"
        )

        self._run_re_plan(bps.mv(ry, target_angle))
        self._update_status(f"Moved ss.ry to {target_angle}.")

    def move_tilt(self, delta: float):
        motor = self._get_motor(self.active_tilt_motor_name)
        if motor is None:
            self._update_status(f"ss.{self.active_tilt_motor_name} is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta))
        self._update_status(f"Moved ss.{self.active_tilt_motor_name} by {delta}.")

    def move_translation(self, delta: float):
        motor = self._get_motor(self.active_translation_motor_name)
        if motor is None:
            self._update_status(f"ss.{self.active_translation_motor_name} is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta))
        self._update_status(f"Moved ss.{self.active_translation_motor_name} by {delta}.")

    def record_clip(self):
        # Placeholder: wire to QMicroscope recording plugin APIs for camES2.
        # Example intent: start recording, run desired sequence, then stop recording.
        self._update_status("Record requested (placeholder).")

    def run_tomo_workflow(self):
        if self.RE.state != "idle":
            self._update_status("RunEngine not idle; cannot run tomo workflow.")
            return
        self.RE(self.tomo_workflow_plan())

    def tomo_workflow_plan(self):
        if self.ss is None or self._get_motor("ry") is None:
            print("Tomo workflow skipped: ss.ry not available.")
            return

        ry = self._get_motor("ry")
        start = float(self.start_angle.value())
        end = float(self.end_angle.value())

        # Placeholder: trigger QMicroscope recording plugin before rotation.
        # Placeholder: optional metadata capture and run UID bookkeeping.
        yield from bps.mv(ry, start)
        yield from bps.mv(ry, end)
        # Placeholder: stop QMicroscope recording and persist clip.
        # Placeholder: submit processing request to Orion cluster.


class TomoGUIMainWindow(QtWidgets.QMainWindow):
    def __init__(self, RE):
        super().__init__()
        self.setWindowTitle("Tomo Data Acquisition")

        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        layout = QtWidgets.QGridLayout()
        main_widget.setLayout(layout)

        self.qmicroscope = QMicroscope(url=CAM_ES2_MJPG_URL)
        layout.addWidget(self.qmicroscope, 0, 0, 2, 1)

        self.tomo_alignment_panel = TomoAlignmentPanel(RE)
        layout.addWidget(self.tomo_alignment_panel, 0, 1)

        self.run_engine_controls = RunEngineControls(
            RE,
            plan_factory=self.tomo_alignment_panel.tomo_workflow_plan,
        )
        layout.addWidget(self.run_engine_controls, 1, 1)

    def show(self):
        super().show()
        self.qmicroscope.start_acquisition()

    def closeEvent(self, event):
        self.qmicroscope.stop_acquisition()
        event.accept()


class TOMOGUI:
    def __init__(self):
        existing_re = globals().get("RE", None)
        self.RE = existing_re if existing_re is not None else RunEngine({})
        self.window = TomoGUIMainWindow(self.RE)

    def show(self):
        self.window.show()

    def close(self):
        self.window.close()


_create_qApp()

try:
    tomo_gui.close()
except NameError:
    pass

tomo_gui = TOMOGUI()
