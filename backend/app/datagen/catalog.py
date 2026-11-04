"""Reference data for the synthetic Indian ledger.

Merchant brand names, bank codes, cities and holiday dates are public facts used descriptively; every person,
account, UPI id and amount generated from this catalogue is synthetic. Merchant UPI ids carry a ``-mrch``
suffix so they cannot be mistaken for real handles.
"""
from dataclasses import dataclass, field
from datetime import date

D0 = date(2020, 1, 1)


@dataclass(frozen=True)
class CategoryDef:
    code: str
    name: str
    group: str
    kind: str
    effective_from: date = D0
    effective_to: date | None = None
    replaced_by: str | None = None


CATEGORIES = [
    CategoryDef("SALARY", "Salary & Pension", "INCOME", "INCOME"),
    CategoryDef("INTEREST", "Interest", "INCOME", "INCOME"),
    CategoryDef("OTHER_INCOME", "Other Income", "INCOME", "INCOME"),
    CategoryDef("RENT", "Rent", "ESSENTIALS", "EXPENSE"),
    CategoryDef("GROCERIES", "Groceries", "ESSENTIALS", "EXPENSE"),
    CategoryDef("UTILITIES", "Utilities & Bills", "ESSENTIALS", "EXPENSE"),
    CategoryDef("FUEL", "Fuel", "ESSENTIALS", "EXPENSE"),
    CategoryDef("TRANSPORT", "Transport", "ESSENTIALS", "EXPENSE"),
    CategoryDef("HEALTH", "Health & Pharmacy", "ESSENTIALS", "EXPENSE"),
    CategoryDef("EDUCATION", "Education", "ESSENTIALS", "EXPENSE"),
    CategoryDef("INSURANCE", "Insurance", "ESSENTIALS", "EXPENSE"),
    CategoryDef("EMI_LOANS", "EMI & Loans", "ESSENTIALS", "EXPENSE"),
    CategoryDef("FOOD_DINING", "Food & Dining", "LIFESTYLE", "EXPENSE"),
    CategoryDef("SHOPPING", "Shopping", "LIFESTYLE", "EXPENSE"),
    CategoryDef("ENTERTAINMENT", "Entertainment", "LIFESTYLE", "EXPENSE"),
    CategoryDef("SUBSCRIPTIONS", "Subscriptions", "LIFESTYLE", "EXPENSE"),
    CategoryDef("TRAVEL", "Travel", "LIFESTYLE", "EXPENSE"),
    CategoryDef("PERSONAL_CARE", "Personal Care", "LIFESTYLE", "EXPENSE"),
    CategoryDef("CASH_WITHDRAWAL", "Cash Withdrawal", "OTHER", "EXPENSE"),
    CategoryDef("UNCATEGORIZED", "Uncategorized", "OTHER", "UNKNOWN"),
    CategoryDef("SELF_TRANSFER", "Self Transfer", "FINANCIAL", "TRANSFER"),
    CategoryDef("CC_BILL_PAYMENT", "Credit Card Bill Payment", "FINANCIAL", "TRANSFER"),
    CategoryDef("DINING_OUT", "Dining Out (retired)", "LIFESTYLE", "EXPENSE", D0, date(2025, 12, 31), "FOOD_DINING"),
    CategoryDef("MOBILE_RECHARGE", "Mobile Recharge (retired)", "ESSENTIALS", "EXPENSE", D0, date(2025, 12, 31),
                "UTILITIES"),
]
CATEGORY_BY_CODE = {c.code: c for c in CATEGORIES}
SYNONYMS = {"FOOD_AND_DINING": "FOOD_DINING", "GROCERY": "GROCERIES", "BILLS": "UTILITIES",
            "SUBSCRIPTION": "SUBSCRIPTIONS", "MEDICAL": "HEALTH"}
