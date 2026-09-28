from dataclasses import replace

from src.invoices.service import InvoiceService
from src.wallet.gateway import WalletGateway
from tests.helpers import FakeRPC, ServiceCase


class RPCServiceIntegrationTests(ServiceCase):
    def test_live_mode_contract_gates_fulfillment_and_preserves_payment_on_outage(self):
        cfg = replace(self.cfg, mode="rpc")
        rpc = FakeRPC()
        wallet = WalletGateway(rpc, cfg, clock=lambda: self.now)
        service = InvoiceService(self.store, wallet, cfg, clock=lambda: self.now)
        inv = service.create({"amount":"10"}, "rpc-order-001")[0]
        self.assertFalse(inv["eligible_for_fulfillment"])
        self.assertTrue(service.sync())
        inv = service.get(inv["id"])
        self.assertTrue(inv["eligible_for_fulfillment"])
        rpc.initial = True
        self.assertFalse(service.sync())
        inv = service.get(inv["id"])
        self.assertEqual(inv["status"], "paid")
        self.assertFalse(inv["eligible_for_fulfillment"])
