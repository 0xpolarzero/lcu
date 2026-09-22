# Retry removal of disposable Electron fixture directories. Electron may still
# flush profile files briefly after its main process exits.
cleanup_fixture() {
  local fixture=$1 attempt
  for attempt in {1..20}; do
    if [[ ! -e $fixture ]]; then
      return 0
    fi
    if rm -rf -- "$fixture"; then
      return 0
    fi
    sleep 0.1
  done
  printf 'Failed to remove test fixture after 20 attempts: %s\n' "$fixture" >&2
  return 1
}

trap_fixture_cleanup() {
  local status=$?
  local fixture=$1 cleanup_status
  trap - EXIT
  if cleanup_fixture "$fixture"; then
    cleanup_status=0
  else
    cleanup_status=$?
  fi
  if (( status != 0 )); then
    exit "$status"
  fi
  exit "$cleanup_status"
}
