#!/bin/sh
# Fetch JOLT's break library and install it on the Move.
#
# The breaks are NOT vendored in this repository, deliberately. schollz/amenbreak ships its
# code under MIT but keeps the audio in a separate release asset, compiled from an
# archive.org amen-break collection — those are samples of copyrighted recordings, and the
# MIT licence on the code does not extend to them. So PoundHard does what the reference
# project's own install.sh does: fetches them at install time. Nothing copyrighted is
# committed here.
#
# The download happens on THIS machine, not the Move. The device's busybox wget cannot
# complete GitHub's TLS redirect to its release CDN ("TLS error from peer (alert code 80)"),
# and there is no curl on it — so the Move never needs internet access at all.
#
#   ./fetch-breaks.sh [move-host]
set -e
HOST="${1:-move.local}"
DEST="/data/UserData/poundhard/breaks"
URL="https://github.com/schollz/amenbreak/releases/download/audio2/amenbreak.tar"
CACHE="${TMPDIR:-/tmp}/poundhard-amenbreak.tar"

if ssh "root@$HOST" "[ -n \"\$(ls -A $DEST 2>/dev/null)\" ]" 2>/dev/null; then
    echo "[breaks] already installed: $(ssh "root@$HOST" "find $DEST -type f | wc -l") files"
    exit 0
fi

if [ ! -s "$CACHE" ]; then
    echo "[breaks] downloading ~114 MB"
    curl -fL --progress-bar -o "$CACHE" "$URL"
fi
echo "[breaks] installing on $HOST"
ssh "root@$HOST" "mkdir -p $DEST"
# straight down the pipe: /data has room, but staging a 114 MB tar and then unpacking it
# doubles the peak usage for no reason
tar -xOf "$CACHE" 2>/dev/null >/dev/null || true
cat "$CACHE" | ssh "root@$HOST" "tar -xf - -C $DEST && chown -R ableton:users $DEST"
ssh "root@$HOST" "echo '[breaks] installed:' \$(find $DEST -type f | wc -l) 'files,' \$(du -sh $DEST | cut -f1)"