UNKNOWN_BUDGET_CODES = ["GYM_FITNESS", "PETS", "MISC_SPEND"]
REMAP_VARIANTS = {"FOOD_DINING": ["DINING_OUT", "FOOD_AND_DINING", "food_dining"],
                  "GROCERIES": ["groceries", "GROCERY"], "UTILITIES": ["MOBILE_RECHARGE", "BILLS"]}


@dataclass(frozen=True)
class MerchantDef:
    merchant_id: str
    name: str
    category: str
    aliases: tuple[str, ...]
    vpa: str | None
    online: bool
    mean_rupees: int
    sigma: float = 0.45
    extra_categories: tuple[str, ...] = ()
    refinements: tuple[tuple[str, str], ...] = field(default=())  # (regex, category) checked before default


_HANDLES = ["ybl", "axl", "icici", "hdfcbank", "paytm"]


def _m(i, name, cat, aliases, online, mean, *, vpa=True, extra=(), refine=(), sigma=0.45) -> MerchantDef:
    slug = aliases[0].replace(" ", "")
    return MerchantDef(f"MER-{i:04d}", name, cat, tuple(aliases),
                       f"{slug}-mrch@{_HANDLES[i % len(_HANDLES)]}" if vpa else None,
                       online, mean, sigma, tuple(extra), tuple(refine))


