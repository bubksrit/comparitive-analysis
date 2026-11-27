export function formatPolicyTimingMilliseconds(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) {
    return "Unavailable";
  }
  if (seconds === 0) {
    return "0 ms";
  }

  const milliseconds = seconds * 1000;
  if (Math.abs(milliseconds) < 0.0000005) {
    return "<0.000001 ms";
  }

  const formatted = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 6,
  }).format(milliseconds);
  return `${formatted} ms`;
}
