#!/usr/bin/env bash
# Stop only orphaned/in-flight lecture H.264 normalization jobs on the API host.
#
# Usage:
#   bash deploy/aws/fail-stuck-video-transcodes.sh --confirm
#
# The lecture row is created only after transcoding completes, so stopping one
# of these processes makes its request fail without changing persisted lectures.
set -Eeuo pipefail

# The final output path is `/tmp/<source>-h264-<random>.mp4`; `-h264-` is
# part of that path rather than a standalone argument.
readonly target_pattern='/usr/bin/ffmpeg .* -i /tmp/.*\.upload\.mp4 .* /tmp/.*-h264-.*\.mp4'

find_target_pids() {
  pgrep -f -- "$target_pattern" || true
}

is_target_process() {
  local pid="$1"
  local command

  command="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$command" =~ $target_pattern ]]
}

mapfile -t target_pids < <(find_target_pids)

if (( ${#target_pids[@]} == 0 )); then
  echo 'No in-flight lecture H.264 transcodes found.'
  exit 0
fi

echo 'Target lecture transcodes:'
ps -fp "${target_pids[@]}"

if [[ "${1:-}" != '--confirm' ]]; then
  echo
  echo 'Dry run only. Re-run with --confirm to mark these uploads as failed.'
  exit 2
fi

for pid in "${target_pids[@]}"; do
  if is_target_process "$pid"; then
    kill -TERM "$pid"
  fi
done

for _ in {1..10}; do
  sleep 1
  mapfile -t remaining_pids < <(find_target_pids)
  if (( ${#remaining_pids[@]} == 0 )); then
    echo 'All targeted transcodes stopped.'
    exit 0
  fi
done

echo 'Force-stopping transcodes that did not exit after 10 seconds:'
ps -fp "${remaining_pids[@]}"
for pid in "${remaining_pids[@]}"; do
  if is_target_process "$pid"; then
    kill -KILL "$pid"
  fi
done

echo 'Targeted transcodes were stopped and their uploads are failed.'
