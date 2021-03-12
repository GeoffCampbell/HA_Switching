import hassapi as hass
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from datetime import time
import requests
import iso8601

# Logging levels: 1 - Errors only
#                 2 - Information messages
#                 3 - Debug messages
LOGERROR = 1
LOGINFO = 2
LOGDEBUG = 3

LOGLEVEL = LOGINFO

###############
# constants for configuration - edit to suit your Octopus Account and consumption requirements
###############

# 'AGILE-18-02-21' is the product code, which appears to be valid for Agile throughout the UK
#     but should perhaps be assumed to be subject to change in future
#
# 'E-1R-AGILE-18-02-21-K' is the tariff code, which will need setting correctly for your area.
#     Log into your Octopus account and see https://octopus.energy/dashboard/developer/ for the
#     correct tariff code for your area, cunningly hidden in the URL under "Unit Rates" towards
#     the bottom of the page.  Mostly it just seems to be the final letter that changes per 
#     region.
OCTOPUS_PRODUCT_CODE = "AGILE-18-02-21"
OCTOPUS_TARIFF_CODE = "E-1R-AGILE-18-02-21-K"
OCTOPUS_URL = "https://api.octopus.energy/v1/products/" + OCTOPUS_PRODUCT_CODE + "/electricity-tariffs/" + OCTOPUS_TARIFF_CODE + "/standard-unit-rates/"

# Definitions for the HA devices used
IMMERSION_SWITCH = "switch.bf9dc8fccf7de43ea4lx7j"

class ImmersionSwitching(hass.Hass):


    def initialize(self):

        # Use the HA trigger mechanism to call Switches whenever the unit cost or threshold changes...
        self.listen_state(self.ImmersionSwitches, "input_number.octopus_cur_cost")
        self.listen_state(self.ImmersionSwitches, "input_number.wh_threshold")

        # ...or when the user over-rides this mechanism to manually switch a device on.
        self.listen_state(self.ImmersionSwitches, "input_boolean.wh_override")


    def ImmersionSwitches(self, entity, attribute, old, new, kwargs):

        # This method gets called whenever the sensor "octopus_cur_cost" changes or
        # a manual over-ride is performed by the user.
        #
        # It compares the current price against the start and stop prices calculated 
        # by Analyse for two large-load devices (Tesla charging and water heating), and 
        # turns them on and off accordingly.
        #
        # I will probably get around to parameterising all this stuff and running
        # individual instances for each device, but that's for another day.

        ts_now = (datetime.now())
        
        self.log(" ")
        self.log("#########################################################################")
        self.log("Immersion Switches executing at: " + str(ts_now))
        self.log("#########################################################################")

        # Load override switches - these allow the user to manually turn on big loads.
        immersion_override = self.get_state("input_boolean.wh_override")
        if LOGLEVEL >= LOGINFO:
            self.log("    Water heater override: " + immersion_override)

        # Read start and stop times from HA.
        immersion_start_time = datetime.strptime(self.get_state("input_datetime.wh_start_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)
        immersion_stop_time = datetime.strptime(self.get_state("input_datetime.wh_stop_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)

        # Adjust start and stop times into tomorrow if the time slot is in the past
        if immersion_stop_time <= ts_now:
            immersion_start_time = immersion_start_time + timedelta(days = 1)
            immersion_stop_time = immersion_stop_time + timedelta(days = 1)

        # Also adjust start times if they appear to be after the stop times (i.e. the slot straddles midnight)
        if immersion_start_time > immersion_stop_time:
            immersion_start_time = immersion_start_time - timedelta(days = 1)

        # Get stored current price, start and stop limit prices from HA
        current_price = self.get_state("input_number.octopus_cur_cost")
        immersion_threshold = self.get_state("input_number.wh_threshold")

        if LOGLEVEL >= LOGINFO:
            self.log("                 Time now: " + str(ts_now))
            self.log("     immersion_start_time: " + str(immersion_start_time))
            self.log("      immersion_stop_time: " + str(immersion_stop_time))
            self.log("            Current price: " + str(current_price))
            self.log("      immersion threshold: " + str(immersion_threshold))

        # Water heater switch.  
        if immersion_override == "off":
            if (immersion_start_time <= ts_now) and (immersion_stop_time >= ts_now):
                if float(current_price) <= float(immersion_threshold):
                    if LOGLEVEL >= LOGINFO:
                        self.log("Turning on water heater.")
                    self.turn_on(IMMERSION_SWITCH)
                if float(current_price) > float(immersion_threshold):
                    if LOGLEVEL >= LOGINFO:
                        self.log("Too expensive, turning off water heater.")
                    self.turn_off(IMMERSION_SWITCH)
            else:
                if LOGLEVEL >= LOGINFO:
                    self.log("Outside time limits, turning off water heater.")
                self.turn_off(IMMERSION_SWITCH)
        else:
            if LOGLEVEL >= LOGINFO:
                self.log("Manual override in force, turning water heater on.")
            self.turn_on(IMMERSION_SWITCH)

