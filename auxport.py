import serial
import time

def _decode_msg(msg):
        
    if len(msg) < 6:
        raise ValueError('message too short')

    preamble = ord(msg[0])
    msg_len = ord(msg[1])
    source_id = ord(msg[2])
    dest_id = ord(msg[3])
    message_id = ord(msg[4])
    checksum = ord(msg[-1])

    if preamble != 0x3b:
        raise ValueError('got unexpected preamble')
    if len(msg) != msg_len + 3:
        raise ValueError('message length mismatch: ' + str(len(msg)) + ', ' + str(msg_len))

    print('source: ' + str(source_id))
    print('dest: ' + str(dest_id))
    print('message ID: ' + str(message_id))

class NexStarAux(object):
    """Interface class to facilitate tracking with NexStar telescopes.

    This class implements a subset of the NexStar AUX bus command set. The
    AUX bus sits between the hand controller and the motor controllers and
    can also be shared by other accessories.

    An excellent reference for the AUX command set can be found here:
    http://www.paquettefamily.ca/nexstar/NexStar_AUX_Commands_10.pdf

    Attributes:
        serial: A Serial class from the PySerial package.
    """

    def __init__(self, device, timeout=1):
        """Inits NexStarAux object.

        Initializes a NexStarAux object by opening a serial connection to the
        AUX bus. Asserts the RTS line which is used in a non-standard manner
        for bus arbitration.

        Args:
            device: A string with the name of the serial device connected
                to the AUX bus. For example, '/dev/ttyUSB0'.
            timeout: Timeout for reads and waiting for bus to be free
        """
        self.serial = serial.Serial(device, baudrate=19200, timeout=timeout)
        self.timeout = timeout
        self.serial.rts = False
        self.serial.reset_input_buffer()

    # stop any active slewing on destruct
    def __del__(self):
        """Destructs a NexStarAux object.
            
        Stops any active slewing before terminating the connection. This is
        important because otherwise applications that crash could leave the 
        mount slewing rapidly until it crashes into some part of the mount.
        """

        # Destructor could be called when a command was already in progress.
        # Wait for any commands to complete and flush the read buffer before
        # proceeding.
        time.sleep(0.1)
        self.serial.reset_input_buffer()
        self.slew('az', 0)
        self.slew('alt', 0)

    def _send(self, msg):
        start_time = time.time()
        while self.serial.cts:
            if time.time() - start_time > self.timeout:
                raise RuntimeError('timeout waiting for bus')

        self.serial.rts = True
        self.serial.write(msg)
        self.serial.flush()
        self.serial.rts = False

        msg_echo = self.serial.read(len(msg))
        assert msg == msg_echo, 'message echo does not match what was sent'

        msg_ack = self.serial.read(len(msg))

        return msg_ack


    def _get_next_msg(self):

        # search for preamble
        while len(self.read_buffer) > 0:
            if ord(self.read_buffer[0]) == 0x3b:
                break
            self.read_buffer = self.read_buffer[1:]

        # messages are at least 6 bytes long
        if len(self.read_buffer) < 6:
            return None
        
        # check to see if buffer contains the full message
        payload_len = ord(self.read_buffer[1])
        msg_len = payload_len + 3
        if len(self.read_buffer) < msg_len:
            return None

        msg = self.read_buffer[:msg_len]
        self.read_buffer = self.read_buffer[msg_len:]

        return msg

    def slew(self, axis, rate):
        """Set slew rate on a single axis.

        Args:
            axis: A string with value 'az' or 'alt'.
            rate: Slew rate in arcseconds per second.
        """
        
        assert axis in ['az', 'alt']

        msg = chr(0x3b)
