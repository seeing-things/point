from abc import *
import serial
import socket
import struct
import string
import gemini_commands


####################################################################################################
####################################################################################################
####################################################################################################
# IMPORTANT: FOR INITIAL USE, WRAP ALL OF THIS STUFF IN A GIANT TRY BLOCK THAT JUST PRINTS THE    ##
#            EXCEPTION AND CONTINUES RUNNING, RATHER THAN TERMINATING ON POSSIBLE FALSE POSITIVES ##
####################################################################################################
####################################################################################################
####################################################################################################


class Gemini2Backend(ABC):
    class NotImplementedYetError(Exception): pass
    class NotSupportedError(Exception):      pass
    class ReadTimeoutError(Exception):       pass
    class ResponseError(Exception):          pass

    @abstractmethod
    def execute_one_command(self, cmd):
        pass

    @abstractmethod
    def execute_multiple_commands(self, *cmds):
        pass


# TODO: handle serial.SerialTimeoutException (?)

class Gemini2BackendSerial(Gemini2Backend):
    def __init__(self, timeout, devname):
        self._timeout = timeout
        self._devname = devname

        # TODO: set baud to 115.2k or whatever here
        self._serial = serial.Serial(devname, timeout=self._timeout)
        self._serial.reset_input_buffer()

    def execute_one_command(self, cmd):
        buf_cmd = cmd.encode(None)

        self._serial.write(buf_cmd.encode('ascii'))
        self._serial.reset_input_buffer()

        resp = cmd.response()
        if resp is None:
            return None

        buf_resp = ''
        while not (resp.fixed_len() is not None and len(buf_resp) >= resp.fixed_len()):
            char = self._serial.read(1).decode('ascii')
            if not char:
                raise Gemini2Backend.ReadTimeoutError()
            buf_resp += char
            if resp.fixed_len() is None:
                if char == '#':
                    break
            else:
                if char == '#':
                    raise ResponseError('received \'#\' terminator as part of a fixed-length response')

        len_consumed = resp.decode(buf_resp)
        if len_consumed != len(buf_resp):
            raise ResponseError('response was decoded, but only {} of the {} available characters were consumed'.format(len_consumed, len(buf_resp)))
        return resp

    def execute_multiple_commands(self, *cmds):
        raise Gemini2Backend.NotSupportedError('executing multiple commands at once is unsupported via the serial backend')


class Gemini2BackendUDP(Gemini2Backend):
    def __init__(self, timeout, remote_addr, local_addr='0.0.0.0', remote_port=11110, local_port=11110):
        self._timeout = timeout

        self._remote_addr = (remote_addr, remote_port)
        self._local_addr  = (local_addr,  local_port)

        self._seqnum = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self._timeout)
        self._sock.bind(self._local_addr)

    def execute_one_command(self, cmd):
        chars = cmd.encode(None)
        if len(chars) > 254:
            raise ValueError('command string is too long: {} > {}'.format(len(chars), 254))

        buf_cmd = struct.pack('!II', self._seqnum, 0)
        buf_cmd += (chars + '\x00').encode('ascii')

        self._sock.sendto(buf_cmd, self._remote_addr)

        try:
            buf_resp = self._sock.recv(4096)
        except socket.timeout:
            # TODO: handle this situation by sending NACK(s)
            raise Gemini2Backend.ReadTimeoutError()
            return None

        if len(buf_resp) > (4 + 4 + 255):
            raise ResponseError('received UDP response datagram larger than max length: {} > {}'.format(len(buf_resp), (4 + 4 + 255)))
        elif len(buf_resp) < (4 + 4 + 2):
            raise ResponseError('received UDP response datagram smaller than min length: {} < {}'.format(len(buf_resp), (4 + 4 + 2)))

        (seqnum, last_seqnum) = struct.unpack('!II', buf_resp[0:8])
        if seqnum != self._seqnum:
            raise ResponseError('mismatched sequence number in UDP response datagram: {} != {}'.format(seqnum, self._seqnum))
        if last_seqnum != 0:
            # NOTE: this may or may not actually be problematic;
            # but the docs do say that the field should be zero in normal circumstances
            raise ResponseError('received UDP response datagram with nonzero last_seqnum {} (current seqnum: {})'.format(last_seqnum, self._seqnum))
        self._seqnum += 1
        buf_resp = buf_resp[8:].decode('ascii')

        num_nulls = buf_resp.count('\x00')
        if num_nulls == 0:
            raise ResponseError('received UDP response buffer of length {} containing no NULL terminator'.format(len(buf_resp)))
        elif num_nulls > 1:
            raise ResponseError('received UDP response buffer of length {} containing {} NULL characters'.format(len(buf_resp), num_nulls))
        elif buf_resp[-1] != '\x00':
            raise ResponseError('received UDP response buffer of length {} with single NULL terminator at non-end index {}'.format(len(buf_resp), string.rfind(buf_resp, '\x00')))
        buf_resp = buf_resp[:-1]

        resp = cmd.response()
        if len(buf_resp) == 1 and buf_resp[0] == '\x06':
            if resp != None:
                raise ResponseError('received ACK (no response), but command {} expected to receive response {}'.format(cmd.__class__.__name__, resp.__class__.__name__))
            return None
        else:
            if resp is None:
                raise ResponseError('received a response of some kind, but command {} was expecting no response'.format(cmd.__class__.__name__))
            len_consumed = resp.decode(buf_resp)
            if len_consumed != len(buf_resp):
                raise ResponseError('response was decoded, but only {} of the {} available characters were consumed'.format(len_consumed, len(buf_resp)))
            return resp

    def execute_multiple_commands(self, *cmds):
        raise NotImplementedYetError('TODO')

    def _synchronously_send_and_recv(self, chars):
        # TODO: use this as the underlying function for the bulk of the common datagram handling
        # stuff in both execute_one_command and execute_multiple_commands
        raise NotImplementedYetError('TODO')


"""
if __name__ == '__main__':
    udp = Gemini2BackendUDP(0.25, 'gemini2')
#    resp = udp.execute_one_command(gemini_commands.G2Cmd_StartupCheck())
#    print(resp.get())
    resp = udp.execute_one_command(gemini_commands.G2Cmd_Echo('Ahooey Kablooie!'))
    print(resp.get())
"""

"""
if __name__ == '__main__':
    usb = Gemini2BackendSerial(0.25, '/dev/ttyACM0')
    resp = usb.execute_one_command(gemini_commands.G2Cmd_Echo('X'))
    print(resp.get())
"""
