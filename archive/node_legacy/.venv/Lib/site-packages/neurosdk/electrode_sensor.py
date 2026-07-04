import contextlib
from abc import abstractmethod, ABC

from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor, _neuro_lib


class ElectrodeSensor(Sensor, ABC):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readElectrodeStateCallibri.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readElectrodeStateCallibri.restype = c_uint8
        self.electrodeStateChanged = None
        self.set_electrode_callbacks()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.electrodeStateChanged = None
                self.unset_electrode_callbacks()
        super().__del__()

    @property
    def electrode_state(self) -> CallibriElectrodeState:
        status = OpStatus()
        el_val = EnumType(c_int8(1))
        _neuro_lib.readElectrodeStateCallibri(self.sensor_ptr, el_val, byref(status))
        raise_exception_if(status)
        return CallibriElectrodeState(el_val.contents.value)

    @abstractmethod
    def set_electrode_callbacks(self):
        pass

    @abstractmethod
    def unset_electrode_callbacks(self):
        pass
