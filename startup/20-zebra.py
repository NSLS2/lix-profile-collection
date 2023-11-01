print(f"Loading {__file__}...")

"""
adapted from SRX

CurrentPreamp?? removed

"""

import os
import threading
import datetime
import numpy as np
import time as ttime
from ophyd import Device, EpicsSignal, EpicsSignalRO
from ophyd import Component as Cpt
from ophyd import FormattedComponent as FC
from ophyd.areadetector.filestore_mixins import FileStorePluginBase, FileStoreHDF5

# this EpicsSignalWithRBV use ":RBV" in readback PV names
from nslsii.detectors.zebra import EpicsSignalWithRBV, Zebra as Zebra_base, ZebraAddresses as ZA

class ZebraPositionCaptureData(Device):
    """
    Data arrays for the Zebra position capture function and their metadata.
    """

    # Data arrays
    div1 = Cpt(EpicsSignal, "PC_DIV1")
    div2 = Cpt(EpicsSignal, "PC_DIV2")
    div3 = Cpt(EpicsSignal, "PC_DIV3")
    div4 = Cpt(EpicsSignal, "PC_DIV4")
    enc1 = Cpt(EpicsSignal, "PC_ENC1")
    enc2 = Cpt(EpicsSignal, "PC_ENC2")
    enc3 = Cpt(EpicsSignal, "PC_ENC3")
    enc4 = Cpt(EpicsSignal, "PC_ENC4")
    filt1 = Cpt(EpicsSignal, "PC_FILT1")
    filt2 = Cpt(EpicsSignal, "PC_FILT2")
    filt3 = Cpt(EpicsSignal, "PC_FILT3")
    filt4 = Cpt(EpicsSignal, "PC_FILT4")
    time = Cpt(EpicsSignal, "PC_TIME")
    # Array sizes
    num_cap = Cpt(EpicsSignal, "PC_NUM_CAP")
    num_down = Cpt(EpicsSignal, "PC_NUM_DOWN")
    # BOOLs to denote arrays with data
    cap_enc1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B0")
    cap_enc2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B1")
    cap_enc3_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B2")
    cap_enc4_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B3")
    cap_filt1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B4")
    cap_filt2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B5")
    cap_div1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B6")
    cap_div2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B7")
    cap_div3_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B8")
    cap_div4_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B9")

    def stage(self):
        super().stage()

    def unstage(self):
        super().unstage()


