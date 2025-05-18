import sys
import minimalmodbus
from datetime import datetime

def renology_read(modbus_device="/dev/ttyUSB0", modbus_slave_address=1):
    instrument = minimalmodbus.Instrument(modbus_device, modbus_slave_address)
    # port name, slave address (in decimal)
    instrument.serial.baudrate = 9600
    instrument.serial.bytesize = 8
    instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
    instrument.serial.stopbits = 2
    instrument.serial.timeout  = 1
    instrument.address = modbus_slave_address # this is the slave address number
    instrument.mode = minimalmodbus.MODE_RTU   # rtu or ascii mode
    instrument.clear_buffers_before_each_transaction = True

    # # Temperature
    # # The actual value has to be split, the highest bit of each is the +/- sign
    temp = instrument.read_register(0x103)
    if (temp & 0x8000) > 0 :
        # This is the positive/negative bit for the Controller Temperature
        tempControllerSign = "-"
    else :
        tempControllerSign = ""
    if (temp & 0x80) > 0 :
        # This is the positive/negative bit for the Aux Battery Temperature
        tempAuxBattSign = "-"
    else :
        tempAuxBattSign = ""
    # Strips the high byte to show Controller Temperature
    tempController = "{}{}".format(tempControllerSign,
                                   int(format(temp & 0x7F00, '016b')[:8], 2))
    # Low byte shows Aux Battery Temperature
    tempAuxBatt = "{}{}".format(tempAuxBattSign, (temp & 0x7F))

    # # Charge State
    # # If the bit is "1" then the value is True, comment is from the Renogy Docs
    chargeState = instrument.read_register(0x120)
    # 00H:no charging activated
    chargingNone = (chargeState & 0x1) > 0
    # 02H:mppt charging mode  (solar)
    chargingSolar = (chargeState & 0x4) > 0
    # 03H:Equallization charging stage  (solar/alternator)
    chargingEqualization = (chargeState & 0x8) > 0
    # 04H:Boost charging stage  (solar/alternator)
    chargingBoost = (chargeState & 0x10) > 0
    # 05H:Float charging stage  (solar/alternator)
    chargingFloat = (chargeState & 0x20) > 0
    # 06H:current-limited charging stage (solar/alternator)
    chargingLimited = (chargeState & 0x40) > 0
    # 08H:direct charging mode (alternator)
    chargingAlt = (chargeState & 0x80) > 0

    # Error Codes
	# If the bit is "1" then the string is added to the array,
    # comment is from the Renogy Docs
    errors = []
    errorCodesLow = instrument.read_register(0x121)
    if (errorCodesLow & 0x10) > 0 :
        # b4:controller inside over temperature 2
        errors.append("CtrlOverTemp2")

    if (errorCodesLow & 0x20) > 0 :
        # b5:alternator input overcurrent
        errors.append("AltInputOverCurrent")

    if (errorCodesLow & 0x100) > 0 :
        # b8：alternator input over voltage protection
        errors.append("AltInputOverVoltProtection")

    if (errorCodesLow & 0x200) > 0 :
        # b9：starter battery reverse polarity
        errors.append("StarterBatteryReversePolarity")
    if (errorCodesLow & 0x400) > 0 :
        # b10：BMS over charge protection
        errors.append("BmsOverChargeProtection")
    if (errorCodesLow & 0x800) > 0 :
        # b11：auxilliary battery stopped taking charges because of
        # low temperature (lithium battery:0°C, lead acid:-35°C)
        errors.append("AuxLowTempProtection")

    errorCodesHigh = instrument.read_register(0x122)
    if (errorCodesHigh & 0x1) > 0 :
        # B0:auxilliary battery over-discharged
        errors.append("AuxBatteryOverDischarge")
    if (errorCodesHigh & 0x2) > 0 :
        # b1:auxilliary battery over voltage
        errors.append("AuxBatteryOverVolt")
    if (errorCodesHigh & 0x4) > 0 :
        # B2:auxilliary battery under voltage warning
        errors.append("AuxBatteryUnderVolt")
    if (errorCodesHigh & 0x20) > 0 :
        # B5:controller inside temperature too high
        errors.append("ControllerOverTemp")
    if (errorCodesHigh & 0x40) > 0 :
        # B6:auxilliary battery over temperature
        errors.append("AuxBatteryOverTemp")
    if (errorCodesHigh & 0x80) > 0 :
        # B7:solar input too high
        errors.append("SolarInputTooHigh")
    if (errorCodesHigh & 0x200) > 0 :
        # B9:solar input over voltage
        errors.append("SolarInputOverVolt")
    if (errorCodesHigh & 0x1000) > 0 :
        # B12:solar, reversed poliarity
        errors.append("SolarReversePolarity")

    renology = {
        "device": instrument.read_string(0xc,8),
        # Auxilliary battery State of charge
        "auxSoc": instrument.read_register(0x100),
        "auxVoltage": instrument.read_register(0x101,1),
        # combined charging current from solar+alternator to the auxilliary
        # battery
        "maxCharge": instrument.read_register(0x102,2),
        "controllerTemp": int(tempController),
        "auxTemp": int(tempAuxBatt),
        "altVoltage": instrument.read_register(0x104,1),
        "altAmps": instrument.read_register(0x105,2),
        "altWatts": instrument.read_register(0x106),
        "solVoltage": instrument.read_register(0x107,1),
        "solAmps": instrument.read_register(0x108,2),
        "solWatts": instrument.read_register(0x109),
        # values returned need to be divided by 10 to transpose to Volts
        "lowDailyVolts": instrument.read_register(0x10b)/10,
        # values returned need to be divided by 10 to transpose to Volts
        "highDailyVolts": instrument.read_register(0x10c)/10,
        # solar+alternator
        "highDailyCurrent": instrument.read_register(0x10d),
        # solar+alternator
        "highDailyPower": instrument.read_register(0x10f),
        # solar+alternator
        "highAccumAh": instrument.read_register(0x111),
        # solar+alternator
        "dailyGeneratedPower": instrument.read_register(0x113),
        "totalWorkingDays": instrument.read_register(0x115),
        "totalOverdischargedBattery": instrument.read_register(0x116),
        "totalChargedBattery": instrument.read_register(0x117),
        "timestamp": str(datetime.now()),
        "chargingNone": str(chargingNone),
        "chargingSolar": str(chargingSolar),
        "chargingEqualization": str(chargingEqualization),
        "chargingBoost": str(chargingBoost),
        "chargingFloat": str(chargingFloat),
        "chargingLimited": str(chargingLimited),
        "chargingAlt": str(chargingAlt),
        "errors": errors
        }
    return renology
