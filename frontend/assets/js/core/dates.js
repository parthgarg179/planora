/* Date helpers. Dates are passed around as 'YYYY-MM-DD' strings (same as the API). */
const pad = n => String(n).padStart(2, '0');

export const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export const toKey = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parse = k => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (k, n) => { const d = parse(k); d.setDate(d.getDate() + n); return toKey(d); };
export const dayOfWeek = k => parse(k).getDay();
export const diffDays = (a, b) => Math.round((parse(b) - parse(a)) / 864e5);
export const weekStart = k => { const d = dayOfWeek(k); return addDays(k, d === 0 ? -6 : 1 - d); };
export const fmt = (k, opts = { weekday: 'short', month: 'short', day: 'numeric' }) =>
  parse(k).toLocaleDateString('en-US', opts);

/** 1.5 → "1.5h", 0.25 → "0.25h" */
export const hrs = h => `${Math.round((h || 0) * 100) / 100}h`;
/** round to the nearest quarter hour */
export const quarter = h => Math.round(h * 4) / 4;

/** "19:00" + list of {planned_hours} → adds from/to labels in sequence */
export function timeBlocks(items, startTime = '19:00') {
  const [h, m] = startTime.split(':').map(Number);
  let t = h * 60 + m;
  const label = x => {
    const H = Math.floor(x / 60) % 24, M = x % 60;
    return `${((H + 11) % 12) + 1}${M ? ':' + pad(M) : ''} ${H >= 12 ? 'pm' : 'am'}`;
  };
  // `start` (minutes after midnight) lets blocks from different goals be sorted into one day
  return items.map(it => { const s = t; t += Math.round(it.planned_hours * 60); return { ...it, start: s, from: label(s), to: label(t) }; });
}

export const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'; };

/** true if `date` is one of the goal's available working days */
export const isWorkingDay = (goal, date) => goal.available_days.includes(dayOfWeek(date));

/** "just now", "5 min ago", "3 h ago", "2 days ago" for an ISO timestamp */
export function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? 'yesterday' : `${d} days ago`;
}
