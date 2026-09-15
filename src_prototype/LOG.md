# Log

**Screen recording:** _[link pending — needs to be recorded and added by
the user; I can't operate screen recording]_

**GitHub repo:** _[link pending — needs the user's go-ahead before
pushing anything public]_

## Which mission/rule section, and why

The rear LED indicator rule: red = autonomous, blue = teleoperation,
flashing green = arrived at a target. Picked it because it's a small,
fully-specified, testable rule (three exact states, an exact trigger for
each) that maps directly onto one ROS topic already defined in this
workspace (`RoverStatus.mode` + `RoverStatus.leg_reached`), so it could be
built and demoed end-to-end without inventing new interfaces.

## What data was shown vs. left out, and why

Shown: mode (drives the steady color) and `leg_reached` (drives the
flash) — the only two fields the rule actually depends on. Everything
else `RoverStatus` carries (battery %, distance/bearing to goal, ArUco
visibility, `state_text`) was left out: none of it changes what the LED
should display, and the brief asked for the minimum program to satisfy
the stated requirements, not a full telemetry dashboard.

## Handling a topic going silent

Currently: silently. If `/rover/status` stops publishing, the LED just
freezes on its last color — there's no watchdog/staleness check in this
minimal version. That's a known gap, not an oversight: `src_dev/lesson_07`
already built the fix for this exact failure mode (a `fresh`/`stale`/`lost`
classifier with an injectable clock), left out here only because it isn't
one of the three stated requirements and the instruction was to add
nothing beyond them.

## What competition-rule wording shaped a design decision

"Visible in bright daylight" is a hardware spec (LED brightness), not
software's problem to solve — but it implies the state has to be
unambiguous at a glance, which is why flashing green uses a hard on/off
color swap (not a fade or a subtler cue) and why the three states use
maximally distinct hues rather than a shared palette.

## What would break first over a real lossy link

`/rover/status` is published as plain `10`-depth here (i.e. effectively
reliable, unlike the BEST_EFFORT telemetry QoS used elsewhere in this
project — see `src_dev/lesson_02`). Over a lossy radio link that's the
first thing to break: a reliable publisher will keep queuing and
retrying stale frames instead of dropping them, so the LED could lag
behind the rover's actual state rather than show "no data." Second: with
no staleness detection (see above), a dropped link wouldn't be
distinguishable from a rover that's simply still in its last reported
mode — exactly the "stale rendered as fresh" failure `lesson_07` exists
to prevent.
