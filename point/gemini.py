import datetime
import time
import calendar
import point.gemini_backend
from point.gemini_commands import *


__all__ = ['Gemini2']


# TODO: Handle UDP response timeouts appropriately
# TODO: Restore "good" documentation to the classes and functions and stuff


class Gemini2(object):
    """Implements serial and UDP command interfaces for Gemini 2.

    This class implements the command interface supported by the Gemini 2
    astronomical positioning system. The Gemini command set has evolved
    over time with the software. This class supports commands from the Level 5
    command interface. These commands are documented on this webpage:
    http://www.gemini-2.com/web/L5V2_1serial.html Both LX200 and Gemini Native
    command formats are supported.

    For numeric commands only the double-precision format is supported. Errors
    will occur if the precision is changed to HIGH or LOW precision.
    """

    class ResponseException(Exception):
        """Raised on bad command responses from Gemini."""

    class ReadTimeoutException(Exception):
        """Raised when read from Gemini times out"""

    def __init__(self, backend):
        """Constructs a Gemini2 object.

        Args:
            backend: A Gemini2Backend object. This can be a Gemini2BackendSerial
                instance (if using USB serial) or a Gemini2BackendUDP instance
                (if using UDP datagrams).
        """
        self._backend = backend
        self.set_double_precision()

    def __del__(self):
        try:
            self.slew_ra (0.0)
        except: pass
        try:
            self.slew_dec(0.0)
        except: pass

    def exec_cmd(self, cmd):
        return self._backend.execute_one_command(cmd)

    def exec_cmds(self, *cmds):
        return self._backend.execute_multiple_commands(*cmds)


    ## Commands
    # All commands in the following sections are placed in the same order as
    # they appear in the serial command reference page:
    # http://www.gemini-2.com/web/L5V2_1serial.html


    ### Special Commands

    def startup_check(self):
        """Check startup state and type of mount."""
        return self.exec_cmd(G2Cmd_StartupCheck()).get()

    def select_startup_mode(self, mode):
        self.exec_cmd(G2Cmd_SelectStartupMode(mode))


    ### Macro Commands

    def enq_macro(self):
        return self.exec_cmd(G2Cmd_MacroENQ()).get()


    ### Synchronization Commands

    def echo(self, char):
        """Test command. Should return the same character as the argument."""
        return self.exec_cmd(G2Cmd_Echo(char)).get()

    # TODO: reimplement this
#    def align_to_object(self):
#        """Add selected object to pointing model."""
#        return self.lx200_cmd('Cm', expect_reply=True)

    # TODO: reimplement this
#    def sync_to_object(self):
#        """Synchronize to selected object."""
#        return self.lx200_cmd('CM', expect_reply=True)

    # TODO: reimplement this
#    def select_pointing_model(self, num):
#        """Select a pointing model (0 or 1)."""
#        return int(self.lx200_cmd('C' + chr(num), expect_reply=True))

    # TODO: reimplement this
#    def select_pointing_model_for_io(self):
#        """Selects the active pointing model for I/O access."""
#        return int(self.lx200_cmd('Cc', expect_reply=True))

    # TODO: reimplement this
#    def get_pointing_model(self):
#        """Get number of active pointing model (0 or 1)."""
#        return int(self.lx200_cmd('C?', expect_reply=True))

    # TODO: reimplement this
#    def init_align(self):
#        """Perform Initial Align with selected object."""
#        return self.lx200_cmd('CI', expect_reply=True)

    # TODO: reimplement this
#    def reset_model(self):
#        """Resets the currently selected model."""
#        return int(self.lx200_cmd('CR', expect_reply=True))

    # TODO: reimplement this
#    def reset_last_align(self):
#        """Resets the last alignment of currently selected model."""
#        return int(self.lx200_cmd('CU', expect_reply=True))


    ### Focus Control Commands

    # TODO: reimplement this
#    def focus_in(self):
#        self.lx200_cmd('F+')

    # TODO: reimplement this
