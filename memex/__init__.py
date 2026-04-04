import warnings

# instructor eagerly imports all provider clients at startup, including Google's
# deprecated generativeai package which emits a noisy FutureWarning. We only
# use the Anthropic provider — suppress the irrelevant noise package-wide.
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"instructor\.providers\.gemini",
)
