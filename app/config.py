from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from x402.schemas import Network

PLACEHOLDER_PAY_TO = {
    "0xyourevmaddress",
    "0x0000000000000000000000000000000000000000",
    "0x0000000000000000000000000000000000000001",
}

MAINNET: Network = "eip155:8453"
SEPOLIA: Network = "eip155:84532"
MAINNET_FACILITATOR = "https://facilitator.payai.network"
SEPOLIA_FACILITATOR = "https://x402.org/facilitator"
CDP_FACILITATOR = "https://api.cdp.coinbase.com/platform/v2/x402"


def is_placeholder_pay_to(address: str) -> bool:
    return address.strip().lower() in PLACEHOLDER_PAY_TO


def is_usable_pay_to(address: str) -> bool:
    value = address.strip()
    if not value.startswith("0x") or len(value) != 42:
        return False
    try:
        return int(value, 16) > 0x100
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    x402_pay_to: str
    # Comma-separated CAIP-2 ids. Mainnet first so Coinbase Wallet USDC matches.
    x402_networks: str = f"{MAINNET},{SEPOLIA}"
    x402_price: str = "$0.01"
    facilitator_url: str = MAINNET_FACILITATOR
    sepolia_facilitator_url: str = SEPOLIA_FACILITATOR
    cdp_api_key_id: str | None = None
    cdp_api_key_secret: str | None = None
    evm_private_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 4021
    request_timeout_seconds: float = 20.0
    max_html_bytes: int = 2_000_000

    def networks(self) -> list[Network]:
        requested = [item.strip() for item in self.x402_networks.split(",") if item.strip()]
        if not is_usable_pay_to(self.x402_pay_to):
            # Do not accept real USDC until a real receiving wallet is configured.
            return [SEPOLIA]
        return requested or [MAINNET]

    def uses_cdp(self) -> bool:
        return bool(self.cdp_api_key_id and self.cdp_api_key_secret)

    def facilitator_kind(self) -> str:
        return "cdp" if self.uses_cdp() else "payai"


@lru_cache
def get_settings() -> Settings:
    return Settings()