class ZebraPositionCapture(Device):
    """
    Signals for the position capture function of the Zebra
    """

    # Configuration settings and status PVs
    enc = Cpt(EpicsSignalWithRBV, "PC_ENC")
    egu = Cpt(EpicsSignalRO, "M1:EGU")
    dir = Cpt(EpicsSignalWithRBV, "PC_DIR")
    tspre = Cpt(EpicsSignalWithRBV, "PC_TSPRE")
    trig_source = Cpt(EpicsSignalWithRBV, "PC_ARM_SEL")
    arm = Cpt(EpicsSignal, "PC_ARM")
    disarm = Cpt(EpicsSignal, "PC_DISARM")
    armed = Cpt(EpicsSignalRO, "PC_ARM_OUT")
    gate_source = Cpt(EpicsSignalWithRBV, "PC_GATE_SEL")
    gate_start = Cpt(EpicsSignalWithRBV, "PC_GATE_START")
    gate_width = Cpt(EpicsSignalWithRBV, "PC_GATE_WID")
    gate_step = Cpt(EpicsSignalWithRBV, "PC_GATE_STEP")
    gate_num = Cpt(EpicsSignalWithRBV, "PC_GATE_NGATE")
    gated = Cpt(EpicsSignalRO, "PC_GATE_OUT")
    pulse_source = Cpt(EpicsSignalWithRBV, "PC_PULSE_SEL")
    pulse_start = Cpt(EpicsSignalWithRBV, "PC_PULSE_START")
    pulse_width = Cpt(EpicsSignalWithRBV, "PC_PULSE_WID")
    pulse_step = Cpt(EpicsSignalWithRBV, "PC_PULSE_STEP")
    pulse_max = Cpt(EpicsSignalWithRBV, "PC_PULSE_MAX")
    pulse = Cpt(EpicsSignalRO, "PC_PULSE_OUT")
    
    # the PVs for these 4 are manually added to the Zebra IOC at LiX
    enc_mot1_prefix = Cpt(EpicsSignal, "M1:PREFIX")
    enc_mot2_prefix = Cpt(EpicsSignal, "M2:PREFIX")
    enc_mot3_prefix = Cpt(EpicsSignal, "M3:PREFIX")
    enc_mot4_prefix = Cpt(EpicsSignal, "M4:PREFIX")
    
    enc_pos1_sync = Cpt(EpicsSignal, "M1:SETPOS.PROC")
    enc_pos2_sync = Cpt(EpicsSignal, "M2:SETPOS.PROC")
    enc_pos3_sync = Cpt(EpicsSignal, "M3:SETPOS.PROC")
    enc_pos4_sync = Cpt(EpicsSignal, "M4:SETPOS.PROC")
    enc_res1 = Cpt(EpicsSignal, "M1:MRES")
    enc_res2 = Cpt(EpicsSignal, "M2:MRES")
    enc_res3 = Cpt(EpicsSignal, "M3:MRES")
    enc_res4 = Cpt(EpicsSignal, "M4:MRES")
    enc_off1 = Cpt(EpicsSignal, "M1:OFF")
    enc_off2 = Cpt(EpicsSignal, "M2:OFF")
    enc_off3 = Cpt(EpicsSignal, "M3:OFF")
    enc_off4 = Cpt(EpicsSignal, "M4:OFF")
    data_in_progress = Cpt(EpicsSignalRO, "ARRAY_ACQ")
    block_state_reset = Cpt(EpicsSignal, "SYS_RESET.PROC")
    data = Cpt(ZebraPositionCaptureData, "")

    def stage(self):
        self.arm.put(1)

        super().stage()

    def unstage(self):
        self.disarm.put(1)
        self.block_state_reset.put(1)

        super().unstage()

class ZebraOR(Device):
    use1 = Cpt(EpicsSignal, '_ENA:B0')
    use2 = Cpt(EpicsSignal, '_ENA:B1')
    use3 = Cpt(EpicsSignal, '_ENA:B2')
    use4 = Cpt(EpicsSignal, '_ENA:B3')
    input_source1 = Cpt(EpicsSignal, '_INP1')
    input_source2 = Cpt(EpicsSignal, '_INP2')
    input_source3 = Cpt(EpicsSignal, '_INP3')
    input_source4 = Cpt(EpicsSignal, '_INP4')
    invert1 = Cpt(EpicsSignal, '_INV:B0')
    invert2 = Cpt(EpicsSignal, '_INV:B1')
    invert3 = Cpt(EpicsSignal, '_INV:B2')
    invert4 = Cpt(EpicsSignal, '_INV:B3')

    def stage(self):
        super().stage()

    def unstage(self):
        super().unstage()


class ZebraAND(Device):
    # I really appreciate the different indexing for input source
    # Thank you for that
    use1 = Cpt(EpicsSignal, '_ENA:B0')
    use2 = Cpt(EpicsSignal, '_ENA:B1')
    use3 = Cpt(EpicsSignal, '_ENA:B2')
    use4 = Cpt(EpicsSignal, '_ENA:B3')
    input_source1 = Cpt(EpicsSignal, '_INP1')
    input_source2 = Cpt(EpicsSignal, '_INP2')
    input_source3 = Cpt(EpicsSignal, '_INP3')
    input_source4 = Cpt(EpicsSignal, '_INP4')
    invert1 = Cpt(EpicsSignal, '_INV:B0')
    invert2 = Cpt(EpicsSignal, '_INV:B1')
    invert3 = Cpt(EpicsSignal, '_INV:B2')
    invert4 = Cpt(EpicsSignal, '_INV:B3')

    def stage(self):
        super().stage()

    def unstage(self):
        super().unstage()



