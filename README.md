# HA_Switching
AppDaemon project to switch big electrical loads on and off to track Octopus billing rates.

This is a set of Python routines to run under AppDaemon, in turn running under Home Assistant.  They allow the tracking of the Octopus Agile electricity rates, and pick the cheapest half-hourly slots within a defined time window to allow big electrical loads to run during the cheapest parts of the day.

We use this to control an electric water heater and an electric car charger, but anything that consumes a reasonable chunk of electricity whilst not needing to run at specific times is fair game.

In the default configuration, the four cheapest half-hourly slots between 00:00 and 08:00 are chosen, however all of these are set up as variables so you can add them to a Home Assistant dashboard.

This project was used to teach myself Home Assistant and Python, so I make no representations that this is good code, or the best way to approach the problem.  All suggestions for improvements gratefully received.

You will need:

1) A working Home Assistant installation with whatever integrations your switches require;
2) A working Octopus Agile account with functioning API access (see https://octopus.energy/dashboard/developer/)
3) The AppDaemon add-on for HA (found in Supervisor|AddonStore);
4) Optionally, the Samba Share SMB add-on from the same place;

Once you are happy those pre-requisites are running properly, installation is something like this:

1) Add the contents of configuration.yaml to your existing configuration.yaml;
2) Place the .py files in appdaemon/apps.  You should always have Octopus.py, to read the upcoming rates from the Octopus API, plus you may want one or both of the two switching programmes Immersion.py and Tesla.py, depending on requirements, or you might want to create others from those two;
3) Add the contents of appdaemon/appdaemon.yaml to your existing appdaemon/appdaemon.yaml, modifying to reflect which modules you are using or have created;
4) Create a directory appdaemon/logs if it's not there already;
5) Restart Home Assistant;
6) Optionally, create a new dashboard to given access to the new variables defined, so you can tweak the time window and number of slots required.
