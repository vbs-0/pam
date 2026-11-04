// Money arrives as integer paise. Only format at the edge; never do float maths on paise.
const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export const rupees = (paise: number) => inr.format(Math.abs(paise) / 100);
export const rupeesShort = (paise: number) => inr0.format(Math.round(Math.abs(paise) / 100));
export const inrSigned = (paise: number) => `${paise < 0 ? "−" : ""}₹${rupees(paise)}`;
export const split = (paise: number) => {
  const [r, p] = rupees(paise).split(".");
  return { r, p };
};
/** Parse what a person types into paise: "1,250.5" -> 125050. Returns null when it isn't a plain amount. */
export function toPaise(input: string): number | null {
  const s = input.replace(/[,₹\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  const [r, p = ""] = s.split(".");
  return Number(r) * 100 + Number(p.padEnd(2, "0"));
}

export const pad = (n: number) => String(n).padStart(2, "0");
export const todayIso = () => {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
export const currentMonth = () => todayIso().slice(0, 7);
export const shiftMonth = (m: string, by: number) => {
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(Date.UTC(y, mo - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthName = (m: string, short = false) => {
  const n = MONTHS[Number(m.slice(5, 7)) - 1];
  return short ? `${n.slice(0, 3)} ’${m.slice(2, 4)}` : `${n} ${m.slice(0, 4)}`;
};
export const dayLabel = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${pad(d)} ${MONTHS[m - 1].slice(0, 3)}`;
};
export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const titleCase = (code: string) => code.toLowerCase().split("_").map((w) => w[0]?.toUpperCase() + w.slice(1)).join(" ");
