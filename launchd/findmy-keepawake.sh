#!/bin/bash
# Keep Find My actively fetching on the headless VM — STALENESS-BASED recovery.
#
# FindMy.app wedges (stops fetching entirely) after a while, even foreground.
# A hung instance can't be revived by `open -a` or `osascript quit` (the latter
# HANGS headless) — only a hard `pkill -9` + relaunch spawns a fresh, actively-
# fetching instance. FindMy fetches fine on the headless display as long as it's
# a *fresh* instance (verified: 11 cache updates / 300s, self-recovering, with no
# display keep-alive beyond `caffeinate -d`), so the un-wedge is what matters —
# NOT any mouse-jiggle / display-power trick. This agent watches the cache mtime
# and only relaunches when it goes stale (FindMy wedged) or FindMy died. Checking
# mtime (vs a blind timer) leaves a healthy FindMy alone → far fewer relaunches,
# no window-stealing while you're on VNC, and recovery within one check interval.
#
# Run under a KeepAlive LaunchAgent. Tunables (env overrides): the cache normally
# refreshes every ~15–30s while FindMy is healthy, so STALE_AFTER=60 flags a real
# wedge without false positives; worst-case staleness ≈ STALE_AFTER + CHECK_EVERY
# + relaunch spin-up (~90s).
CHECK_EVERY="${FINDMY_CHECK_SECONDS:-15}"
STALE_AFTER="${FINDMY_STALE_SECONDS:-60}"
CACHE="$HOME/Library/Caches/com.apple.findmy.fmipcore"

newest_age() {  # seconds since the most-recently-written cache file (999999 if none)
  local now newest=0 m
  now=$(date +%s)
  for f in Devices Items FamilyMembers; do
    m=$(stat -f '%m' "$CACHE/$f.data" 2>/dev/null) || continue
    [ "$m" -gt "$newest" ] && newest=$m
  done
  [ "$newest" -eq 0 ] && { echo 999999; return; }
  echo $(( now - newest ))
}

relaunch() {
  /usr/bin/pkill -9 -x FindMy 2>/dev/null
  /usr/bin/pkill -9 -f 'FindMy.app/Contents/MacOS/FindMy' 2>/dev/null
  sleep 3
  /usr/bin/open -a FindMy >/dev/null 2>&1
  sleep 8   # give the fresh instance a moment to start fetching before re-checking
}

/usr/bin/caffeinate -dis &
/usr/bin/open -a FindMy >/dev/null 2>&1   # ensure it's up at start
while true; do
  sleep "$CHECK_EVERY"
  if ! /usr/bin/pgrep -x FindMy >/dev/null 2>&1; then
    relaunch                              # FindMy not running → start it
  elif [ "$(newest_age)" -gt "$STALE_AFTER" ]; then
    relaunch                              # cache stale → FindMy wedged, kick it
  fi
done
