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
#CAM_ES2_MJPG_URL = "http://xf16id1-cam-ioc1-1613:8741/C2.MJPG.mjpg"
#CAM_ES2_MJPG_URL = "http://xf16idc-webcam-outboard.nsls2.bnl.local/mjpg/1/video.mjpg"
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
    ry0 = {"camES1": 0,
           "camES2": 35}

    def __init__(self, RE):
        super().__init__("Tomo Alignment Controls")
        self.RE = RE
        self.ss = globals().get("ss", None)
        self.cam = "camES2"
        self.ssx_range = [0, 0]
        # 0: ready to mount
        # 1: ready to align using camES2 
        # 2: ready to align using camES1 
        self.sample_state = 0   

        self.active_tilt_motor_name = "tx"
        self.active_translation_motor_name = "sz"

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        # Row 0: robot
        layout.addWidget(QtWidgets.QLabel("sample #:"), 0, 0)

        self.sample_list = QtWidgets.QSpinBox()
        self.sample_list.setRange(1, 9)
        self.sample_list.setValue(1)
        layout.addWidget(self.sample_list, 0, 1)
        
        #self.robot_status = QtWidgets.QLabel("ready")
        #self.robot_status.setStyleSheet("background-color: green;")
        #layout.addWidget(self.robot_status, 0, 2)

        self.btn_auto_center = QtWidgets.QPushButton(f"center sample")
        self.btn_auto_center.clicked.connect(self.auto_center)
        layout.addWidget(self.btn_auto_center, 0, 2)


        self.btn_sample_action = QtWidgets.QPushButton(f"move_sample()")
        self.btn_sample_action.clicked.connect(self.exec_sample_action)
        layout.addWidget(self.btn_sample_action, 0, 3)

        # Row 1: ry preset buttons
        self.cam_sel = QtWidgets.QComboBox()
        self.cam_sel.addItems(["camES2", "camES1"])
        self.cam_sel.currentTextChanged.connect(self.set_cam)
        layout.addWidget(self.cam_sel, 1, 0)
   
        ry1 = self.ry0[self.cam]-90
        self.btn_set_ry_min = QtWidgets.QPushButton(f"move ss.ry to {ry1:d}")
        self.btn_set_ry_min.clicked.connect(lambda: self.set_ry_mode(-90, "tx", "sz"))
        layout.addWidget(self.btn_set_ry_min, 1, 1)

        ry1 = self.ry0[self.cam]
        self.btn_set_ry_mid = QtWidgets.QPushButton(f"move ss.ry to {ry1:d}")
        self.btn_set_ry_mid.clicked.connect(lambda: self.set_ry_mode(0, "tz", "sx"))
        layout.addWidget(self.btn_set_ry_mid, 1, 2)

        ry1 = self.ry0[self.cam]+90
        self.btn_set_ry_max = QtWidgets.QPushButton(f"move ss.ry to {ry1:d}")
        self.btn_set_ry_max.clicked.connect(lambda: self.set_ry_mode(90, "tx", "sz", reverse_dir=True))
        layout.addWidget(self.btn_set_ry_max, 1, 3)

        # Row 2: active motor pair label
        self.active_pair_label = QtWidgets.QLabel("Active pair: tilt=ss.tx, translation=ss.sz")
        layout.addWidget(self.active_pair_label, 2, 0, 1, 2)

        self.btn_move_ssy_up = QtWidgets.QPushButton("ss.y up")
        self.btn_move_ssy_up.clicked.connect(lambda: self.move_ssy(1))
        layout.addWidget(self.btn_move_ssy_up, 2, 3)

        self.btn_move_ssy_dn = QtWidgets.QPushButton("ss.y down")
        self.btn_move_ssy_dn.clicked.connect(lambda: self.move_ssy(-1))
        layout.addWidget(self.btn_move_ssy_dn, 2, 2)

        # Row 3: tilt step spinboxes
        layout.addWidget(QtWidgets.QLabel("Tilt fine step"), 3, 0)
        self.tilt_fine = QtWidgets.QDoubleSpinBox()
        self.tilt_fine.setDecimals(1)
        self.tilt_fine.setRange(0, 100)
        self.tilt_fine.setValue(0.1)
        self.tilt_fine.setEnabled(False)
        layout.addWidget(self.tilt_fine, 3, 1)

        layout.addWidget(QtWidgets.QLabel("Tilt coarse step"), 3, 2)
        self.tilt_coarse = QtWidgets.QDoubleSpinBox()
        self.tilt_coarse.setDecimals(1)
        self.tilt_coarse.setRange(0, 100)
        self.tilt_coarse.setValue(1.0)
        self.tilt_coarse.setEnabled(False)
        layout.addWidget(self.tilt_coarse, 3, 3)

        # Row 4: tilt buttons
        self.btn_tilt_minus_coarse = QtWidgets.QPushButton("Tilt - (coarse)")
        self.btn_tilt_minus_coarse.clicked.connect(lambda: self.move_tilt(-self.tilt_coarse.value()))
        layout.addWidget(self.btn_tilt_minus_coarse, 4, 0)

        self.btn_tilt_minus_fine = QtWidgets.QPushButton("Tilt - (fine)")
        self.btn_tilt_minus_fine.clicked.connect(lambda: self.move_tilt(-self.tilt_fine.value()))
        layout.addWidget(self.btn_tilt_minus_fine, 4, 1)

        self.btn_tilt_plus_fine = QtWidgets.QPushButton("Tilt + (fine)")
        self.btn_tilt_plus_fine.clicked.connect(lambda: self.move_tilt(self.tilt_fine.value()))
        layout.addWidget(self.btn_tilt_plus_fine, 4, 2)

        self.btn_tilt_plus_coarse = QtWidgets.QPushButton("Tilt + (coarse)")
        self.btn_tilt_plus_coarse.clicked.connect(lambda: self.move_tilt(self.tilt_coarse.value()))
        layout.addWidget(self.btn_tilt_plus_coarse, 4, 3)

        # Row 5: translation step spinboxes
        layout.addWidget(QtWidgets.QLabel("Translation fine step"), 5, 0)
        self.trans_fine = QtWidgets.QDoubleSpinBox()
        self.trans_fine.setDecimals(2)
        self.trans_fine.setRange(0, 100)
        self.trans_fine.setValue(0.005)
        self.trans_fine.setEnabled(False)
        layout.addWidget(self.trans_fine, 5, 1)

        layout.addWidget(QtWidgets.QLabel("Translation coarse step"), 5, 2)
        self.trans_coarse = QtWidgets.QDoubleSpinBox()
        self.trans_coarse.setDecimals(2)
        self.trans_coarse.setRange(0, 100)
        self.trans_coarse.setValue(0.05)
        self.trans_coarse.setEnabled(False)
        layout.addWidget(self.trans_coarse, 5, 3)

        # Row 6: translation buttons
        self.btn_trans_minus_coarse = QtWidgets.QPushButton("Translation <- (coarse)")
        self.btn_trans_minus_coarse.clicked.connect(
            lambda: self.move_translation(self.trans_coarse.value())
        )
        layout.addWidget(self.btn_trans_minus_coarse, 6, 0)

        self.btn_trans_minus_fine = QtWidgets.QPushButton("Translation <- (fine)")
        self.btn_trans_minus_fine.clicked.connect(
            lambda: self.move_translation(self.trans_fine.value())
        )
        layout.addWidget(self.btn_trans_minus_fine, 6, 1)

        self.btn_trans_plus_fine = QtWidgets.QPushButton("Translation -> (fine)")
        self.btn_trans_plus_fine.clicked.connect(
            lambda: self.move_translation(-self.trans_fine.value())
        )
        layout.addWidget(self.btn_trans_plus_fine, 6, 2)

        self.btn_trans_plus_coarse = QtWidgets.QPushButton("Translation -> (coarse)")
        self.btn_trans_plus_coarse.clicked.connect(
            lambda: self.move_translation(-self.trans_coarse.value())
        )
        layout.addWidget(self.btn_trans_plus_coarse, 6, 3)

        # Row 7: record + run tomo workflow
        #self.record_button = QtWidgets.QPushButton("Record")
        #self.record_button.clicked.connect(self.record_clip)
        #layout.addWidget(self.record_button, 7, 0, 1, 2)

        #self.plan_button = QtWidgets.QPushButton("Run Tomo Workflow Plan")
        #self.plan_button.clicked.connect(self.run_tomo_workflow)
        #layout.addWidget(self.plan_button, 7, 2, 1, 2)

        # Row 8: tweak ss.x
        self.btn_ssx_minus_coarse = QtWidgets.QPushButton("ss.x <- (coarse)")
        self.btn_ssx_minus_coarse.clicked.connect(lambda: self.move_ssx(0.5))
        layout.addWidget(self.btn_ssx_minus_coarse, 8, 0)

        self.btn_ssx_minus_fine = QtWidgets.QPushButton("ss.x <- (fine)")
        self.btn_ssx_minus_fine.clicked.connect(lambda: self.move_ssx(0.02))
        layout.addWidget(self.btn_ssx_minus_fine, 8, 1)

        self.btn_ssx_plus_fine = QtWidgets.QPushButton("ss.x -> (fine)")
        self.btn_ssx_plus_fine.clicked.connect(lambda: self.move_ssx(-0.02))
        layout.addWidget(self.btn_ssx_plus_fine, 8, 2)

        self.btn_ssx_plus_coarse = QtWidgets.QPushButton("ss.x -> (coarse)")
        self.btn_ssx_plus_coarse.clicked.connect(lambda: self.move_ssx(-0.5))
        layout.addWidget(self.btn_ssx_plus_coarse, 8, 3)

        # Row 9: scan params 
        self.btn_ssx_range_minus = QtWidgets.QPushButton("set ss.x range [-]")
        self.btn_ssx_range_minus.clicked.connect(lambda: self.set_ssx_range(0))
        layout.addWidget(self.btn_ssx_range_minus, 9, 0)

        self.btn_ssx_range_plus = QtWidgets.QPushButton("set ss.x range [+]")
        self.btn_ssx_range_plus.clicked.connect(lambda: self.set_ssx_range(1))
        layout.addWidget(self.btn_ssx_range_plus, 9, 1)

        self.btn_scan_params = QtWidgets.QPushButton("print scan params")
        self.btn_scan_params.clicked.connect(self.print_scan_params)
        layout.addWidget(self.btn_scan_params, 9, 3)

        # Row 10: status label
        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label, 10, 0, 1, 4)
        
        self.set_cam(self.cam_sel.currentText())
        self.sample_state = 1
        self._update_status()
        
        self.exec_sample_action()


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

    def set_cam(self, cam):
        self.cam = cam
        ry0 = self.ry0[self.cam]
        self.btn_set_ry_min.setText(f"move ss.ry to {ry0-90:d}")
        self.btn_set_ry_mid.setText(f"move ss.ry to {ry0:d}")
        self.btn_set_ry_max.setText(f"move ss.ry to {ry0+90:d}")

        state = (cam=='camES1')
        self.btn_ssx_plus_fine.setEnabled(state)
        self.btn_ssx_plus_coarse.setEnabled(state)
        self.btn_ssx_minus_coarse.setEnabled(state)
        self.btn_ssx_minus_fine.setEnabled(state)
        self.btn_ssx_range_plus.setEnabled(state)
        self.btn_ssx_range_minus.setEnabled(state)

        self.btn_trans_plus_coarse.setEnabled(not state)
        #self.btn_trans_plus_fine.setEnabled(not state)
        #self.btn_trans_minus_fine.setEnabled(not state)
        self.btn_trans_minus_coarse.setEnabled(not state)
        self.btn_tilt_plus_coarse.setEnabled(not state)
        #self.btn_tilt_plus_fine.setEnabled(not state)
        #self.btn_tilt_minus_fine.setEnabled(not state)
        self.btn_tilt_minus_coarse.setEnabled(not state)
        
    def auto_center(self):
        """ this should run after the sample orientation is adjusted 
            align_sample() defined in def-tomo.py
            ROI = [top, bottom, left, right] (top coordinate is 0)
        """
        align_sample(roi=[200, -200, 100, -100], keep_orientation=True)

    def exec_sample_action(self):
        # this version does not use the robot
        snum = self.sample_list.value()
        if self.sample_state==1:
            # park
            move_sample('park', use_robot=False)
            self.btn_sample_action.setText("move_sample()")
            self.cam_sel.setCurrentIndex(self.cam_sel.findText("camES2"))
            self.set_cam('camES2')
            ss.ry.move(-55).wait()
            self.set_ry_mode(-90, "tx", "sz")
            self.ssx_range = [0., 0.]
            self.btn_auto_center.setEnabled(True)
            self.sample_state = 0
        elif self.sample_state==0:
            # measure
            self.btn_auto_center.setEnabled(False)
            self.btn_sample_action.setText("move_sample('park')")
            self.sample_state = 1
            move_sample(use_XSP3=True, use_robot=False)
            self.cam_sel.setCurrentIndex(self.cam_sel.findText("camES1"))

    def set_ry_mode(self, target_angle: float, 
                    tilt_name: str, translation_name: str, reverse_dir:bool=False):
        if self.ss is None:
            self._update_status()
            return
        ry = self._get_motor("ry")
        if ry is None:
            self._update_status("ss.ry is not available.")
            return

        self.active_tilt_motor_name = tilt_name
        self.active_translation_motor_name = translation_name
        self.active_motion_dir = (-1 if reverse_dir else 1)
        self.active_pair_label.setText(
            f"Active pair: tilt=ss.{tilt_name}, translation=ss.{translation_name}"
        )

        ry0 = self.ry0[self.cam]
        self._run_re_plan(bps.mv(ry, target_angle+ry0))
        self._update_status(f"Moved ss.ry to {target_angle+ry0}.")

    def move_tilt(self, delta: float):
        motor = self._get_motor(self.active_tilt_motor_name)
        if motor is None:
            self._update_status(f"ss.{self.active_tilt_motor_name} is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta*self.active_motion_dir))
        self._update_status(f"Moved ss.{self.active_tilt_motor_name} by {delta}.")

    def move_translation(self, delta: float):
        motor = self._get_motor(self.active_translation_motor_name)
        if motor is None:
            self._update_status(f"ss.{self.active_translation_motor_name} is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta*self.active_motion_dir))
        self._update_status(f"Moved ss.{self.active_translation_motor_name} by {delta}.")

    def move_ssx(self, delta: float):
        motor = self._get_motor("x")
        if motor is None:
            self._update_status(f"ss.x is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta))
        self._update_status(f"Moved ss.x by {delta}.")

    def move_ssy(self, delta:float):
        motor = self._get_motor("y")
        if motor is None:
            self._update_status(f"ss.y is not available.")
            return
        self._run_re_plan(bps.mvr(motor, delta))
        self._update_status(f"Moved ss.y by {delta}.")
        
    def set_ssx_range(self, idx: int):
        motor = self._get_motor("x")
        self.ssx_range[idx] = motor.position

    def print_scan_params(self):
        print(f"current motor positions: ss.x={ss.x.position:.2f}, ss.y={ss.x.position:.2f}, ss.ry={ss.ry.position:.1f}")

        print("spos = ", self.sample_list.value())
        print(f"x1 = {self.ssx_range[0]:.2f}")
        print(f"x2 = {self.ssx_range[1]:.2f}")
        motor = self._get_motor("y")
        print(f"ylist = [{motor.position:.1f}]")
        
        print("mount_sample(spos, ", end="")
        for mot_name in ['sx', 'sz', 'tx', 'tz']:
            motor = self._get_motor(mot_name)
            print(f"pos_{mot_name} = {motor.position:.2f}, ", end="")
        print("use_XSP3=True)")

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
        #start = float(self.start_angle.value())
        #end = float(self.end_angle.value())

        # Placeholder: trigger QMicroscope recording plugin before rotation.
        # Placeholder: optional metadata capture and run UID bookkeeping.
        #yield from bps.mv(ry, start)
        #yield from bps.mv(ry, end)
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

        """
        self.run_engine_controls = RunEngineControls(
            RE,
            plan_factory=self.tomo_alignment_panel.tomo_workflow_plan,
        )
        layout.addWidget(self.run_engine_controls, 1, 1)
        """

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

rbt.park()
tomo_gui = TOMOGUI()

def get_sample_outline():
    
    camES2.ext_trig = False
    
    _md = {"experiment": "alignment",
           "scan_type": "sam3_tomo"}
    _md.update(md or {})

    RE(ascan([camES2], ss.ry, -55, 125, 181), md=_md)

