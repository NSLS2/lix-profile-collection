"""Ophyd interface for the BioFluidix EPICS IOC.
"""

import threading
import time

from ophyd import Component as Cpt
from ophyd import Device, EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import DeviceStatus


class BFXChannel(Device):
    enable = Cpt(EpicsSignal, "ENABLE", string=True, kind=Kind.config)
    drops = Cpt(EpicsSignal, "DROPS", kind=Kind.config)
    stroke_velocity = Cpt(EpicsSignal, "STROKE", kind=Kind.config)
    pipe_id = Cpt(EpicsSignal, "PIPE_ID", string=True, kind=Kind.config)
    position = Cpt(EpicsSignal, "POSITION", kind=Kind.config)
    horizontal_offset = Cpt(EpicsSignal, "H_OFFSET", kind=Kind.config)
    vertical_offset = Cpt(EpicsSignal, "V_OFFSET", kind=Kind.config)


class BioFluidix(Device):
    connected = Cpt(EpicsSignalRO, "CONNECTED", string=True, kind=Kind.normal)
    busy = Cpt(EpicsSignalRO, "BUSY", string=True, kind=Kind.normal)
    simulation = Cpt(EpicsSignalRO, "SIMULATION", string=True, kind=Kind.normal)
    last_command = Cpt(EpicsSignalRO, "LAST_COMMAND", string=True, kind=Kind.normal)
    last_result = Cpt(EpicsSignalRO, "LAST_RESULT", string=True, kind=Kind.normal)
    last_error = Cpt(EpicsSignalRO, "LAST_ERROR", string=True, kind=Kind.normal)
    command_count = Cpt(EpicsSignalRO, "COMMAND_COUNT", kind=Kind.normal)

    frequency = Cpt(EpicsSignal, "FREQUENCY", kind=Kind.config)
    mode = Cpt(EpicsSignal, "MODE", string=True, kind=Kind.config)
    advance_after_fire = Cpt(
        EpicsSignal, "ADVANCE_AFTER_FIRE", string=True, kind=Kind.config
    )

    ch1 = Cpt(BFXChannel, "CH1:")
    ch2 = Cpt(BFXChannel, "CH2:")
    ch3 = Cpt(BFXChannel, "CH3:")
    ch4 = Cpt(BFXChannel, "CH4:")

    connect_command = Cpt(EpicsSignal, "CONNECT", kind=Kind.omitted)
    fire_command = Cpt(EpicsSignal, "FIRE", kind=Kind.omitted)
    disable_all_command = Cpt(EpicsSignal, "DISABLE_ALL", kind=Kind.omitted)

    def __init__(self, *args, command_timeout=30, **kwargs):
        self.command_timeout = command_timeout
        super().__init__(*args, **kwargs)

    @staticmethod
    def _enum_is(value, expected):
        return str(value).strip().casefold() == expected.casefold()

    def trigger(self):
        """Fire once and finish only when the IOC reports command completion."""
        status = DeviceStatus(self)

        try:
            if not self._enum_is(self.connected.get(), "Connected"):
                raise RuntimeError("BFX IOC is not connected")
            if not self._enum_is(self.busy.get(), "Idle"):
                raise RuntimeError("BFX IOC is busy")
            initial_count = int(self.command_count.get())
            self.fire_command.put(1, wait=True, timeout=5)
        except Exception as exc:
            status.set_exception(exc)
            return status

        def wait_for_completion():
            deadline = time.monotonic() + self.command_timeout
            try:
                while time.monotonic() < deadline:
                    count = int(self.command_count.get())
                    idle = self._enum_is(self.busy.get(), "Idle")
                    if count > initial_count and idle:
                        error = str(self.last_error.get()).strip()
                        if error:
                            raise RuntimeError(error)
                        if str(self.last_command.get()).strip().upper() != "FIRE":
                            raise RuntimeError(
                                f"Expected FIRE, IOC completed {self.last_command.get()!r}"
                            )
                        status.set_finished()
                        return

                    error = str(self.last_error.get()).strip()
                    if error.startswith("Rejected FIRE"):
                        raise RuntimeError(error)
                    time.sleep(0.05)

                raise TimeoutError(
                    f"BFX FIRE did not complete within {self.command_timeout} s"
                )
            except Exception as exc:
                status.set_exception(exc)

        threading.Thread(
            target=wait_for_completion,
            name="bfx-fire-status",
            daemon=True,
        ).start()
        return status

    def stop(self, success=False):
        """Disable physical channels when Bluesky stops or aborts a plan."""
        self.disable_all_command.put(1, wait=False)


bfx = BioFluidix("XF:16IDC-ES{BFX}:SP:", name="bfx")

print(f"Loaded {__file__}: bfx = {bfx.prefix}")
