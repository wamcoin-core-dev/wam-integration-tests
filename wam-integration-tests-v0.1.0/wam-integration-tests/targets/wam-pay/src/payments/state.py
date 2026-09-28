def derive_state(amount, expires_at, required, payments, now):
    active = [p for p in payments if p["active"]]
    total = sum(p["amount_units"] for p in active)
    confirmed = sum(p["amount_units"] for p in active if p["confirmations"] >= required)
    on_time = sum(p["amount_units"] for p in active
                  if p["confirmations"] >= required and p["first_seen_at"] < expires_at)
    if confirmed >= amount:
        status = "paid" if on_time >= amount else "late_paid"
    elif total >= amount:
        status = "confirming"
    elif total:
        status = "partial_expired" if now >= expires_at else "partially_paid"
    else:
        status = "expired" if now >= expires_at else "pending"
    return status, total, confirmed
