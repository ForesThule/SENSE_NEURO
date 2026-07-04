from neurosdk.amp_sensor import AmpSensor
from neurosdk.brainbit_sensor import BrainBitSensor
from neurosdk.fpg_sensor import FpgSensor
from neurosdk.mems_sensor import MemsSensor
from neurosdk.neuro_smart_sensor import NeuroSmartSensor


class BrainBitBlackSensor(BrainBitSensor, MemsSensor, AmpSensor, FpgSensor, NeuroSmartSensor):
    def __init__(self, ptr):
        super().__init__(ptr)

    def __del__(self):
        super().__del__()