#    def focus_out(self):
#        self.lx200_cmd('F-')

    # TODO: reimplement this
#    def focus_stop(self):
#        self.lx200_cmd('FQ')

    # TODO: reimplement this
#    def focus_fast(self):
#        self.lx200_cmd('FF')

    # TODO: reimplement this
#    def focus_medium(self):
#        self.lx200_cmd('FM')

    # TODO: reimplement this
#    def focus_slow(self):
#        self.lx200_cmd('FS')


    ### Get Information Commands

    # TODO: reimplement this
#    def get_alt(self):
#        """Altitude in signed degrees format [-90.0, +90.0]."""
#        return float(self.lx200_cmd('GA', expect_reply=True))

    # TODO: reimplement this
#    def get_led_brightness(self):
#        return int(self.lx200_cmd('GB', expect_reply=True))

    # TODO: reimplement this
#    def get_local_date(self):
#        """Date as a string in mm/dd/yy format."""
#        return self.lx200_cmd('GC', expect_reply=True)

    # TODO: reimplement this
#    def get_clock_format(self):
#        return self.lx200_cmd('Gc', expect_reply=True)

    # TODO: reimplement this
#    def get_dec(self):
#        """Apparent declination in signed degrees [-90.0,+90.0]."""
#        return float(self.lx200_cmd('GD', expect_reply=True))

    # TODO: reimplement this
#    def get_obj_dec(self):
#        """Selected object's declination in signed degrees."""
#        return float(self.lx200_cmd('Gd', expect_reply=True))

    # TODO: reimplement this
#    def get_alarm_time(self):
#        return self.lx200_cmd('GE', expect_reply=True)

    # TODO: reimplement this
#    def get_utc_offset(self):
#        return self.lx200_cmd('GG', expect_reply=True)

    # TODO: reimplement this
#    def get_site_lon(self):
#        return float(self.lx200_cmd('Gg', expect_reply=True))

    # TODO: reimplement this
#    def get_hour_angle(self):
#        """Hour angle in signed degrees."""
#        return float(self.lx200_cmd('GH', expect_reply=True))

    # TODO: reimplement this
#    def get_info_buffer(self):
#        return self.lx200_cmd('GI', expect_reply=True)

    # TODO: reimplement this
#    def get_local_time(self):
#        """Local time in hours as a float."""
#
#        # For some reason time is not very precise in double precision. It's
#        # worse than one second. High precision format has better resolution.
#        return float(self.lx200_cmd('GL', expect_reply=True))

    # TODO: reimplement this
#    def get_meridian_side(self):
#        """Returns 'E' or 'W' to indicate side of meridian."""
#        return self.lx200_cmd('Gm', expect_reply=True)

    # TODO: reimplement this
#    def get_site_name(self, site_num=0):
#        site_letters = ['M', 'N', 'O', 'P']
#        return self.lx200_cmd('G' + site_letters[site_num], expect_reply=True)

    # TODO: reimplement this
#    def get_ra(self):
#        """Apparent right ascension in hours [0.0,24.0)."""
#        return float(self.lx200_cmd('GR', expect_reply=True))

    # TODO: reimplement this
#    def get_obj_ra(self):
#        """Selected object's right ascension in signed degrees."""
#        return float(self.lx200_cmd('Gr', expect_reply=True))

    # TODO: reimplement this
#    def get_sidereal_time(self):
#        return float(self.lx200_cmd('GS', expect_reply=True))

    # TODO: reimplement this
#    def get_site_lat(self):
#        return float(self.lx200_cmd('Gt', expect_reply=True))

    # Omitting command 'GV' which is redundant with 'GVN'.

    # TODO: reimplement this
#    def get_software_build_date(self):
#        return self.lx200_cmd('GVD', expect_reply=True)

    # TODO: reimplement this
#    def get_software_level(self):
#        return self.lx200_cmd('GVN', expect_reply=True)

    # TODO: reimplement this
