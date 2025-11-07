# Marine Forecast Parser ??

This Python script scrapes and parses NOAA Coastal Waters Forecasts (CWF) for South Florida (Miami) and the Florida Keys.  
It outputs structured CSV files with extracted marine forecast data for newsroom and automation use.

## Features
- Automatically detects “today” or “tomorrow” forecasts based on current time
- Extracts:
  - Winds (with direction and gusts)
  - Seas (with ranges and occasional values)
  - Intracoastal/nearshore water conditions
- Flags Small Craft Advisories and Cautions
- Outputs data as a CSV for local and network use

## How to Run
1. Make sure Python 3.9+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt

## File Structure
The working directory on my system is:

C:\Users\TruVuAdmin\Documents\Python_Projects\
+-- src\
¦   +-- marine_forecast.py
¦   +-- utils\
¦   +-- data\
¦       +-- output\
¦           +-- marine_forecast.csv

For GitHub, only the main script and dependency files are included.

