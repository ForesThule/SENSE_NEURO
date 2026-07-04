import contextlib

from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor, _neuro_lib


class MemsSensor(Sensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readAccelerometerSensSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readAccelerometerSensSensor.restype = c_uint8
        _neuro_lib.writeAccelerometerSensSensor.argtypes = [SensorPointer, c_int8, POINTER(OpStatus)]
        _neuro_lib.writeAccelerometerSensSensor.restype = c_uint8
        _neuro_lib.readGyroscopeSensSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readGyroscopeSensSensor.restype = c_uint8
        _neuro_lib.writeGyroscopeSensSensor.argtypes = [SensorPointer, c_int8, POINTER(OpStatus)]
        _neuro_lib.writeGyroscopeSensSensor.restype = c_uint8
        _neuro_lib.readSamplingFrequencyMEMSSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readSamplingFrequencyMEMSSensor.restype = c_uint8
        _neuro_lib.addMEMSDataCallback.argtypes = [SensorPointer, MEMSDataCallback, c_void_p, ctypes.py_object,
                                                   POINTER(OpStatus)]
        _neuro_lib.addMEMSDataCallback.restype = c_uint8
        _neuro_lib.removeMEMSDataCallback.argtypes = [MEMSDataListenerHandle]
        _neuro_lib.removeMEMSDataCallback.restype = c_void_p
        if self.is_supported_feature(SensorFeature.MEMS):
            self.memsDataReceived = None
            self.__add_mems_data_callback()

        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.memsDataReceived = None
                _neuro_lib.removeMEMSDataCallback(self.__memsDataCallbackHandle)
        super().__del__()

    @property
    def sampling_frequency_mems(self) -> SensorSamplingFrequency:
        status = OpStatus()
        sampling_frequency_out = EnumType(c_int8(1))
        _neuro_lib.readSamplingFrequencyMEMSSensor(self.sensor_ptr, sampling_frequency_out, byref(status))
        raise_exception_if(status)
        return SensorSamplingFrequency(sampling_frequency_out.contents.value)

    @property
    def acc_sens(self) -> SensorAccelerometerSensitivity:
        status = OpStatus()
        acc_sens_val = EnumType(c_int8(1))
        _neuro_lib.readAccelerometerSensSensor(self.sensor_ptr, acc_sens_val, byref(status))
        raise_exception_if(status)
        return SensorAccelerometerSensitivity(acc_sens_val.contents.value)

    @property
    def gyro_sens(self) -> SensorGyroscopeSensitivity:
        status = OpStatus()
        gyro_sens_val = EnumType(c_int8(1))
        _neuro_lib.readGyroscopeSensSensor(self.sensor_ptr, gyro_sens_val, byref(status))
        raise_exception_if(status)
        return SensorGyroscopeSensitivity(gyro_sens_val.contents.value)

    def __add_mems_data_callback(self):
        def __py_mems_data_callback(ptr, data, sz_data, user_data):
            mems_data = [MEMSData(PackNum=int(data[i].PackNum),
                                  Accelerometer=Point3D(X=data[i].Accelerometer.X,
                                                        Y=data[i].Accelerometer.Y,
                                                        Z=data[i].Accelerometer.Z),
                                  Gyroscope=Point3D(X=data[i].Gyroscope.X,
                                                    Y=data[i].Gyroscope.Y,
                                                    Z=data[i].Gyroscope.Z)) for i in range(sz_data)]
            if user_data.memsDataReceived is not None:
                user_data.memsDataReceived(user_data, mems_data)

        status = OpStatus()
        self.__memsDataCallback = MEMSDataCallback(__py_mems_data_callback)
        self.__memsDataCallbackHandle = MEMSDataListenerHandle()
        _neuro_lib.addMEMSDataCallback(self.sensor_ptr, self.__memsDataCallback,
                                       byref(self.__memsDataCallbackHandle), py_object(self), byref(status))
        raise_exception_if(status)
