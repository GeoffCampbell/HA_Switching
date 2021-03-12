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
TESLA_LOCATION_TRACKER = "device_tracker.kod_location_tracker"
TESLA_HOME_STRING = "Home"
TESLA_CHARGING_SWITCH = "switch.kod_charger_switch"

class TeslaSwitching(hass.Hass):


    def initialize(self):

        # Use the HA trigger mechanism to call TeslaSwitches whenever the unit cost or threshold changes...
        self.listen_state(self.TeslaSwitches, "input_number.octopus_cur_cost")
        self.listen_state(self.TeslaSwitches, "input_number.tesla_threshold")

        # ...or when the user over-rides this mechanism to manually switch a device on.
        self.listen_state(self.TeslaSwitches, "input_boolean.tesla_override")

        # Also call when the car is plugged into a charger.
        self.listen_state(self.TeslaSwitches, "binary_sensor.kod_charger_sensor", new="on")

    def TeslaSwitches(self, entity, attribute, old, new, kwargs):

        # This method gets called whenever the sensor "octopus_cur_cost" changes or
        # a manual over-ride is performed by the user.
        #
        # It compares the current price against the start and stop prices calculated 
        # by Analyse for large-load devices (Tesla charging), and 
        # turns them on and off accordingly.

        ts_now = (datetime.now())
        self.log(" ")
        self.log("#########################################################################")
        self.log("TeslaSwitches executing at: " + str(ts_now))
        self.log("#########################################################################")

        # Load override switches - these allow the user to manually turn on big loads.
        tesla_override = self.get_state("input_boolean.tesla_override")
        if LOGLEVEL >= LOGINFO:
            self.log("           Tesla override: " + tesla_override)

        # Read start and stop times from HA.
        tesla_start_time = datetime.strptime(self.get_state("input_datetime.tesla_start_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)
        tesla_stop_time = datetime.strptime(self.get_state("input_datetime.tesla_stop_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)

        # Adjust start and stop times into tomorrow if the time slot is in the past
        if tesla_stop_time <= ts_now:
            tesla_start_time = tesla_start_time + timedelta(days = 1)
            tesla_stop_time = tesla_stop_time + timedelta(days = 1)

        # Also adjust start times if they appear to be after the stop times (i.e. the slot straddles midnight)
        if tesla_start_time > tesla_stop_time:
            tesla_start_time = tesla_start_time - timedelta(days = 1)

        # Get stored current price, start and stop limit prices from HA
        current_price = self.get_state("input_number.octopus_cur_cost")
        tesla_threshold = self.get_state("input_number.tesla_threshold")

        if LOGLEVEL >= LOGINFO:
            self.log("                 Time now: " + str(ts_now))
            self.log("         tesla_start_time: " + str(tesla_start_time))
            self.log("          tesla_stop_time: " + str(tesla_stop_time))
            self.log("            Current price: " + str(current_price))
            self.log("          Tesla threshold: " + str(tesla_threshold))

        # Tesla charging switch.
        if tesla_override == "off":    # Only execute if the manual over-ride is off
            tesla_location = self.get_state(TESLA_LOCATION_TRACKER)
            if tesla_location.upper() == TESLA_HOME_STRING.upper():    # Only execute if the car is at home
                if (tesla_start_time <= ts_now) and (tesla_stop_time >= ts_now):    # Only execute if we're in the time slot defined
                    if LOGLEVEL >= LOGINFO:
                        self.log("           Tesla location: " + tesla_location)
                        if float(current_price) <= float(tesla_threshold):     # Turn on if current price is below the defined start price
                            if LOGLEVEL >= LOGINFO:
                                self.log("Turning on Tesla charging.")
                            self.turn_on(TESLA_CHARGING_SWITCH)
                        if float(current_price) > float(tesla_threshold):      # Turn off if current price is above the defined stop price
                            if LOGLEVEL >= LOGINFO:
                                self.log("Too expensive, turning off Tesla charging.")
                            self.turn_off(TESLA_CHARGING_SWITCH)
                else:    # If we're outside the time slot, and there's no over-ride in force, turn it off.
                    if LOGLEVEL >= LOGINFO:
                        self.log("Outside time limits, turning off Tesla charging.")
                    self.turn_off(TESLA_CHARGING_SWITCH)
            else:
                if LOGLEVEL >= LOGINFO:
                    self.log("Tesla not at home, exiting.")
        else:    # If the over-ride is on, turn the charging on
            if LOGLEVEL >= LOGINFO:
                self.log("Manual override in force, turning Tesla charging on.")
            self.turn_on(TESLA_CHARGING_SWITCH)
