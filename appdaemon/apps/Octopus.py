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

# Some defaults for the start/stop costs.  Note that these are used if no new values are found,
#    they do not act as limits if any new values are extracted.
HEADROOM = 0.01             # The amount above the values found to set the start values
DEFAULT_TESLA_THRESHOLD = 9
DEFAULT_WH_THRESHOLD = 9
DEFAULT_CURRENT_COST = 25
DEFAULT_MINIMUM_COST = 25

# Time in which to update start/stop values.  Specified as a single hour value,
#    which means the routine will run at least twice, on the hour and half past the hour,
#    just in case the first time fails for whatever reason.  
UPDATE_TIMESLOT = 20

class OctopusAnalysis(hass.Hass):


    def initialize(self):

        # Call Analyse method to initialise prices on first run
        self.Analyse({ })
        
        # Set the scheduled callback to Analyse for every thirty minutes, on the hour and on the half-hour
        # This needs two calls to run_hourly
        ts_start = time(0, 0, 0)
        self.run_hourly(self.Analyse, ts_start)
        ts_start = time(0, 30, 0)
        self.run_hourly(self.Analyse, ts_start)

        # Just as a bonus, run the Analyse method if the users changes the "tesla_min_slots"
        # or "wh_min_slots" sensors, to recalculate the values
        self.listen_state(self.VariablesChanged, "input_number.tesla_min_slots")
        self.listen_state(self.VariablesChanged, "input_number.wh_min_slots")


    def VariablesChanged(self, entity, attribute, old, new, kwargs):
        self.Analyse({ })


    def Analyse(self, kwargs):

        # This method runs every half hour
        # It downloads the next 24 hours or so of per-unit cost data from Octopus,
        #   then munges it to extract current price and minimum price
        #   If the time is within the hour defined in UPDATE_TIMESLOT, it then finds suitable 
        #   time slots to execute defined loads, based on the number of slots required
        #   which are defined in two input_numbers "tesla_min_slots" and "wh_min_slots"
        #   and sets the maximum and minimum costs in order to trigger the switches during
        #   those time slots.

        ts_now = (datetime.now(timezone.utc))
        self.log(" ")
        self.log("#########################################################################")
        self.log("Octopus Analyse executing at: " + str(ts_now) + " UTC")
        self.log("#########################################################################")

        # set default prices
        tesla_threshold = DEFAULT_TESLA_THRESHOLD
        wh_threshold = DEFAULT_WH_THRESHOLD
        current_price = DEFAULT_CURRENT_COST

        # Initialise price lists.  One per device, plus one that contains all prices
        global_price_list = []
        tesla_price_list = []
        wh_price_list = []

        # set up DST flag
        is_dst = self.get_state("binary_sensor.is_dst")
        if LOGLEVEL >= LOGINFO:
            self.log("                   is_dst: " + is_dst)
        
        # Set current time, and the to and from times for the call to the Octopus API
        ts_now = (datetime.now())
        ts_from = ts_now - timedelta(hours = 1)
        ts_to = ts_from + timedelta(hours = 26)

        # Get the defined time slots for the devices from HA
        tesla_start_time = datetime.strptime(self.get_state("input_datetime.tesla_start_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)
        tesla_stop_time = datetime.strptime(self.get_state("input_datetime.tesla_stop_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)
        wh_start_time = datetime.strptime(self.get_state("input_datetime.wh_start_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)
        wh_stop_time = datetime.strptime(self.get_state("input_datetime.wh_stop_time"), "%H:%M:%S").replace(year = ts_now.year, month = ts_now.month, day = ts_now.day)

        # Adjust start and stop times into tomorrow if the time slot is in the past
        if tesla_stop_time <= ts_now:
            tesla_start_time = tesla_start_time + timedelta(days = 1)
            tesla_stop_time = tesla_stop_time + timedelta(days = 1)
        if wh_stop_time <= ts_now:
            wh_start_time = wh_start_time + timedelta(days = 1)
            wh_stop_time = wh_stop_time + timedelta(days = 1)

        # Also adjust start times if they appear to be after the stop times (i.e. the slot straddles midnight)
        if tesla_start_time > tesla_stop_time:
            tesla_start_time = tesla_start_time - timedelta(days = 1)
        if wh_start_time > wh_stop_time:
            wh_start_time = wh_start_time - timedelta(days = 1)

        period_from = ts_from.isoformat()[0:25] + "Z"    # convert to and from times for API call into ISO format
        period_to = ts_to.isoformat()[0:25] + "Z"
        if LOGLEVEL >= LOGINFO:
            self.log("                 Time now: " + str(ts_now))
            self.log("         tesla_start_time: " + str(tesla_start_time))
            self.log("          tesla_stop_time: " + str(tesla_stop_time))
            self.log("            wh_start_time: " + str(wh_start_time))
            self.log("             wh_stop_time: " + str(wh_stop_time))
            self.log("              Period_from: " + period_from)
            self.log("                Period_to: " + period_to)

        payload = { 'period_from' : period_from, 'period_to' : period_to }
        r = requests.get(OCTOPUS_URL, params=payload)   # HTTP call to Octopus API

        if LOGLEVEL >= LOGDEBUG:
            self.log("Call returned HTTP code: " + str(r.status_code))
            self.log(r.content)
            self.log(r.json())

        timeslots = r.json()["results"]    # discard the bits of the response that aren't pricing data...
        for x in timeslots:                # ...and then loop through the bits that are
            price = round(x["value_inc_vat"], 3)
            start_time = iso8601.parse_date(x["valid_from"])
            end_time = iso8601.parse_date(x["valid_to"])
            start_time = start_time.replace(tzinfo=None)
            end_time = end_time.replace(tzinfo=None)

            # Adjust times for DST, as Octopus returns UTC times and things get messy if we try and 
            #   use timezone information to get it right.  The is_dst flag is maintained by HA,
            #   and reads "on" or "off", mildly irritatingly.
            if is_dst.upper() == "ON":
                start_time = start_time + timedelta(hours = 1)
                end_time = end_time + timedelta(hours = 1)
            
            global_price_list.append(price)  # keep list of all prices
            if (tesla_start_time <= start_time) and (tesla_stop_time >= end_time):
                tesla_price_list.append(price)   # add to list of prices for car charging if the data point is within the right time span
            if (wh_start_time <= start_time) and (wh_stop_time >= end_time):
                wh_price_list.append(price)      # add to list of prices for water heater if the data point is within the right time span

            if LOGLEVEL >= LOGDEBUG:
                self.log("Start time: " + str(start_time) + "   End time: " + str(end_time) + "   Price: " + str(price) + "   Current time: " + str(ts_now))
 
            if (ts_now >= start_time) and (ts_now <= end_time):
                current_price = price    # pick up the current price if this data is relevant
                if LOGLEVEL >= LOGDEBUG:
                    self.log("      Found current price: " + str(current_price))

        tesla_price_list.sort()
        wh_price_list.sort()
        if LOGLEVEL >= LOGDEBUG:
            self.log("             Global price list: " + str(global_price_list))
            self.log("       Sorted Tesla price list: " + str(tesla_price_list))
            self.log("Sorted water heater price list: " + str(wh_price_list))

        if ts_now.hour == UPDATE_TIMESLOT:    # Only update start and stop prices in the defined hour, normally 18:00-19:00
            # Calculate threshold prices
            # Use the <xxx>_time_slots input numbers to find a price level that will give the required number of slots.
            # The stop price is set to the start price plus a fixed hysteresis value for now, we might do something
            # cleverer later.
            # Note that the code block is duplicated per device, so modifications need making to all blocks
            if len(tesla_price_list) > 0:
                tesla_min_slots = int(float(self.get_state("input_number.tesla_min_slots")))
                if tesla_min_slots > len(tesla_price_list):
                    tesla_min_slots = len(tesla_price_list)
                if LOGLEVEL >= LOGDEBUG:
                    self.log("input_number.tesla_min_slots: " + str(tesla_min_slots))
                if tesla_min_slots > 0:
                    tesla_threshold = round(tesla_price_list[tesla_min_slots - 1] + HEADROOM, 3)
            else:
                tesla_threshold = DEFAULT_TESLA_THRESHOLD

            # Calculate start/stop prices
            # Use the <xxx>_time_slots input numbers to find a price level that will give the required number of slots.
            # The stop price is set to the start price plus a fixed hysteresis value for now, we might do something
            # cleverer later.
            # Note that the code block is duplicated per device, so modifications need making to all blocks
            if len(wh_price_list) > 0:
                wh_min_slots = int(float(self.get_state("input_number.wh_min_slots")))
                if wh_min_slots > len(wh_price_list):
                    wh_min_slots = len(wh_price_list)
                if LOGLEVEL >= LOGINFO:
                    self.log("input_number.wh_min_slots: " + str(wh_min_slots))
                if wh_min_slots > 0:
                    wh_threshold = round(wh_price_list[wh_min_slots - 1] + HEADROOM, 3)
            else:
                wh_threshold = DEFAULT_WH_THRESHOLD

            if LOGLEVEL >= LOGINFO:
                self.log ("      New Tesla threshold: " + str(tesla_threshold) + "p/kWh")
                self.log ("         New WH threshold: " + str(wh_threshold) + "p/kWh")
            self.set_state("input_number.tesla_threshold", state=tesla_threshold, attributes = {"unit_of_measurement": "p/kWh"})
            self.set_state("input_number.wh_threshold", state=wh_threshold, attributes = {"unit_of_measurement": "p/kWh"})

        # now save current price.  Done last so that the triggers in the OctopusSwitching method 
        # work with the start/stop values extracted above
        if LOGLEVEL >= LOGINFO:
            self.log ("        New minimum price: " + str(min(global_price_list)) + "p/kWh")
            self.log ("                New price: " + str(current_price) + "p/kWh")
        self.set_state("input_number.octopus_min_cost", state = min(global_price_list), attributes = {"unit_of_measurement": "p/kWh"})
        self.set_state("input_number.octopus_cur_cost", state = current_price, attributes = {"unit_of_measurement": "p/kWh"})
