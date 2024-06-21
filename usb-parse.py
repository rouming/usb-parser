#!/usr/bin/python3

from dataclasses import dataclass, field
import csv
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import sys

def usb_period(is_full_speed):
    if is_full_speed:
        return 1 / 12e6
    return 1 / 1.5e6

def crc5(data):
    # x^5 + x^2 + 1
    polynomial = 0b00101
    # USB crc5 is initialized to all 1
    register = 0b11111

    for d in range(len(data)):
        byte = data[d]
        bits = range(8) if d < len(data)-1 else range(3)
        for i in bits:
            bit = (byte >> i) & 1
            xor_flag = (register >> 4) & 1
            register = (register << 1) & 0b11111
            if bit ^ xor_flag:
                register ^= polynomial

    # USB crc5 is inversed at output time
    return 0b11111 - register

@dataclass
class dpdm_sample:
    cnt:     int = 0
    dp:      int = 0
    dm:      int = 0
    next_tm: float = 0

    def __init__(self, next_tm):
        self.next_tm = next_tm

class dpdm_byte:
    nr_bits:  int = 0
    b:        int = 0

@dataclass
class dpdm_data:
    byte:      dpdm_byte = field(default_factory=dpdm_byte)
    prev_bit:  int = None
    bytes_arr: list[int] = field(default_factory=list)

if len(sys.argv) != 2:
    print("Usage: <file.csv>")
    sys.exit(1)

f_input = open(sys.argv[1])

csv_input = csv.reader(f_input, skipinitialspace=True)
header = next(csv_input)

FS_SYNC = 0x2a
LS_SYNC = 0xd5

PID_OUT   = 0xe1
PID_IN    = 0x69
PID_SOF   = 0xa5
PID_SETUP = 0x2d
PID_DATA0 = 0xc3
PID_DATA1 = 0x4b
PID_ACK   = 0xd2
PID_NAK   = 0x5a
PID_STALL = 0x1e
PID_PRE   = 0x3c

SE0 = -1
SE1 =  2

LOW  = -1
HIGH =  1

UNKNOWN      = 0
IDLE         = 1
DETECT_SYNC  = 2
RECEIVE      = 3
GOT_SE1      = 4
GOT_EOP      = 5

state = UNKNOWN
se0_cnt = 0

full_speed = None
period = None

sample = None
data = None

prev_tm = None
prev_dp = None
prev_dm = None
for v1, v2, v3 in csv_input:
    tm_v = float(v1)
    dp_v = float(v2)
    dm_v = float(v3)

    # To logical levels
    dp_v = LOW if dp_v < 1.2 else HIGH
    dm_v = LOW if dm_v < 1.2 else HIGH

    # Detect full/low speed
    if full_speed is None and dp_v != dm_v:
        full_speed = (dp_v == HIGH)

    # Detect required number of samples per USB period
    if full_speed is not None and \
       period is None and prev_tm is not None:
        period = usb_period(full_speed)
        state = IDLE

    # Detect SYNC
    if state == IDLE and (prev_dp != dp_v or prev_dm != dm_v):
        state = DETECT_SYNC
        sample = dpdm_sample(tm_v + period)
        data = dpdm_data()

    # Oversampling and decoding
    if sample is not None:
        sample.dp  += dp_v
        sample.dm  += dm_v

        if tm_v >= sample.next_tm:
            dp = 1 if sample.dp > 0 else 0
            dm = 1 if sample.dm > 0 else 0

            # Detect EOP or SE1
            if dp != dm:
                if se0_cnt >= 2:
                    # EOP: detect J which follows the 2x SE0
                    if full_speed and dp > dm:
                        state = GOT_EOP
                    elif not full_speed and dp < dm:
                        state = GOT_EOP
                se0_cnt = 0
            elif dp == 0 and dm == 0:
                se0_cnt += 1
            else:
                print("[%f] Warning: SE1 state detected" % tm_v)
                state = GOT_SE1

            # SE1 or EOP
            if state == GOT_SE1 or state == GOT_EOP:
                sample = None
                if state == GOT_SE1:
                    # Discard everything and start over
                    data = None
                    state = IDLE
            else:
                # Decode a bit
                bit = raw_bit = 1 if dp > dm else 0
                if data.prev_bit is not None:
                    # Decode NRZI
                    bit = 1 if data.prev_bit == raw_bit else 0
                    data.prev_bit = raw_bit
                data.byte.b |= (bit << data.byte.nr_bits)
                data.byte.nr_bits += 1
                if data.byte.nr_bits == 8:
                    # Last bit of SYNC for further NRZI decoding
                    if state == DETECT_SYNC:
                        data.prev_bit = raw_bit
                    data.bytes_arr.append(data.byte.b)
                    data.byte = dpdm_byte()

                next_tm = sample.next_tm + period
                sample = dpdm_sample(next_tm)

    # Detect SYNC
    if state == DETECT_SYNC:
        if len(data.bytes_arr) == 1:
            sync = data.bytes_arr[0]
            if full_speed and sync == FS_SYNC:
                data.byte = dpdm_byte()
                state = RECEIVE
            elif not full_speed and sync == LS_SYNC:
                data.byte = dpdm_byte()
                state = RECEIVE
            else:
                # Incorrect sync so start over
                state = IDLE
                sample = None
                data = None

    # We have a full packet
    if state == GOT_EOP:
        for b in data.bytes_arr:
            print("%x " % b, end='')
        if len(data.bytes_arr) > 0:
            print()

        ## XXX
        if data.bytes_arr[1] == PID_SOF:
            nr_frame = (data.bytes_arr[2] << 3) | (data.bytes_arr[3] & 7)
            bits = []
            for i in range(11):
                bits.append(nr_frame & (1 << i))
            crc = (data.bytes_arr[3] >> 3)
            print("%x, %x, %x" % (nr_frame, crc5(bits), crc))

        state = IDLE
        sample = None
        data = None

    prev_tm = tm_v
    prev_dp = dp_v
    prev_dm = dm_v
