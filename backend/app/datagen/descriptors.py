"""Bank-statement narrations in the shapes Indian banks print them."""
from datetime import date

HANDLE_BANK = {"ybl": "YESB", "axl": "UTIB", "icici": "ICIC", "hdfcbank": "HDFC", "paytm": "PYTM",
               "oksbi": "SBIN", "okhdfcbank": "HDFC", "okicici": "ICIC", "okaxis": "UTIB", "kotak": "KKBK",
               "barodampay": "BARB", "pnb": "PUNB", "cnrb": "CNRB"}
HQ = ["MUMBAI", "BENGALURU", "GURUGRAM", "NEW DELHI"]
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def ref_for(key: int, seed: int) -> str:
    """Unique 12-digit RRN per key: the multiplier is coprime with 10**11, so key -> ref is a bijection."""
    return "6" + f"{(key * 48_271_934_567 + seed) % 10**11:011d}"


def hq(merchant_id: str) -> str:
    """City printed on e-commerce card narrations (stable per merchant)."""
    return HQ[int(merchant_id[-4:]) % len(HQ)]


def bank_of(vpa: str) -> str:
    return HANDLE_BANK.get(vpa.split("@", 1)[1], "NPCI")


def upi(dr: bool, ref: str, name: str, vpa: str, note: str) -> str:
    return f"UPI/{'DR' if dr else 'CR'}/{ref}/{name}/{bank_of(vpa)}/{vpa}/{note}"


def upi_reversal(ref: str, name: str, vpa: str) -> str:
    return f"UPI/REV/{ref}/{name}/{bank_of(vpa)}/{vpa}/Reversal"


def ifsc(bank: str, branch: int) -> str:
    return f"{bank}0{branch:06d}"


def neft_cr(ifsc_code: str, payer: str, note: str) -> str:
    return f"NEFT CR-{ifsc_code}-{payer}-{note}"


def imps_self(dr: bool, ref: str, bank: str, last4: int) -> str:
    return f"IMPS/{'P2A' if dr else 'CR'}/{ref}/SELF/{bank} XX{last4}"


def imps_cr(ref: str, payer: str) -> str:
    return f"IMPS/CR/{ref}/{payer}"


def nach(lender: str, ref: str) -> str:
    return f"ACH D- {lender}-EMI {ref[-8:]}"


def bbps(biller: str, service: str, ref: str) -> str:
    return f"BBPS/{biller}/{service}/{ref}"


def pos(last4: int, name: str, city: str) -> str:
    return f"POS 4{last4 * 7 % 100000:05d}XXXXXX{last4} {name} {city.upper()}"


def ecom(name: str, city: str, *, refund: bool = False, recurring: bool = False) -> str:
    tag = "REFUND " if refund else ""
    tail = " RECURRING" if recurring else ""
    return f"ECOM {tag}{name} {city.upper()}{tail}"


def atm(bank_name: str, city: str, ref: str) -> str:
    return f"ATM WDL {bank_name} ATM {city.upper()} {ref[-6:]}"


def interest(start: date, end: date) -> str:
    return f"INT.PD:{start:%d-%m-%Y} TO {end:%d-%m-%Y}"


def cc_bill(bank: str, last4: int, ref: str) -> str:
    return f"CC BILL PAY {bank} CARD XX{last4} {ref}"


def card_payment_received(ref: str) -> str:
    return f"PAYMENT RECEIVED - THANK YOU {ref}"
