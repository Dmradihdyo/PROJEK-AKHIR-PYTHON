"""Dataclass hasil kembalian core. Sengaja tanpa hash agar aman dikirim ke template."""
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str
    phone: str | None
    balance: int
    role: str
    status: str
    created_at: str

    @property
    def is_active(self) -> bool:
        return self.status == "AKTIF"

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"


@dataclass(frozen=True)
class Transaction:
    id: int
    ref_no: str
    group_ref: str
    user_id: str
    type: str
    direction: str
    amount: int
    fee: int
    counterparty_id: str | None
    note: str | None
    status: str
    created_at: str


@dataclass(frozen=True)
class Receipt:
    """Bukti transaksi untuk ditampilkan ke pengguna."""

    ref_no: str
    type: str
    amount: int
    user_id: str
    counterparty_id: str | None
    note: str | None
    created_at: str
    balance_after: int


@dataclass(frozen=True)
class PaySession:
    token: str
    sender_id: str
    merchant_id: str
    merchant_name: str
    amount: int
    expires_at: int
