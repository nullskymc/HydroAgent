# HydroAgent Operating Memory

## Safety Rules
- Never start irrigation for a zone unless a structured irrigation plan exists.
- Any `start` action requires explicit approval unless it is a manual override endpoint that creates and approves a plan in the same transaction.
- Do not irrigate when weather data strongly suggests rain in the next 48 hours unless the soil moisture is in the emergency band.
- If actuator state is unknown, disabled, or already running, escalate risk and avoid automatic execution.
- If sensor data is missing or invalid, generate a hold/defer plan instead of a start plan.

## Planning Rules
- Plans are created per zone.
- Each plan must include evidence, a safety review, a recommended duration, and a risk level.
- High-risk and medium-risk start plans should request approval in chat and through the plan API.
- Hold/defer plans should still be logged for auditability, but they do not require approval.

## Approval Rules
- Approval decisions should be recorded with actor, timestamp, and optional comment.
- Rejected plans must not be executable.
- Approved plans can be executed only once unless a new plan is generated.

## Crop Defaults
- Use zone-specific thresholds when available.
- Default threshold is 40% soil moisture.
- Emergency band starts 15 percentage points below the zone threshold.
- Default irrigation duration is the zone default duration, adjusted by moisture deficit and weather risk.
