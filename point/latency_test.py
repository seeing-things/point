#!/usr/bin/env python3

import sys
import argparse
import point
import numpy as np
import time


def latency_test(cmd_function, cmd_args, num_trials):
    measurements = []
    for i in range(num_trials):
        time_start = time.time()
        cmd_function(*cmd_args)
        measurements.append((time.time() - time_start) * 1000)
    print('Mean: ' + str(np.mean(measurements)) + ' ms')
    print('Standard deviation: ' + str(np.std(measurements)) + ' ms')

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--mount-type',
        help='select mount type (nexstar or gemini)',
        default='gemini'
    )
    parser.add_argument(
        '--mount-path',
        help='serial device node or hostname for mount command interface',
        default='/dev/ttyACM0'
    )
    args = parser.parse_args()

    NUM_TRIALS_PER_COMMAND = 1000

    if args.mount_type == 'nexstar':
        mount = nexstar.NexStar(args.mount_path)

        print('Testing get_azalt command latency...')
        latency_test(mount.get_azalt, [], NUM_TRIALS_PER_COMMAND)

        print('Testing slew_var command latency...')
        latency_test(mount.slew_var, ['az', 0.0], NUM_TRIALS_PER_COMMAND)

    elif args.mount_type == 'gemini':
        mount = point.Gemini2(args.mount_path)

        print('Testing get_ra command latency...')
        latency_test(mount.get_ra, [], NUM_TRIALS_PER_COMMAND)

        print('Testing get_dec command latency...')
        latency_test(mount.get_dec, [], NUM_TRIALS_PER_COMMAND)

        print('Testing slew_ra command latency...')
        latency_test(mount.slew_ra, [0.001], NUM_TRIALS_PER_COMMAND)

        print('Testing slew_dec command latency...')
        latency_test(mount.slew_dec, [0.001], NUM_TRIALS_PER_COMMAND)

        print('Testing ENQ command latency...')
        latency_test(mount.enq_macro, [], NUM_TRIALS_PER_COMMAND)
    else:
        print('mount-type not supported: ' + args.mount_type)
        sys.exit(1)

if __name__ == "__main__":
    main()