MERCHANTS = [
    _m(1, "Swiggy", "FOOD_DINING", ["swiggy", "swiggy instamart", "swigy", "bundl technologies"], True, 420,
       extra=["GROCERIES"], refine=[(r"instamart", "GROCERIES")]),
    _m(2, "Zomato", "FOOD_DINING", ["zomato", "zomato order", "zomato ltd"], True, 450),
    _m(3, "Domino's", "FOOD_DINING", ["dominos", "jubilant foodworks"], True, 520),
    _m(4, "McDonald's", "FOOD_DINING", ["mcdonalds", "hardcastle restaurants"], False, 380),
    _m(5, "Starbucks", "FOOD_DINING", ["starbucks", "tata starbucks"], False, 450),
    _m(6, "Haldiram's", "FOOD_DINING", ["haldirams", "haldiram snacks"], False, 350),
    _m(7, "BigBasket", "GROCERIES", ["bigbasket", "bb now", "supermarket grocery supplies"], True, 1400),
    _m(8, "Blinkit", "GROCERIES", ["blinkit", "grofers"], True, 650),
    _m(9, "Zepto", "GROCERIES", ["zepto", "kiranakart"], True, 600),
    _m(10, "DMart", "GROCERIES", ["dmart", "avenue supermarts"], False, 1900),
    _m(11, "Reliance Retail", "GROCERIES", ["reliance fresh", "reliance smart", "reliance digital",
                                           "reliance retail"], False, 1500,
       extra=["SHOPPING"], refine=[(r"reliance digital", "SHOPPING")]),
    _m(12, "More Supermarket", "GROCERIES", ["more supermarket", "more retail"], False, 1100),
    _m(13, "Amazon", "SHOPPING", ["amazon", "amazon pay", "amzn mktp", "amazon fresh", "amazon prime"], True, 1300,
       extra=["GROCERIES", "SUBSCRIPTIONS"],
       refine=[(r"amazon fresh", "GROCERIES"), (r"amazon prime", "SUBSCRIPTIONS")]),
    _m(14, "Flipkart", "SHOPPING", ["flipkart", "flipkart internet", "fkrt"], True, 1600),
    _m(15, "Myntra", "SHOPPING", ["myntra", "myntra designs"], True, 1400),
    _m(16, "Ajio", "SHOPPING", ["ajio", "ajio reliance"], True, 1300),
    _m(17, "Croma", "SHOPPING", ["croma", "infiniti retail"], False, 6500, sigma=0.8),
    _m(18, "Decathlon", "SHOPPING", ["decathlon", "decathlon sports"], False, 2200),
    _m(19, "IKEA", "SHOPPING", ["ikea", "ikea india"], False, 3500),
    _m(20, "Uber", "TRANSPORT", ["uber", "uber india", "uber trip"], True, 280),
    _m(21, "Ola", "TRANSPORT", ["ola", "ani technologies", "olacabs"], True, 260),
    _m(22, "Rapido", "TRANSPORT", ["rapido", "roppen transportation"], True, 120),
    _m(23, "Metro Rail", "TRANSPORT", ["metro rail", "bmrcl", "dmrc"], False, 60),
    _m(24, "FASTag", "TRANSPORT", ["fastag", "netc fastag"], False, 400),
    _m(25, "Indian Oil", "FUEL", ["indian oil", "iocl"], False, 1800),
    _m(26, "HPCL", "FUEL", ["hpcl", "hindustan petroleum"], False, 1800),
    _m(27, "BPCL", "FUEL", ["bpcl", "bharat petroleum"], False, 1800),
    _m(28, "BESCOM", "UTILITIES", ["bescom", "bangalore electricity"], False, 1600),
    _m(29, "MSEDCL", "UTILITIES", ["msedcl", "mahavitaran"], False, 1600),
    _m(30, "BSES", "UTILITIES", ["bses", "bses rajdhani"], False, 1700),
    _m(31, "TGSPDCL", "UTILITIES", ["tgspdcl", "tsspdcl"], False, 1400),
    _m(32, "TANGEDCO", "UTILITIES", ["tangedco", "tneb"], False, 1300),
    _m(33, "Tata Power", "UTILITIES", ["tata power", "tata power ddl"], False, 1500),
    _m(34, "Airtel", "UTILITIES", ["airtel", "bharti airtel", "airtel xstream"], True, 450),
    _m(35, "Jio", "UTILITIES", ["jio", "reliance jio", "jio prepaid"], True, 330),
    _m(36, "Vi", "UTILITIES", ["vodafone idea", "vi prepaid"], True, 320),
    _m(37, "ACT Fibernet", "UTILITIES", ["act fibernet", "atria convergence"], True, 900),
    _m(38, "Tata Play", "UTILITIES", ["tata play", "tata sky"], True, 380),
    _m(39, "Apollo Pharmacy", "HEALTH", ["apollo pharmacy", "apollo health"], False, 650),
    _m(40, "PharmEasy", "HEALTH", ["pharmeasy", "axelia solutions"], True, 800),
    _m(41, "Tata 1mg", "HEALTH", ["tata 1mg", "1mg technologies"], True, 700),
    _m(42, "Practo", "HEALTH", ["practo", "practo technologies"], True, 600),
    _m(43, "Unacademy", "EDUCATION", ["unacademy", "sorting hat"], True, 2500),
    _m(44, "Coursera", "EDUCATION", ["coursera", "coursera inc"], True, 3500),
    _m(45, "LIC", "INSURANCE", ["lic of india", "life insurance corp"], False, 12000, sigma=0.6),
    _m(46, "Star Health", "INSURANCE", ["star health", "star health insurance"], True, 9000, sigma=0.6),
    _m(47, "Bajaj Finance", "EMI_LOANS", ["bajaj finance", "bajaj finserv"], False, 6000, vpa=False),
    _m(48, "HDFC Loans", "EMI_LOANS", ["hdfc bank loan", "hdfc ltd emi"], False, 9000, vpa=False),
    _m(49, "BookMyShow", "ENTERTAINMENT", ["bookmyshow", "bigtree entertainment"], True, 650),
    _m(50, "PVR INOX", "ENTERTAINMENT", ["pvr inox", "pvr cinemas"], False, 700),
    _m(51, "Netflix", "SUBSCRIPTIONS", ["netflix", "netflix com"], True, 499),
    _m(52, "Spotify", "SUBSCRIPTIONS", ["spotify", "spotify india"], True, 119),
    _m(53, "Disney+ Hotstar", "SUBSCRIPTIONS", ["hotstar", "disney hotstar", "novi digital"], True, 299),
    _m(54, "YouTube Premium", "SUBSCRIPTIONS", ["youtube premium", "google youtube"], True, 129),
    _m(55, "Google One", "SUBSCRIPTIONS", ["google one", "google storage"], True, 130),
    _m(56, "Cult.fit", "SUBSCRIPTIONS", ["cult fit", "curefit"], True, 999),
    _m(57, "IRCTC", "TRAVEL", ["irctc", "irctc ticketing"], True, 1400, sigma=0.7),
    _m(58, "IndiGo", "TRAVEL", ["indigo", "interglobe aviation"], True, 6500, sigma=0.6),
    _m(59, "MakeMyTrip", "TRAVEL", ["makemytrip", "mmt"], True, 7000, sigma=0.7),
    _m(60, "OYO", "TRAVEL", ["oyo", "oravel stays"], True, 2500),
    _m(61, "RedBus", "TRAVEL", ["redbus", "redbus in"], True, 900),
    _m(62, "Urban Company", "PERSONAL_CARE", ["urban company", "urbanclap"], True, 900),
    _m(63, "Nykaa", "PERSONAL_CARE", ["nykaa", "fsn ecommerce"], True, 1100, extra=["SHOPPING"]),
    _m(64, "CRED", "CC_BILL_PAYMENT", ["cred", "cred club", "dreamplug"], True, 0),
    # bare "tata" is ambiguous; longer aliases (tata power / play / 1mg / starbucks) win by longest match
    _m(65, "Tata Group", "SHOPPING", ["tata cliq", "tata neu", "tata"], True, 1500, extra=["UTILITIES", "HEALTH"]),
]
MERCHANT_BY_ID = {m.merchant_id: m for m in MERCHANTS}
CRED_ID = "MER-0064"

