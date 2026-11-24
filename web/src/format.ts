const number = new Intl.NumberFormat("en-US");
const day = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const clock = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  hourCycle: "h23",
});

export const formatNumber = (value: number) => number.format(value);
export const formatPoolDay = (value: string) =>
  day.format(new Date(value + "T00:00:00Z")) + " (UTC)";
export const formatClock = (value: string) => clock.format(new Date(value)) + " UTC";
