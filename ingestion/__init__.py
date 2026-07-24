"""PRISM ingestion package — pluggable sensor data drivers.

F4: Define the SensorDriver protocol and Reading dataclass.
F6: ReplayDriver and ScenarioEngine for historical replay and fault injection.
Drivers implement SensorDriver; the pipeline normalizes and persists.
"""
