#!/usr/bin/env bash
# Download the sample photos into frontend/public/images (A-88, A-195, D-57).
#
#   cd frontend && bash scripts/fetch-photos.sh
#
# Every photo is free under the Unsplash License; source, author and licence for each
# file are in docs/PHOTO_SOURCES.md. Run it once and commit the files: the site serves
# them itself, so guests' browsers never contact Unsplash. Existing files are kept, so
# re-running only fetches what is missing.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=public/images

# file  width  images.unsplash.com photo id
PHOTOS="
hero.jpg            2400 photo-1571244007059-888ae90b5d85
estate-rows.jpg     2000 photo-1762686852371-763b689910b2
estate-cherries.jpg 2000 photo-1586095516671-d085ff58cdd4
estate-cup.jpg      2000 photo-1609088581933-e5a75a70d4a9
rooms/DLX-1.jpg     2000 photo-1781572725438-ac8c41476752
rooms/DLX-2.jpg     2000 photo-1702255489644-392758161f1f
rooms/DLX-3.jpg     2000 photo-1552558636-f6a8f071c2b3
rooms/EVR-1.jpg     2000 photo-1774311237295-a65a4c1ff38a
rooms/EVR-2.jpg     2000 photo-1718717722247-26f4c6c09192
rooms/EVR-3.jpg     2000 photo-1672219386269-486cbbe9a50f
rooms/FST-1.jpg     2000 photo-1657554378558-efc5479a9dcb
rooms/FST-2.jpg     2000 photo-1779364867798-386fb7213a2c
rooms/FST-3.jpg     2000 photo-1617325247661-675ab4b64ae2
rooms/PLV-2.jpg     2000 photo-1604882234072-d5741489e0c0
rooms/PLV-3.jpg     2000 photo-1679163818124-b43cecd1c6a2
rooms/PPV-1.jpg     2000 photo-1669279261386-6be88fb8fc65
rooms/PPV-2.jpg     2000 photo-1728051104503-e1a4a19d638c
rooms/PPV-3.jpg     2000 photo-1604578762246-41134e37f9cc
panel-account.jpg   1600 photo-1455157823797-3019317cbcf0
panel-enquire.jpg   1600 photo-1512972972907-6d71529c5e92
not-found.jpg       2000 photo-1648723352146-6028c4a7165a
"

mkdir -p "$OUT/rooms"
fetched=0
kept=0
failed=0
while read -r file width id; do
  [ -z "$file" ] && continue
  target="$OUT/$file"
  if [ -s "$target" ]; then
    kept=$((kept + 1))
    continue
  fi
  url="https://images.unsplash.com/$id?fm=jpg&q=80&w=$width&fit=max"
  if curl -fsSL --retry 3 --max-time 60 -o "$target.part" "$url" \
    && [ "$(head -c 3 "$target.part" | od -An -tx1 | tr -d ' \n')" = "ffd8ff" ]; then
    mv "$target.part" "$target"
    fetched=$((fetched + 1))
    echo "ok      $file"
  else
    rm -f "$target.part"
    failed=$((failed + 1))
    echo "FAILED  $file  ($url)" >&2
  fi
done <<< "$PHOTOS"

echo "fetched $fetched, already present $kept, failed $failed"
[ "$failed" -eq 0 ]
