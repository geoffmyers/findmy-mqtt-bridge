#!/bin/bash
# Read-only precheck to plan SIP+AMFI disable on the dockur/macos guest:
# is there a Recovery volume, what does NVRAM look like, is a toolchain present
# to build the entitled key extractor?
echo "== csrutil / SIP =="; csrutil status 2>&1
echo; echo "== current NVRAM csr/boot-args =="
nvram -p 2>/dev/null | grep -iE "csr-active-config|boot-args|SystemAudioVolume" || echo "(none set)"
echo; echo "== APFS volumes — is there a Recovery volume to boot? =="
diskutil list 2>&1 | grep -iE "Recovery|Macintosh|Container|APFS|Volume" | head -30
echo; echo "== apfs recovery boot support =="
diskutil apfs list 2>/dev/null | grep -iE "Recovery|Volume Name|Roles" | head -20
echo; echo "== toolchain for building the entitled extractor =="
for t in swiftc clang codesign xcrun security; do
  p=$(command -v $t 2>/dev/null); echo "  $t: ${p:-MISSING}"
done
xcode-select -p 2>&1
echo; echo "== is FindMy's entitled agent running (lldb target on SIP-off)? =="
ps ax -o pid,comm 2>/dev/null | grep -iE "[f]indmydeviced|[f]indmylocateagent|[s]earchpartyd" || echo "(none)"
echo "== DONE =="
