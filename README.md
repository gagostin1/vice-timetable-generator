# VICE Timetable Generator

A Python utility for generating VICE-compatible airport timetables from historical flight schedule datasets.

## Current Status

Early development / v0.1.

The tool currently:
- Reads quarterly Parquet flight data
- Filters traffic for a selected airport and date
- Converts UTC timestamps to local airport time
- Removes ambiguous or invalid airport records
- Generates a VICE-compatible timetable CSV
- Supports basic cargo classification

## Output Format

VICE timetable files use:

callsign,origin,destination,aircraft_type,time,cargo

Example:

AAL1234,KCLT,KDFW,A321,08:14,false

## Data Source

Built for use with the aircraft-flight-schedules dataset published by MrAirspace.

## Requirements

Python 3.11+ recommended.

Install dependencies with:

pip install -r requirements.txt