from __future__ import annotations
from abc import ABC, abstractmethod
from point.gemini_commands import Backend, Gemini2Command, Gemini2Response
import serial
import socket
import struct
import multiprocessing
from point.gemini_exceptions import (
    G2BackendCommandNotSupportedError,
    G2BackendResponseError,
    G2BackendReadTimeoutError,
    G2BackendCommandError,
    G2BackendFeatureNotImplementedYetError,
)


class Gemini2Backend(ABC):
    def __enter__(self) -> Gemini2Backend:
        """Support usage of this class in `with` statements."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Disconnect and release associated resources."""
        self.disconnect()

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from hardware and release any associated resources."""

    @abstractmethod
    def execute_one_command(self, cmd: Gemini2Command) -> None:
        pass

    def _str_encoding(self):
        return 'ascii'


# TODO: handle serial.SerialTimeoutException (?)


class Gemini2BackendSerial(Gemini2Backend):
    def __init__(self, timeout: float, devname: str):
        self._timeout = timeout
        self._devname = devname

        # TODO: set baud to 115.2k or whatever here
        self._serial = serial.Serial(devname, timeout=self._timeout)
        self._serial.reset_input_buffer()

    def disconnect(self) -> None:
        """Disconnect from the serial port."""
        self._serial.close()

    def execute_one_command(self, cmd: Gemini2Command) -> None:
        if Backend.SERIAL not in cmd.supported_backends:
            raise G2BackendCommandNotSupportedError(
                f'Command {cmd.__class__.__name__} not supported on the serial backend.'
            )

        buf_cmd = cmd.encode()

        self._serial.write(buf_cmd.encode(self._str_encoding()))
        self._serial.reset_input_buffer()

        resp = cmd.response
        if resp is None:
            return

        # Ugh, we have to have special logic to handle cases where there may be no
        # response at all!
        # So what we do here is we send an additional 'echo' cmd after the actual cmd;
        # this way, we can actually discern between 0-bytes-returned and haven't-
        # blocked-long-enough.
        # NOTE: we only support the fixed-length decoder for now, to keep things simple
        if resp.zero_len_hack:
            assert resp.type == Gemini2Response.ResponseType.FIXED_LENGTH
            self._serial.write(b':CE\xff#')

        buf_resp = self._wait_for_response(resp)

        len_consumed = resp.decode(buf_resp)
        if len_consumed != len(buf_resp):
            raise G2BackendResponseError(
                f'Response was decoded, but only {len_consumed} of the {len(buf_resp)} '
                'available characters were consumed.'
            )

    def _wait_for_response(self, resp: Gemini2Response) -> str:
        # TODO: This seems like rather tight coupling with the Gemini2Response class.
        # There must be a better way!
        if resp.type == Gemini2Response.ResponseType.FIXED_LENGTH:
            return self._wait_for_response_fixed_length(resp)
        elif resp.type == Gemini2Response.ResponseType.HASH_TERMINATED:
            return self._wait_for_response_hash_terminated(resp)
        elif resp.type == Gemini2Response.ResponseType.SEMICOLON_DELIMITED:
            return self._wait_for_response_semicolon_delimited(resp)
        else:
            assert False

    def _wait_for_response_fixed_length(self, response: Gemini2Response) -> str:
        if response.zero_len_hack:
            buf_resp = self._get_chars(2)
            if buf_resp == '\xff#':
                return ''  # zero-length response confirmed
            buf_resp += self._get_chars(response.length_expected)
            if buf_resp[-2:] != '\xff#':
                raise G2BackendResponseError(
                    'Did not receive echo sequence for possibly-zero-length response.'
                )
            buf_resp = buf_resp[:-2]
        else:
            buf_resp = self._get_chars(response.length_expected)
        if '#' in buf_resp:
            raise G2BackendResponseError(
                "Received '#' terminator as part of a fixed-length response."
            )
        return buf_resp

    def _wait_for_response_hash_terminated(self, response: Gemini2Response) -> str:
        buf_resp = ''
        while not (len(buf_resp) >= 1 and buf_resp[-1] == '#'):
            buf_resp += self._get_char()
        return buf_resp

    def _wait_for_response_semicolon_delimited(self, response: Gemini2Response) -> str:
        buf_resp = ''
        field_count = 0
        while field_count < response.num_fields_expected:
            buf_resp += self._get_char()
            if buf_resp[-1] == ';':
                field_count += 1
        if '#' in buf_resp:
            raise G2BackendResponseError(
                "Received '#' terminator as part of a semicolon-delimited response."
            )
        return buf_resp

    def _get_char(self) -> str:
        char = self._serial.read(1).decode(self._str_encoding())
        if not char:
            raise G2BackendReadTimeoutError()
        return char

    def _get_chars(self, count: int) -> str:
        chars = self._serial.read(count).decode(self._str_encoding())
        assert len(chars) <= count
        if len(chars) != count:
            raise G2BackendReadTimeoutError()
        return chars


class Gemini2BackendUDP(Gemini2Backend):
    UDP_DEFAULT_LOCAL_ADDR = '0.0.0.0'
    UDP_DEFAULT_LOCAL_PORT = 11110
    UDP_DEFAULT_REMOTE_PORT = 11110

    # Maximum length of GeminiData field, leaving one character for the terminating
    # NULL.
    UDP_CMD_STR_LEN_MAX = 255 - 1

    # DatagramNumber[4] + LastDatagramNumber[4] + GeminiData[2]
    # {0 response chars, '#', NULL}
    UDP_RESP_DGRAM_LEN_MIN = 4 + 4 + 2

    # DatagramNumber[4] + LastDatagramNumber[4] + GeminiData[255]
    # {253 response chars, '#', NULL}
    UDP_RESP_DGRAM_LEN_MAX = 4 + 4 + 255

    # Essentially arbitrary; must be >= UDP_RESP_DGRAM_LEN_MAX.
    UDP_RECV_BUF_SIZE = 4096

    # How many times to attempt NACK recovery on a lost command or response datagram
    # before giving up and raising an exception.
    DEFAULT_RETRY_LIMIT = 5

    def __init__(
        self,
        timeout: float,
        remote_addr: str,
        local_addr: str = UDP_DEFAULT_LOCAL_ADDR,
        remote_port: int = UDP_DEFAULT_REMOTE_PORT,
        local_port: int = UDP_DEFAULT_LOCAL_PORT,
        retry_limit: int = DEFAULT_RETRY_LIMIT,
    ):
        self._timeout = timeout

        self._remote_addr = (remote_addr, remote_port)
        self._local_addr = (local_addr, local_port)

        self._retry_limit = retry_limit

        self._seqnum = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(self._timeout)
        self._sock.bind(self._local_addr)

        self._stats = {}
        self._stats['cmd_exec'] = 0
        self._stats['dgram_cmd_tx'] = 0
        self._stats['dgram_cmd_rx'] = 0
        self._stats['dgram_nack_tx'] = 0
        self._stats['dgram_nack_rx'] = 0

        self._command_lock = multiprocessing.Lock()

    def disconnect(self) -> None:
        """Close the socket connection."""
        self._sock.close()

    def execute_one_command(self, cmd: Gemini2Command) -> None:
        self._command_lock.acquire()
        try:
            self._execute_one_command(cmd)
        finally:
            self._command_lock.release()

    def _execute_one_command(self, cmd: Gemini2Command) -> None:
        if Backend.UDP not in cmd.supported_backends:
            raise G2BackendCommandNotSupportedError(
                f'Command {cmd.__class__.__name__} is not supported on the UDP backend.'
            )

        cmd_str = cmd.encode()
        if len(cmd_str) > self.UDP_CMD_STR_LEN_MAX:
            raise G2BackendCommandError(
                f'Command string is too long: {len(cmd_str)} > '
                f'{self.UDP_CMD_STR_LEN_MAX}.'
            )

        # If we get a response that references an earlier seqnum, it's from an earlier
        # command and we can freely discard and ignore it.
        min_seqnum = self._seqnum
        skip_send = False
        # TODO: Maybe receive packets in a separate thread and buffer them by their
        # seqnum, so that over here we can specifically wait on receiving a datagram
        # with the actual seqnum we want?
        # OR: Integrate the seqnum/last_seqnum processing into a separate function, so
        # that we can rapidly identify it and just immediately loop back to recv again
        # if it's wrong.

        # Upon a successful NACK that indicates the command was not received, we'll end
        # up back here.
        while True:
            if not skip_send:
                cmd_seqnum = self._seqnum

                buf_cmd = struct.pack('!II', cmd_seqnum, 0)
                buf_cmd += (cmd_str).encode(self._str_encoding())
                buf_cmd += b'\x00'

                self._sock.sendto(buf_cmd, self._remote_addr)
                self._stats['dgram_cmd_tx'] += 1

            skip_send = False

            did_retry = False
            try:
                buf_resp = self._sock.recv(self.UDP_RECV_BUF_SIZE)
            except socket.timeout:
                # NOTE: our NACK handling has one edge case where it may work wrong:
                # If the original reply DOES eventually come back, but just late, then
                # we'll probably trigger the mismatched-sequence-number check exception
                # later on.
                retry_num = 0
                while True:
                    if retry_num >= self._retry_limit:
                        raise G2BackendReadTimeoutError(
                            f'Gave up after {retry_num:d} NACK retry attempts.'
                        )
                    retry_num += 1
                    self._seqnum += 1
                    buf_nack = struct.pack('!IIc', self._seqnum, 0, b'\x15')
                    self._sock.sendto(buf_nack, self._remote_addr)
                    self._stats['dgram_nack_tx'] += 1
                    try:
                        buf_resp = self._sock.recv(self.UDP_RECV_BUF_SIZE)
                    except socket.timeout:
                        pass
                    else:
                        self._stats['dgram_nack_rx'] += 1
                        did_retry = True
                        break
            else:
                self._stats['dgram_cmd_rx'] += 1

            if len(buf_resp) > self.UDP_RESP_DGRAM_LEN_MAX:
                raise G2BackendResponseError(
                    'Received UDP response datagram larger than max length: '
                    f'{len(buf_resp)} > {self.UDP_RESP_DGRAM_LEN_MAX}.'
                )
            elif len(buf_resp) < self.UDP_RESP_DGRAM_LEN_MIN:
                raise G2BackendResponseError(
                    'Received UDP response datagram smaller than min length: '
                    f'{len(buf_resp)} < {self.UDP_RESP_DGRAM_LEN_MIN}.'
                )

            (seqnum, last_seqnum) = struct.unpack('!II', buf_resp[0:8])

            # this is a mess...
            if seqnum != self._seqnum:
                if seqnum < min_seqnum:
                    skip_send = True
                    continue
                elif seqnum < cmd_seqnum or seqnum > self._seqnum:
                    raise G2BackendResponseError(
                        'Mismatched sequence number in UDP response datagram: '
                        f'{seqnum} != {self._seqnum}.'
                    )

            if did_retry:
                if last_seqnum == cmd_seqnum:
                    print(
                        f'After {retry_num} NACK\'s, Gemini indicated that its response'
                        ' datagram was lost; successfully recovered.'
                    )
                else:
                    print(
                        f'After {retry_num} NACK\'s, Gemini indicated that our command '
                        'datagram was lost; will resend it.'
                    )
                    continue
            # else:
            #     if last_seqnum != 0:
            #         # NOTE: This may or may not actually be problematic;
            #         # but the docs do say that the field should be zero in normal
            #         # circumstances.
            #         print(
            #             'Received UDP response datagram with nonzero last_seqnum '
            #             f'{last_seqnum} in non-NACK situation (current seqnum: '
            #             f'{self._seqnum}).'

            self._seqnum += 1

            buf_resp = buf_resp[8:].decode(self._str_encoding())

            num_nulls = buf_resp.count('\x00')
            if num_nulls == 0:
                raise G2BackendResponseError(
                    f'Received UDP response buffer of length {len(buf_resp)} '
                    'containing no NULL terminator.'
                )
            elif num_nulls > 1:
                raise G2BackendResponseError(
                    f'Received UDP response buffer of length {len(buf_resp)} '
                    f'containing {num_nulls} NULL characters.'
                )
            elif buf_resp[-1] != '\x00':
                null_idx = buf_resp.rfind("\x00")
                raise G2BackendResponseError(
                    f'Received UDP response buffer of length {len(buf_resp)} with '
                    f'single NULL terminator at non-end index {null_idx}.'
                )
            buf_resp = buf_resp[:-1]

            resp = cmd.response
            if len(buf_resp) == 1 and buf_resp[0] == '\x06':
                if resp is not None:
                    raise G2BackendResponseError(
                        'Received ACK (no response), but command '
                        f'{cmd.__class__.__name__} expected to receive response '
                        f'{resp.__class__.__name__}.'
                    )
            else:
                if resp is None:
                    raise G2BackendResponseError(
                        'Received a response of some kind, but command '
                        f'{cmd.__class__.__name__} was expecting no response.'
                    )
                len_consumed = resp.decode(buf_resp)
                if len_consumed != len(buf_resp):
                    raise G2BackendResponseError(
                        f'Response was decoded, but only {len_consumed} of the '
                        f'{len(buf_resp)} available characters were consumed.'
                    )

            self._stats['cmd_exec'] += 1
            return

    def _synchronously_send_and_recv(self, chars: str):
        # TODO: use this as the underlying function for the bulk of the common datagram
        # handling stuff in execute_one_command.
        raise G2BackendFeatureNotImplementedYetError('TODO')

    def get_statistic(self, key: str) -> int:
        return self._stats[key]
