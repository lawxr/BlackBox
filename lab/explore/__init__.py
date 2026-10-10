"""Generic exploration engines.

Each engine builds request sequences from the active profile (never from
hand-written hypotheses) and returns a list of `Observation`s. Engines do not
talk to the network themselves: they receive a `Target`, so the same engine
runs against the original (live), the in-process replica, or a fake in tests.
"""
