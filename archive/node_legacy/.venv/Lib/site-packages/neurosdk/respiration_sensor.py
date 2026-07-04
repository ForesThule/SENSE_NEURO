from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.sensor import _neuro_lib
import contextlib
from abc import abstractmethod, ABC
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor


class RespirationSensor(Sensor, ABC):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readSamplingFrequencyRespSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readSamplingFrequencyRespSensor.restype = c_uint8
        if self.is_supported_feature(SensorFeature.Respiration):
            self.respirationDataReceived = None
            self.set_respiration_callbacks()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.respirationDataReceived = None
                self.unset_respiration_callbacks()
        super().__del__()

    @abstractmethod
    def set_respiration_callbacks(self):
        pass

    @abstractmethod
    def unset_respiration_callbacks(self):
        pass

    @property
    def sampling_frequency_resp(self) -> SensorSamplingFrequency:
        status = OpStatus()
        sampling_frequency_out = EnumType(c_int8(1))
        _neuro_lib.readSamplingFrequencyRespSensor(self.sensor_ptr, sampling_frequency_out, byref(status))
        raise_exception_if(status)
        return SensorSamplingFrequency(sampling_frequency_out.contents.value)