# Local shops that are NOT in the merchant master. The suffix decides the true category; "ENTERPRISES" and
# "TRADERS" are genuinely ambiguous (their true category varies), so no rule can be right every time.
LONG_TAIL_PREFIXES = ["SRI LAKSHMI", "NEW BALAJI", "OM SAI", "ANNAPOORNA", "SHREE GANESH", "RAJ", "MAA DURGA",
                      "SAI KRISHNA", "JAI HIND", "ROYAL", "GREEN LEAF", "SUNRISE", "VINAYAKA", "STAR"]
LONG_TAIL = [("PROVISION STORES", ["GROCERIES"]), ("KIRANA", ["GROCERIES"]), ("SUPER MART", ["GROCERIES"]),
             ("HOTEL", ["FOOD_DINING"]), ("CAFE", ["FOOD_DINING"]), ("BHAVAN", ["FOOD_DINING"]),
             ("MEDICALS", ["HEALTH"]), ("PHARMA", ["HEALTH"]), ("FUEL STATION", ["FUEL"]),
             ("SALON", ["PERSONAL_CARE"]), ("ENTERPRISES", ["SHOPPING", "GROCERIES", "HEALTH"]),
             ("TRADERS", ["SHOPPING", "GROCERIES"])]

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan", "Karthik",
               "Ananya", "Diya", "Saanvi", "Aadhya", "Pari", "Priya", "Lakshmi", "Meera", "Kavya", "Fatima",
               "Imran", "Joseph", "Gurpreet", "Harini", "Nikhil", "Pooja", "Rahul", "Sneha", "Vikram", "Zoya"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Patel", "Gupta", "Singh", "Khan", "Das",
              "Banerjee", "Mehta", "Rao", "Menon", "Joshi", "Kulkarni", "Pillai", "Chopra", "Fernandes", "Sheikh"]
CITIES = [("Bengaluru", "KA", 1), ("Mumbai", "MH", 1), ("Delhi", "DL", 1), ("Hyderabad", "TG", 1),
          ("Chennai", "TN", 1), ("Pune", "MH", 1), ("Kolkata", "WB", 1), ("Ahmedabad", "GJ", 1),
          ("Jaipur", "RJ", 2), ("Lucknow", "UP", 2), ("Kochi", "KL", 2), ("Indore", "MP", 2),
          ("Coimbatore", "TN", 2), ("Bhubaneswar", "OD", 2), ("Nagpur", "MH", 2), ("Guwahati", "AS", 2),
          ("Chandigarh", "CH", 2), ("Patna", "BR", 2), ("Mysuru", "KA", 3), ("Vijayawada", "AP", 3)]