#    def get_product_string(self):
#        return self.lx200_cmd('GVP', expect_reply=True)

    # TODO: reimplement this
#    def get_software_build_time(self):
#        return self.lx200_cmd('GVT', expect_reply=True)

    # TODO: reimplement this
#    def get_max_velocity(self):
#        """Maximum velocity of both axes."""
#        return self.lx200_cmd('Gv', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity_ra(self):
#        return self.lx200_cmd('GW', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity_dec(self):
#        return self.lx200_cmd('Gw', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity(self):
#        """Velocity of both axes: RA, DEC (2 characters)."""
#        return self.lx200_cmd('Gu', expect_reply=True, reply_len=2)

    # TODO: reimplement this
#    def get_az(self):
#        """Azimuth in signed degrees format [0.0, 360.0)."""
#        return float(self.lx200_cmd('GZ', expect_reply=True))


    ### Park Commands

    # TODO: reimplement this
#    def park_home(self):
#        self.lx200_cmd('hP')

    # TODO: reimplement this
#    def park_startup(self):
#        self.lx200_cmd('hC')

    # TODO: reimplement this
#    def park_zenith(self):
#        self.lx200_cmd('hZ')

    # TODO: reimplement this
#    def sleep(self):
#        self.lx200_cmd('hN')

    # TODO: reimplement this
#    def wake(self):
#        self.lx200_cmd('hW')


    ### Move Commands

    # TODO: reimplement this
#    def goto_object_horiz(self):
#        """Goto object selected with horizontal coordinates."""
#        return self.lx200_cmd('MA', expect_reply=True)

    # TODO: reimplement this
#    def search_pattern(self, arcmins):
#        """Move at find speed in a meander search pattern."""
#        self.lx200_cmd('MF' + str(arcmins), expect_reply=True)

    # TODO: reimplement this
#    def move_lock(self):
#        self.lx200_cmd('ML', expect_reply=True)

    # TODO: reimplement this
#    def move_unlock(self):
#        self.lx200_cmd('Ml', expect_reply=True)

    # TODO: reimplement this
#    def meridian_flip(self):
#        return self.lx200_cmd('Mf', expect_reply=True)

    # TODO: reimplement this
#    def goto_object(self, allow_meridian_flip=False):
#        """Goto object selected from database or equatorial coordinates."""
#        cmd = 'MM' if allow_meridian_flip else 'MS'
#        return lx200_cmd(cmd, expect_reply=True)

    # TODO: reimplement this
#    def move(self, direction):
#        """Move in a direction: 'east', 'west', 'north', or 'south'."""
#        if direction not in ['east', 'west', 'north', 'south']:
#            raise ValueError('invalid direction for move command')
#        self.lx200_cmd('M' + direction[0])

    # TODO: reimplement this
#    def move_ticks(self, ra_steps, dec_steps):
#        self.lx200_cmd('mi' + str(ra_steps) + ';' + str(dec_steps))

    # TODO: reimplement this
