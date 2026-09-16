#!/bin/bash
# Investigate what makes FindMy.app refresh the cache more often, WITHOUT the
# flaky System Events UI scripting (which times out headless). Compares idle vs
# "kept foreground + App Nap off + display awake". Runs ON the guest.
set +e
D="$HOME/Library/Caches/com.apple.findmy.fmipcore/Devices.data"
mt() { stat -f '%m' "$D" 2>/dev/null; }
watch() {  # $1=label $2=seconds $3=foreground(1/0)
  local label="$1" secs="$2" fg="$3" last now changes=0 t=0
  last=$(mt)
  while [ $t -lt "$secs" ]; do
    [ "$fg" = "1" ] && open -a FindMy >/dev/null 2>&1
    sleep 10; t=$((t+10)); now=$(mt)
    if [ "$now" != "$last" ]; then changes=$((changes+1)); echo "  [$label +${t}s] cache updated (mtime=$now)"; last=$now; fi
  done
  echo "  $label: $changes update(s) in ${secs}s"
}

echo "===== setup ====="
echo "App Nap before: $(defaults read com.apple.findmy NSAppSleepDisabled 2>/dev/null || echo unset)"
defaults write com.apple.findmy NSAppSleepDisabled -bool YES && echo "App Nap: disabled for FindMy"
# relaunch FindMy so the pref takes effect + keep display/system awake for the test
osascript -e 'quit app "FindMy"' >/dev/null 2>&1; sleep 3; open -a FindMy; sleep 6
caffeinate -dis -t 320 >/dev/null 2>&1 &
CAF=$!

echo; echo "===== PHASE A: idle (FindMy not re-foregrounded), 120s ====="
watch idle 120 0

echo; echo "===== PHASE B: kept foreground (open -a FindMy every 10s) + AppNap off, 120s ====="
watch foreground 120 1

kill "$CAF" 2>/dev/null
echo "===== DONE ====="
