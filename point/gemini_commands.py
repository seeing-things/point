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
        # TODO: base/generic G2 native encoding
        pass

class Gemini2Command_Native_NoReply(Gemini2Command_Native):
    def response(): return None


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

# TODO: the echo cmd actually only supports one-char, not strs.
# so change the types involved here,
# and also in encode and/or decode, verify length of 1
class G2Cmd_Echo(Gemini2Command_LX200):
    def __init__(self, str):
        super().__init__()
        self._str = str
    def encode(self, chars): return super().encode('CE' + self._str)
    def response(self): return G2Rsp_Echo()
class G2Rsp_Echo(Gemini2Response_LX200): pass # .get() returns the string
# TODO: probably make the echo response class verify that the echoed string is the same as the one sent


#def echo(self, char):
#    """Test command. Should return the same character as the argument."""
#    return self.lx200_cmd('CE' + char, expect_reply=True)
#
#def align_to_object(self):
#    """Add selected object to pointing model."""
#    return self.lx200_cmd('Cm', expect_reply=True)
#
#def sync_to_object(self):
#    """Synchronize to selected object."""
#    return self.lx200_cmd('CM', expect_reply=True)
#
#def select_pointing_model(self, num):
#    """Select a pointing model (0 or 1)."""
#    return int(self.lx200_cmd('C' + chr(num), expect_reply=True))
#
#def select_pointing_model_for_io(self):
#    """Selects the active pointing model for I/O access."""
#    return int(self.lx200_cmd('Cc', expect_reply=True))
#
#def get_pointing_model(self):
#    """Get number of active pointing model (0 or 1)."""
#    return int(self.lx200_cmd('C?', expect_reply=True))
#
#def init_align(self):
#    """Perform Initial Align with selected object."""
#    return self.lx200_cmd('CI', expect_reply=True)
#
#def reset_model(self):
#    """Resets the currently selected model."""
#    return int(self.lx200_cmd('CR', expect_reply=True))
#
#def reset_last_align(self):
#    """Resets the last alignment of currently selected model."""
#    return int(self.lx200_cmd('CU', expect_reply=True))






def hello(str):
    print(str)


# I <3 Python and underscores
if __name__ == '__main__':
    hello('hi')