BANKS = [("SBIN", "SBI", "oksbi"), ("HDFC", "HDFC BANK", "okhdfcbank"), ("ICIC", "ICICI BANK", "okicici"),
         ("UTIB", "AXIS BANK", "okaxis"), ("KKBK", "KOTAK BANK", "kotak"), ("BARB", "BANK OF BARODA", "barodampay"),
         ("PUNB", "PNB", "pnb"), ("CNRB", "CANARA BANK", "cnrb")]
BANK_BY_CODE = {b[0]: b for b in BANKS}
EMPLOYERS = ["ACME TECHNOLOGIES PVT LTD", "BLUEWAVE SOFTWARE LLP", "SUNRISE TEXTILES LTD", "NOVA FINSERV PVT LTD",
             "GREENFIELD HOSPITALS", "ORBIT LOGISTICS PVT LTD", "VEDA PHARMA LTD", "KITE EDUTECH PVT LTD"]
CLIENTS = ["ZEN DESIGN STUDIO", "PRIME BUILDERS", "METRO TRADING CO", "APEX CONSULTANTS", "LOTUS EVENTS",
           "NORTHSTAR EXPORTS", "COASTAL FOODS", "BRIGHT MINDS ACADEMY"]
UTILITY_BY_STATE = {"KA": "MER-0028", "MH": "MER-0029", "DL": "MER-0030", "TG": "MER-0031", "TN": "MER-0032"}
DEFAULT_UTILITY = "MER-0033"
BROADBAND = ["MER-0037", "MER-0034"]
MOBILE = [("MER-0035", 29900), ("MER-0034", 34900), ("MER-0036", 29900)]   # 28-day packs, paise
DTH = "MER-0038"
LENDERS = ["MER-0047", "MER-0048"]
# (merchant_id, monthly price in paise); the last entry is Amazon Prime billed monthly
SUBSCRIPTIONS = [("MER-0051", 49900), ("MER-0052", 11900), ("MER-0053", 29900), ("MER-0054", 12900),
                 ("MER-0055", 13000), ("MER-0056", 99900), ("MER-0013", 29900)]
# National fixed-date bank holidays 2026 (Sundays and 2nd/4th Saturdays are handled in calendar.py)
HOLIDAYS_2026 = {date(2026, 1, 26), date(2026, 5, 1), date(2026, 8, 15), date(2026, 10, 2), date(2026, 12, 25)}

SEASONALITY = {  # Jan..Dec frequency multipliers
    "SHOPPING": [0.9, 0.85, 0.95, 0.9, 0.95, 0.9, 0.95, 1.0, 1.1, 1.6, 1.7, 1.2],   # Diwali Oct-Nov
    "TRAVEL": [1.0, 0.9, 0.9, 1.2, 1.5, 1.3, 0.8, 0.8, 0.9, 1.2, 1.3, 1.6],         # summer + year-end
    "FOOD_DINING": [1.0, 0.95, 1.0, 1.0, 1.0, 1.05, 1.1, 1.05, 1.0, 1.15, 1.2, 1.3],
    "GROCERIES": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.15, 1.15, 1.05],
    "UTILITIES": [0.9, 0.9, 1.1, 1.4, 1.5, 1.3, 1.0, 1.0, 1.0, 0.95, 0.9, 0.9],    # summer AC load
    "EDUCATION": [0.4, 0.4, 0.6, 2.5, 0.8, 2.5, 1.2, 0.5, 0.4, 0.4, 0.4, 0.4],     # Apr/Jun fees
    "HEALTH": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.25, 1.2, 1.0, 1.0, 1.0],         # monsoon
    "ENTERTAINMENT": [1.0, 1.0, 1.0, 1.0, 1.1, 1.0, 0.9, 0.9, 1.0, 1.1, 1.1, 1.3],
}
PERSONA_WEIGHTS = {
    "SALARIED": {"FOOD_DINING": .22, "GROCERIES": .20, "SHOPPING": .12, "TRANSPORT": .12, "FUEL": .06,
                 "HEALTH": .05, "ENTERTAINMENT": .05, "PERSONAL_CARE": .03, "TRAVEL": .03, "EDUCATION": .02,
                 "CASH_WITHDRAWAL": .04, "LONG_TAIL": .06},
    "SELF_EMPLOYED": {"FOOD_DINING": .18, "GROCERIES": .22, "SHOPPING": .12, "TRANSPORT": .10, "FUEL": .09,
                      "HEALTH": .05, "ENTERTAINMENT": .04, "PERSONAL_CARE": .03, "TRAVEL": .04, "EDUCATION": .02,
                      "CASH_WITHDRAWAL": .05, "LONG_TAIL": .06},
    "RETIRED": {"FOOD_DINING": .08, "GROCERIES": .30, "SHOPPING": .08, "TRANSPORT": .08, "FUEL": .03,
                "HEALTH": .18, "ENTERTAINMENT": .04, "PERSONAL_CARE": .03, "TRAVEL": .05, "EDUCATION": .00,
                "CASH_WITHDRAWAL": .07, "LONG_TAIL": .06},
}