#    def set_step_multiplier(self, multiplier):
#        self.lx200_cmd('mm' + str(multiplier))


    ### Precision Guiding Commands


    ### Object/Observing/Output Commands


    ### Precession and Refraction Commands


    ### Precision Commands

    def get_precision(self):
        return self.exec_cmd(G2Cmd_GetPrecision()).get()

    def toggle_precision(self):
        self.exec_cmd(G2Cmd_TogglePrecision())

    def set_double_precision(self):
        self.exec_cmd(G2Cmd_SetDblPrecision())


    ### Quit Motion Commands


    ### Rate Commands


    ### Set Commands


    ### Site Selection Commands


    ### Native Commands


    ### Undocumented Commands

    def undoc_set_ra_divisor(self, div):
        self.exec_cmd(G2Cmd_Undoc_RA_Divisor_Set(div))

    def undoc_set_dec_divisor(self, div):
        self.exec_cmd(G2Cmd_Undoc_DEC_Divisor_Set(div))

    def undoc_ra_start_movement(self):
        self.exec_cmd(G2Cmd_Undoc_RA_StartStop_Set(G2Stopped.NOT_STOPPED))
    def undoc_ra_stop_movement(self):
        self.exec_cmd(G2Cmd_Undoc_RA_StartStop_Set(G2Stopped.STOPPED))

    def undoc_dec_start_movement(self):
        self.exec_cmd(G2Cmd_Undoc_DEC_StartStop_Set(G2Stopped.NOT_STOPPED))
    def undoc_dec_stop_movement(self):
        self.exec_cmd(G2Cmd_Undoc_DEC_StartStop_Set(G2Stopped.STOPPED))












    ### Wrapper Methods
    # These are methods that wrap one or more of the low-level interface
    # commands to provide extra functionality, abstration, or programming
    # convenience.

    def get_unix_time(self):
        """Get UNIX time (seconds since 00:00:00 UTC on 1 Jan 1970)"""

        # Slight risk that date and time commands will be inconsistent if
        # one is called just before UTC midnight and the other is called just
        # after midnight but there is no single command to retrieve the date
        # and time in one atomic operation so this is the best we can do.
        date = self.get_local_date()
        time = self.get_local_time() * 3600.0  # seconds since 00:00:00
        hours = int(time / 3600.0)
        time -= hours * 3600.0
        minutes = int(time / 60.0)
        time -= minutes * 60.0
        seconds = int(time)
        time -= seconds
        microseconds = int(time * 1e6)
        t = datetime.datetime(
            2000 + int(date[6:8]), # year
            int(date[0:2]),        # month
            int(date[3:5]),        # day
            hours,
            minutes,
            seconds,
            microseconds,
        )
        return calendar.timegm(t.timetuple())

    def slew_ra(self, rate):
        """Variable rate slew in the right ascension / hour angle axis.

        This slew command allows changes to the slew rate on the fly, in
        contrast to move commands which do not.

        Args:
            rate: Slew rate in degrees per second. Positive values move east,
                toward increasing right ascension.
        """
        # print('slew_ra: rate = ' + str(rate))
        if rate != 0.0:
            # the divisor is negated here to reverse the direction
            div = -int(12e6 / (6400.0 * rate))
        else:
            div = 0

        self.undoc_set_ra_divisor(div)
        #if div != 0:
        #    self.undoc_ra_start_movement()
        #else:
        #    self.undoc_ra_stop_movement()

    def slew_dec(self, rate):
        """Variable rate slew in the declination axis.

        This slew command allows changes to the slew rate on the fly, in
        contrast to move commands which do not.

        Args:
            rate: Slew rate in degrees per second. Positive values move toward
                increasing declination when the mount is west of the meridian.
                Positive values move toward decreasing declination when the
                mount is east of the meridian.
        """
        # print('slew_dec: rate = ' + str(rate))
        if rate != 0.0:
            div = int(12e6 / (6400.0 * rate))
        else:
            div = 0

        self.undoc_set_dec_divisor(div)
        #if div != 0:
        #    self.undoc_dec_start_movement()
        #else:
        #    self.undoc_dec_stop_movement()


if __name__ == '__main__':
    g = Gemini2(gemini_backend.Gemini2BackendUDP(0.25, '192.168.10.100'))
    print('established UDP connection to mount')

    time.sleep(1.0)

    print('invoking ENQ macro:')
    print(g.enq_macro())

    time.sleep(1.0)

#    print('slewing RA @ -1.0 deg/sec for 3.0 secs')
#    g.slew_ra(-1.0)
#    time.sleep(3.0)
#    g.slew_ra(0.0)
#    print('done')
#
#    time.sleep(1.0)
#
#    print('slewing DEC @ -1.0 deg/sec for 3.0 secs')
#    g.slew_dec(-1.0)
#    time.sleep(3.0)
#    g.slew_dec(0.0)
#    print('done')

    time.sleep(1.0)

    print('invoking ENQ macro:')
    print(g.enq_macro())
