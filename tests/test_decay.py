import math

def exponential_decay(confidence, days_since, evidence_count):
    return confidence * math.exp(-days_since / (60 * math.sqrt(max(evidence_count, 1))))

# Single observation, 30 days — should decay significantly
assert round(exponential_decay(0.9, 30, 1), 2) == 0.55, f"Got {round(exponential_decay(0.9, 30, 1), 2)}"

# Single observation, 60 days — should be very low
assert round(exponential_decay(0.9, 60, 1), 2) == 0.33, f"Got {round(exponential_decay(0.9, 60, 1), 2)}"

# 5 observations, 60 days — decays slower
assert round(exponential_decay(0.9, 60, 5), 2) == 0.58, f"Got {round(exponential_decay(0.9, 60, 5), 2)}"

# 10 observations, 90 days — still healthy
assert round(exponential_decay(0.9, 90, 10), 2) == 0.56, f"Got {round(exponential_decay(0.9, 90, 10), 2)}"

# 0 days since last seen — no decay
assert exponential_decay(0.9, 0, 1) == 0.9

# High evidence, long time — eventually decays
assert round(exponential_decay(0.9, 365, 10), 2) == 0.13, f"Got {round(exponential_decay(0.9, 365, 10), 2)}"

# Threshold test: below 0.2 should be filtered
assert exponential_decay(0.5, 120, 1) < 0.2, "Should be below threshold"

print("All decay tests passed.")