def seed_rules() -> list[dict]:
    """Version-1 rules. Priority: 5 system keywords, 10 merchant refinements, 50 merchant defaults,
    60 contextual keywords, 90 long-tail keywords, 95 credit fallbacks."""
    rows: list[dict] = []

    def add(priority, category, *, merchant=None, pattern=None, channel=None, direction="ANY",
            account_type=None, confidence=0.95, note=""):
        rows.append({"rule_id": f"RUL-{len(rows) + 1:04d}", "version": 1, "priority": priority,
                     "category_code": category, "merchant_id": merchant, "pattern": pattern, "channel": channel,
                     "direction": direction, "account_type": account_type, "confidence": confidence,
                     "note": note})

    add(5, "SALARY", pattern=r"\b(salary|sal|pension)\b", direction="CR", note="payroll or pension credit")
    add(5, "INTEREST", pattern=r"\bint\.?pd\b|\binterest\b", direction="CR", note="savings interest")
    add(5, "CC_BILL_PAYMENT", pattern=r"payment received", direction="CR", account_type="CREDIT_CARD",
        note="card bill credited on the card account")
    add(5, "CC_BILL_PAYMENT", pattern=r"\bcc bill\b|credit card bill", direction="DR", note="card bill paid")
    add(5, "SELF_TRANSFER", pattern=r"\bself\b", note="explicit self transfer")
    add(6, "CASH_WITHDRAWAL", channel="ATM", note="ATM withdrawal")
    add(6, "EMI_LOANS", channel="NACH", pattern=r"\bemi\b|\bloan\b", direction="DR", note="NACH loan debit")
    for m in MERCHANTS:
        for rx, cat in m.refinements:
            add(10, cat, merchant=m.merchant_id, pattern=rx, confidence=0.9, note=f"{m.name} refinement")
    for m in MERCHANTS:
        add(50, m.category, merchant=m.merchant_id, confidence=0.8 if m.extra_categories else 0.95,
            note=f"{m.name} default")
    add(60, "RENT", pattern=r"\brent\b", channel="UPI", direction="DR", confidence=0.85, note="UPI note says rent")
    for suffix, cats in LONG_TAIL:
        if len(cats) == 1:
            add(90, cats[0], pattern=rf"\b{suffix.lower()}\b", confidence=0.6, note="local shop keyword")
    add(95, "OTHER_INCOME", channel="UPI", direction="CR", confidence=0.6, note="P2P credit")
    add(95, "OTHER_INCOME", channel="NEFT", direction="CR", confidence=0.6, note="business or other credit")
    add(95, "OTHER_INCOME", channel="IMPS", direction="CR", confidence=0.6, note="IMPS credit")
    return rows
