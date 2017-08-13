#!/usr/bin/env python

import argparse
import nexstar
import numpy as np
import time

parser = argparse.ArgumentParser()
parser.add_argument('--scope', help='serial device for connection to telescope', default='/dev/ttyUSB0')
args = parser.parse_args()

NUM_TRIALS_PER_COMMAND = 100

mount = nexstar.NexStar(args.scope)

print('Testing get_position command latency...')
measurements = []
for i in range(NUM_TRIALS_PER_COMMAND):
    time_start = time.time()
    mount.get_azalt()
    measurements.append((time.time() - time_start) * 1000)
    print('\t' + str(i) + ': ' + str(measurements[-1]) + ' ms')
print('Mean: ' + str(np.mean(measurements)) + ' ms')
print('Standard deviation: ' + str(np.std(measurements)) + ' ms')

print('Testing slew command latency...')
measurements = []
for i in range(NUM_TRIALS_PER_COMMAND):
    time_start = time.time()
    mount.slew_var('az', 0.0)
    measurements.append((time.time() - time_start) * 1000)
    print('\t' + str(i) + ': ' + str(measurements[-1]) + ' ms')
print('Mean: ' + str(np.mean(measurements)) + ' ms')
print('Standard deviation: ' + str(np.std(measurements)) + ' ms')
