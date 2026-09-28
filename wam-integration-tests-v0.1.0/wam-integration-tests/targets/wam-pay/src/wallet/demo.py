import uuid

from src.errors import ValidationError


class DemoWallet:
    """Synthetic in-memory receipts. Addresses cannot receive real WAM."""
    def __init__(self):
        self.outputs = {}
        self.tip = "d" * 64

    def new_address(self, label):
        return "DEMO_NOT_A_WAM_ADDRESS_" + uuid.uuid4().hex

    def snapshot(self, invoices, known_txids):
        return self.tip, [dict(p) for p in self.outputs.values()]

    def hydrate(self, rows):
        for row in rows:
            if row["active"]:
                self.outputs[(row["txid"], row["vout"])] = {
                    key: row[key] for key in ("txid", "vout", "invoice_id", "amount_units", "confirmations")}

    def receive(self, invoice_id, amount_units, confirmations):
        txid = uuid.uuid4().hex + uuid.uuid4().hex
        self.outputs[(txid, 0)] = {"txid": txid, "vout": 0, "invoice_id": invoice_id,
                                  "amount_units": amount_units, "confirmations": confirmations}
        return txid

    def change(self, invoice_id, txid, confirmations):
        key = (txid, 0)
        if key not in self.outputs or self.outputs[key]["invoice_id"] != invoice_id:
            raise ValidationError("Unknown demo transaction")
        if confirmations < 0:
            del self.outputs[key]
        else:
            self.outputs[key]["confirmations"] = confirmations
