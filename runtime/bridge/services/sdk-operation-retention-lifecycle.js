const DEFAULT_SWEEP_INTERVAL_MS = 60_000;

export function createSdkOperationRetentionLifecycle({
  operationAuthority,
  sweepIntervalMs = DEFAULT_SWEEP_INTERVAL_MS,
  scheduleInterval = (callback, interval) => setInterval(callback, interval),
  clearScheduledInterval = (timer) => clearInterval(timer),
  onCleanupError = () => {},
} = {}) {
  if (typeof operationAuthority?.cleanup !== "function"
    || !Number.isSafeInteger(sweepIntervalMs)
    || sweepIntervalMs < 1
    || typeof scheduleInterval !== "function"
    || typeof clearScheduledInterval !== "function"
    || typeof onCleanupError !== "function") {
    throw new TypeError("SDK operation retention lifecycle requires a valid authority and scheduler.");
  }

  let stopped = false;
  let timer = null;
  let startPromise = null;

  function report(error) {
    try { onCleanupError(error); } catch {}
  }

  function sweep() {
    if (stopped) return;
    try {
      operationAuthority.cleanup();
    } catch (error) {
      report(error);
    }
  }

  function startAfter(readiness) {
    if (startPromise) return startPromise;
    startPromise = (async () => {
      await readiness;
      if (stopped) return;
      try {
        operationAuthority.cleanup();
      } catch (error) {
        report(error);
        throw error;
      }
      if (stopped) return;
      timer = scheduleInterval(sweep, sweepIntervalMs);
      timer?.unref?.();
    })();
    return startPromise;
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    if (timer !== null) {
      clearScheduledInterval(timer);
      timer = null;
    }
  }

  return Object.freeze({ startAfter, stop });
}
