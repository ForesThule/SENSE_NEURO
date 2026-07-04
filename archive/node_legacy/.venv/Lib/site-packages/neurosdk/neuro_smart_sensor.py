from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.__cmn_types import OpStatus
from neurosdk.__utils import raise_exception_if
from neurosdk.sensor import Sensor, _neuro_lib


class NeuroSmartSensor(Sensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.pingNeuroSmart.argtypes = [SensorPointer, c_uint8, POINTER(OpStatus)]
        _neuro_lib.pingNeuroSmart.restype = c_uint8

    def __del__(self):
        super().__del__()

    def ping_neuro_smart(self, marker: int):
        """
        Allows the user to send a flag to the device, which will then be returned to the data packet as the value of
        the token. Not supported by all devices

        :param marker: int
            Byte marker

        :raises BaseException:
            If an internal error occurred while executing command.
        """
        status = OpStatus()
        _neuro_lib.pingNeuroSmart(self.sensor_ptr, c_uint8(marker), byref(status))
        raise_exception_if(status)
