# Demo drill: surviving GitHub, registry or Docker failures

Do all of this on the demo machine and on the backup machine, while online, the day before.

## 1. Warm everything (online)
```bash
python scripts/build_images.py      # sandbox image (pinned by digest in docker/images.lock.json)
python scripts/warm_caches.py       # local git mirrors of every fixture state + every fixture world built offline
python tools/fl.py up               # then run one full analysis so records and caches exist
python scripts/export_replay.py     # REPLAY pack: recorded evidence only (var/replay)
```

## 2. Three rehearsals
| Run | How | What the screen must say |
|---|---|---|
| Normal | online, `python tools/fl.py up` | the mode badge you claim (LIVE or REPRODUCIBLE FIXTURE) |
| Network off | disconnect the network, ingest from `var/mirror/<scenario>_<repo>` (same pinned commits, same sandboxed fetch), wheels come from the warm wheelhouse volume | REPRODUCIBLE FIXTURE; say "network is off" |
| Docker off | quit Docker Desktop, start the REPLAY pack below | RECORDED; Re-run is disabled |

## 3. REPLAY pack
```bash
FAULTLINE_MODE=REPLAY FAULTLINE_DB=var/replay/faultline.db FAULTLINE_STORE=var/replay/store \
  python -m uvicorn faultline.api.main:app_factory --factory --port 8001
```
REPLAY mode needs no Docker and no network, refuses every action that would start work, and shows the mode stored with each record
(a request cannot change it; this is tested in `tests/integration/test_replay_mode.py`).

## 4. Record what you did
Append the outcome of each rehearsal with `python tools/track.py note "..."` so TC-12.2.1 and TC-12.2.2 have evidence.
