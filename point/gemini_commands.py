from abc import *


####################################################################################################


class Gemini2Command(ABC):
    # input: string containing basic command information
    # output: string containing fully encoded command with prefix, postfix, etc
    @abstractmethod
    def encode(self, chars): pass

    # return: a Gemini2Response-derived object if this command expects a response
    # return: None if this command does not expect a response
    @abstractmethod
    def response(): pass

    # raised when invalid arguments are provided for encoding the command
    class ArgumentError(Exception): pass

# ==================================================================================================

class Gemini2Command_ACK(Gemini2Command):
    def encode(self, chars):
        return '\x06'

class Gemini2Command_ACK_NoReply(Gemini2Command_ACK):
    def response(): return None

# --------------------------------------------------------------------------------------------------

class Gemini2Command_LX200(Gemini2Command):
    def encode(self, chars):
        return ':' + chars + '#'

class Gemini2Command_LX200_NoReply(Gemini2Command_LX200):
    def response(): return None

# --------------------------------------------------------------------------------------------------

class Gemini2Command_Native(Gemini2Command):
    def encode(self, chars):
        return chars + compute_checksum(chars) + '#'

    @staticmethod
    def compute_checksum(chars):
        csum = 0
        for char in chars:
            csum = csum ^ ord(char)
        return (csum % 128) + 64

class Gemini2Command_Native_Get(Gemini2Command_Native):
    def encode(self, chars):
        return super().encode('<' + self.id() + ':' + param)

    @abstractmethod
    def id(self): pass

    def param(self): return None

class Gemini2Command_Native_Set(Gemini2Command_Native):
    def encode(self, chars):
        return super().encode('<' + self.id() + ':' + param)

    @abstractmethod
    def id(self): pass

    def param(self): return None


"""
class Gemini2Command_Native(Gemini2Command):
    def encode(self, chars):


        # TODO: base/generic G2 native encoding
        pass

class Gemini2Command_Native_NoReply(Gemini2Command_Native):
    def response(): return None
"""


####################################################################################################


class Gemini2Response(ABC):
    def __init__(self):
        self._decoded = False

    # input: string containing this response, and potentially additional responses to other commands
    # output: integer representing how many characters from the input were decoded for this response
    @abstractmethod
    def decode(self, chars):
        assert not self._decoded
        self._decoded = True
        if self.fixed_len() is not None:
            idx = self.fixed_len()
            if len(chars) < idx:
                raise ResponseTooShortError(len(chars), idx)
            self._resp_str = chars[:idx]
            return idx
        else:
            idx = chars.find('#')
            if idx == -1:
                raise ResponseMissingTerminatorError(len(chars))
            self._resp_str = chars[:idx]
            return idx + 1

    # return: integer representing how many characters are expected for a fixed-length response
    # return: None if this response is terminated by a '#' character
    @abstractmethod
    def fixed_len(self): pass

    # output: decoded response string (derived classes should override and interpret it further)
    def get(self):
        assert self._decoded
        return self._resp_str

    # raised when the response cannot be decoded properly for whatever reason
    class ResponseError(Exception): pass

    # raised when a fixed-length response is presented with fewer characters than it needs
    class ResponseTooShortError(ResponseError):
        def __init__(self, actual, expected):
            super().__init__('response too short: length <= {}, expected {}'.format(actual, expected))

    # raised when a '#'-terminated response is presented with no '#' character
    class ResponseMissingTerminatorError(ResponseError):
        def __init__(self, actual):
            super().__init__('response with length <= {} not terminated with a \'#\' character'.format(actual))

# ==================================================================================================

class Gemini2Response_ACK(Gemini2Response):
    def decode(self, chars):
        ret = super().decode(chars)
        if len(self._resp_str) != 1:
            raise ACKResponseWrongLengthError(len(self._resp_str), 1)
        return ret

    def fixed_len(self):
        return None

    class ACKResponseWrongLengthError(Gemini2Response.ResponseError):
        def __init__(self, actual, expected):
            super().__init__('ACK response with wrong length {}: expected {}'.format(actual, expected))

# --------------------------------------------------------------------------------------------------

class Gemini2Response_LX200(Gemini2Response):
    def __init__(self, fixed_len=None):
        super().__init__()
        self._fixed_len = fixed_len

    def decode(self, chars):
        return super().decode(chars)

    def fixed_len(self):
        return self._fixed_len

# --------------------------------------------------------------------------------------------------

class Gemini2Response_Native(Gemini2Response):
    def decode(self, chars):
        # TODO: base/generic G2 native decoding
        pass

    def fixed_len(self):
        return None

    def get(self):
        # TODO: need to return our post-processed string, not self._resp_str (raw from superclass)
        pass


####################################################################################################


## Commands
# All commands in the following sections are placed in the same order as
# they appear in the serial command reference page:
# http://www.gemini-2.com/web/L5V2_1serial.html

"""

BRETT'S BRAIN DUMP OF COMMANDS THAT WE ACTUALLY *DO* NEED
=========================================================
get RA
get DEC
get AZ
get ALT
set double precision
native 411-412 (do arcsec/sec conversions automagically)
native 21
get meridian side
native 130-137

LESS IMPORTANT ONES
===================
all the date+time shit (some of this is under 'Set' category for some idiotic reason)
all the site shit
get info buffer
velocities
park stuff
all move commands + quit-moving commands
native 120-122
native 190-192 (191 = "do not track at all")
native 220-223
native 826
native 65533-65535

BELOW THAT
==========
everything else in category/alphabetical order

"""


### Special Commands

class G2Cmd_StartupCheck(Gemini2Command_ACK):
    def response(self): return G2Rsp_StartupCheck()
class G2Rsp_StartupCheck(Gemini2Response_ACK): pass # .get() returns the char


### Synchronization Commands

class G2Cmd_Echo(Gemini2Command_LX200):
    def __init__(self, char):
#        super().__init__()
        self._char = char
    def encode(self):
        if len(self._char) != 1:
            raise ArgumentError('echo command only supports a single character')
        return super().encode('CE' + self._char)
    def response(self): return G2Rsp_Echo()
class G2Rsp_Echo(Gemini2Response_LX200): pass # .get() returns the char

# ...


### Focus Control Commands

# ...


### Get Information Commands

# ...


### Park Commands

# ...


### Move Commands

# ...


### Precision Guiding Commands

# ...


### Object/Observing/Output Commands

# ...


### Precession and Refraction Commands

# ...


### Precision Commands

class G2Cmd_GetPrecision(Gemini2Command_LX200):
    def encode(self):
        return super().encode('P')
    def response(self): return G2Rsp_GetPrecision()
class G2Rsp_GetPrecision(Gemini2Response_LX200): pass # .get() returns the big long ugly 14-char string
# TODO: invent an enum and implement decode() in this response to convert the str to the enum val

class G2Cmd_TogglePrecision(Gemini2Command_LX200_NoReply):
    def encode(self):
        return super().encode('U')

class G2Cmd_SetDblPrecision(Gemini2Command_LX200_NoReply):
    def encode(self):
        return super().encode('u')


### Quit Motion Commands

# ...


### Rate Commands

# ...


### Set Commands

# ...


### Site Selection Commands

# ...