class ZebraPulse(Device):
    width = Cpt(EpicsSignalWithRBV, 'WID')
    input_addr = Cpt(EpicsSignalWithRBV, 'INP')
    input_str = Cpt(EpicsSignalRO, 'INP:STR', string=True)
    input_status = Cpt(EpicsSignalRO, 'INP:STA')
    delay = Cpt(EpicsSignalWithRBV, 'DLY')
    delay_sync = Cpt(EpicsSignal, 'DLY:SYNC')
    time_units = Cpt(EpicsSignalWithRBV, 'PRE', string=True)
    output = Cpt(EpicsSignal, 'OUT')

    input_edge = FC(EpicsSignal,
                    '{self._zebra_prefix}POLARITY:{self._edge_addr}')

    _edge_addrs = {1: 'BC',
                   2: 'BD',
                   3: 'BE',
                   4: 'BF',
                   }

    def stage(self):
        super().stage()

    def unstage(self):
        super().unstage()

    def __init__(self, prefix, *, index=None, parent=None,
                 configuration_attrs=None, read_attrs=None, **kwargs):
        if read_attrs is None:
            read_attrs = ['input_addr', 'input_edge', 'delay', 'width', 'time_units']
        if configuration_attrs is None:
            configuration_attrs = []

        zebra = parent
        self.index = index
        self._zebra_prefix = zebra.prefix
        self._edge_addr = self._edge_addrs[index]

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, parent=parent, **kwargs)



class Zebra(Zebra_base):

    pc = Cpt(ZebraPositionCapture, "")
    or1 = Cpt(ZebraOR, "OR1")  # XF:05IDD-ES:1{Dev:Zebra2}:OR1_INV:B0
    or2 = Cpt(ZebraOR, "OR2")
    or3 = Cpt(ZebraOR, "OR3")
    or4 = Cpt(ZebraOR, "OR4")
    and1 = Cpt(ZebraAND, "AND1")  # XF:05IDD-ES:1{Dev:Zebra2}:AND1_ENA:B0
    and2 = Cpt(ZebraAND, "AND2")
    and3 = Cpt(ZebraAND, "AND3")
    and4 = Cpt(ZebraAND, "AND4")
    pulse1 = Cpt(ZebraPulse, "PULSE1_", index=1)  #  XF:16IDC-ES{Zeb:1}:PULSE1_DLY
    pulse2 = Cpt(ZebraPulse, "PULSE2_", index=2)
    pulse3 = Cpt(ZebraPulse, "PULSE3_", index=3)
    pulse4 = Cpt(ZebraPulse, "PULSE4_", index=4)

    def stage(self):
        super().stage()

    def unstage(self):
        super().unstage()

    def __init__(
        self, prefix, *,
        read_attrs=None, configuration_attrs=None, **kwargs
    ):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = []

        super().__init__(
            prefix,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            **kwargs,
        )

zebra = Zebra("XF:16IDC-ES{Zeb:1}:", name="Zebra", read_attrs=["pc.data.enc1", "pc.data.enc2", "pc.data.time"])

# Pilatus triggering
zebra.pulse1.input_addr.put(ZA.IN3_OC)
zebra.pulse1.width.put(1)
zebra.pulse1.delay.put(0)
zebra.pulse1.time_units.put('ms')
zebra.or1.input_source1.put(ZA.PULSE1)
zebra.or1.input_source2.put(ZA.SOFT_IN1)
zebra.or1.use1.put(1)
zebra.or1.use2.put(1)
zebra.output1.ttl.addr.put(ZA.OR1)