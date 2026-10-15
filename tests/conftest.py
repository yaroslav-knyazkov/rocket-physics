"""Suite-wide test setup.

Force matplotlib's headless Agg backend before any test imports pyplot.
Only tests/test_plotting.py used to set it, so whether the rest of the
suite ran headless depended on collection order: a file run on its own
(e.g. tests/test_weight_aero_tradeoff.py) fell back to TkAgg and could
fail with `_tkinter.TclError` on this Windows machine.
"""

import matplotlib

matplotlib.use("Agg")
