import ctypes
from ctypes import py_object, c_void_p

from _ctypes import byref, POINTER
from neurosdk.__utils import raise_exception_if

from neurosdk.__cmn_types import OpStatus, SignalDataCallbackBrainBit2, BrainBit2SignalDataListenerHandle, \
    ResistDataCallbackBrainBit2, BrainBit2ResistDataListenerHandle, SensorPointer, NativeBrainBit2AmplifierParam, \
    NativeEEGChannelInfo, SizeType, BRAINBIT2_MAX_CH_COUNT
from neurosdk.cmn_types import SignalChannelsData, ResistRefChannelsData, BrainBit2AmplifierParam, BrainBit2ChannelMode, \
    SensorGain, GenCurrent, EEGChannelInfo, EEGChannelId, EEGChannelType

from neurosdk.neuro_smart_sensor import NeuroSmartSensor
from neurosdk.fpg_sensor import FpgSensor
from neurosdk.amp_sensor import AmpSensor
from neurosdk.mems_sensor import MemsSensor
from neurosdk.resist_sensor import ResistSensor
from neurosdk.signal_sensor import SignalSensor
from neurosdk.sensor import _neuro_lib


class BrainBit2Sensor(SignalSensor, ResistSensor, MemsSensor, AmpSensor, FpgSensor, NeuroSmartSensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.addResistCallbackBrainBit2.argtypes = [SensorPointer, ResistDataCallbackBrainBit2, c_void_p,
                                                          ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addResistCallbackBrainBit2.restype = ctypes.c_uint8
        _neuro_lib.removeResistCallbackBrainBit2.argtypes = [BrainBit2ResistDataListenerHandle]
        _neuro_lib.removeResistCallbackBrainBit2.restype = c_void_p
        _neuro_lib.addSignalCallbackBrainBit2.argtypes = [SensorPointer, SignalDataCallbackBrainBit2, c_void_p,
                                                          ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addSignalCallbackBrainBit2.restype = ctypes.c_uint8
        _neuro_lib.removeSignalCallbackBrainBit2.argtypes = [BrainBit2SignalDataListenerHandle]
        _neuro_lib.removeSignalCallbackBrainBit2.restype = c_void_p
        _neuro_lib.readAmplifierParamBrainBit2.argtypes = [SensorPointer, POINTER(NativeBrainBit2AmplifierParam),
                                                           POINTER(OpStatus)]
        _neuro_lib.readAmplifierParamBrainBit2.restype = ctypes.c_uint8
        _neuro_lib.writeAmplifierParamBrainBit2.argtypes = [SensorPointer, NativeBrainBit2AmplifierParam,
                                                            POINTER(OpStatus)]
        _neuro_lib.writeAmplifierParamBrainBit2.restype = ctypes.c_uint8
        _neuro_lib.readSupportedChannelsBrainBit2.argtypes = [SensorPointer, POINTER(NativeEEGChannelInfo), POINTER(
                                                              ctypes.c_int32), POINTER(OpStatus)]
        _neuro_lib.readSupportedChannelsBrainBit2.restype = ctypes.c_uint8

    def __del__(self):
        super().__del__()

    def set_signal_callbacks(self):
        self.__add_signal_data_callback_brain_bit_2()

    def unset_signal_callbacks(self):
        _neuro_lib.removeSignalCallbackBrainBit2(self.__signalDataCallbackBrainBit2Handle)

    def set_resist_callbacks(self):
        self.__add_resist_callback_brain_bit_2()

    def unset_resist_callbacks(self):
        _neuro_lib.removeResistCallbackBrainBit2(self.__resistCallbackBrainBit2Handle)

    def __add_signal_data_callback_brain_bit_2(self):
        def __py_signal_data_callback_brain_bit_2(ptr, data, sz_data, user_data):
            signal_data = [SignalChannelsData(PackNum=int(data[i].PackNum),
                                              Marker=int(data[i].Marker),
                                              Samples=[float(data[i].Samples[j]) for j in range(data[i].SzSamples)]) for
                           i in range(sz_data)]
            if user_data.signalDataReceived is not None:
                user_data.signalDataReceived(user_data, signal_data)

        status = OpStatus()
        self.__signalDataCallbackBrainBit2 = SignalDataCallbackBrainBit2(__py_signal_data_callback_brain_bit_2)
        self.__signalDataCallbackBrainBit2Handle = BrainBit2SignalDataListenerHandle()
        _neuro_lib.addSignalCallbackBrainBit2(self.sensor_ptr, self.__signalDataCallbackBrainBit2,
                                              byref(self.__signalDataCallbackBrainBit2Handle),
                                              py_object(self), byref(status))
        raise_exception_if(status)

    def __add_resist_callback_brain_bit_2(self):
        def __py_resist_callback_brain_bit_2(ptr, data, sz_data, user_data):
            resist = [ResistRefChannelsData(PackNum=int(data[i].PackNum),
                                            Samples=[float(data[i].Samples[j]) for j in range(data[i].SzSamples)],
                                            Referents=[float(data[i].Referents[j]) for j in range(data[i].SzReferents)])
                      for i in range(sz_data)]
            if user_data.resistDataReceived is not None:
                user_data.resistDataReceived(user_data, resist)

        status = OpStatus()
        self.__resistCallbackBrainBit2 = ResistDataCallbackBrainBit2(__py_resist_callback_brain_bit_2)
        self.__resistCallbackBrainBit2Handle = BrainBit2ResistDataListenerHandle()
        _neuro_lib.addResistCallbackBrainBit2(self.sensor_ptr, self.__resistCallbackBrainBit2,
                                              byref(self.__resistCallbackBrainBit2Handle),
                                              py_object(self), byref(status))
        raise_exception_if(status)

    @property
    def amplifier_param(self) -> BrainBit2AmplifierParam:
        status = OpStatus()
        cmap = POINTER(NativeBrainBit2AmplifierParam)
        amplifier_param_out = cmap(NativeBrainBit2AmplifierParam())
        _neuro_lib.readAmplifierParamBrainBit2(self.sensor_ptr, amplifier_param_out, byref(status))
        raise_exception_if(status)
        ch_count = _neuro_lib.getChannelsCountSensor(self.sensor_ptr)
        return BrainBit2AmplifierParam(
            ChSignalMode=[BrainBit2ChannelMode(amplifier_param_out.contents.ChSignalMode[i]) for i in range(ch_count)],
            ChResistUse=[bool(amplifier_param_out.contents.ChResistUse[i]) for i in range(ch_count)],
            ChGain=[SensorGain(amplifier_param_out.contents.ChGain[i]) for i in range(ch_count)],
            Current=GenCurrent(amplifier_param_out.contents.Current))

    @amplifier_param.setter
    def amplifier_param(self, params: BrainBit2AmplifierParam):
        status = OpStatus()
        ch_count = _neuro_lib.getChannelsCountSensor(self.sensor_ptr)
        amplifier_param = NativeBrainBit2AmplifierParam()
        amplifier_param.ChSignalMode = (ctypes.c_uint8 * BRAINBIT2_MAX_CH_COUNT)(
            *[params.ChSignalMode[i].value for i in range(ch_count)])
        amplifier_param.ChResistUse = (ctypes.c_uint8 * BRAINBIT2_MAX_CH_COUNT)(*[params.ChResistUse[i] for i in range(ch_count)])
        amplifier_param.ChGain = (ctypes.c_uint8 * BRAINBIT2_MAX_CH_COUNT)(*[params.ChGain[i].value for i in range(ch_count)])
        amplifier_param.Current = params.Current.value
        _neuro_lib.writeAmplifierParamBrainBit2(self.sensor_ptr, amplifier_param, byref(status))
        raise_exception_if(status)

    @property
    def supported_channels(self) -> list[EEGChannelInfo]:
        status = OpStatus()
        ch_count = _neuro_lib.getChannelsCountSensor(self.sensor_ptr)
        channel_info_out = (NativeEEGChannelInfo * ch_count)(*[NativeEEGChannelInfo() for _ in range(ch_count)])
        sz_channel_info_in_out = SizeType(ctypes.c_int32(ch_count))
        _neuro_lib.readSupportedChannelsBrainBit2(self.sensor_ptr, channel_info_out, sz_channel_info_in_out,
                                                  byref(status))
        raise_exception_if(status)
        channel_info = []
        for i in range(sz_channel_info_in_out.contents.value):
            channel_info.append(
                EEGChannelInfo(Id=EEGChannelId(channel_info_out[i].Id),
                               ChType=EEGChannelType(channel_info_out[i].ChType),
                               Name=''.join([chr(c) for c in channel_info_out[i].Name]).rstrip('\x00'),
                               Num=int(channel_info_out[i].Num)))
        return channel_info
