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
SOLANA: Network = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
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


def is_usable_solana(address: str) -> bool:
    value = address.strip()
    if len(value) < 32 or len(value) > 44:
        return False
    alphabet = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return all(char in alphabet for char in value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Preferred Render name. X402_PAY_TO remains a fallback for existing deploys.
    payment_wallet_address: str = ""
    x402_pay_to: str = ""
    solana_wallet_address: str = ""
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
    max_pdf_bytes: int = 8_000_000
    max_download_bytes: int = 10_000_000
    max_redirects: int = 5
    crawl_timeout_seconds: float = 15.0
    cache_ttl_seconds: float = 900.0
    # Public address used in llms.txt, sitemap, manifests and code samples. Set PUBLIC_URL
    # to a custom domain once it points at this service.
    public_url: str = "https://x402-markdown-scraper.onrender.com"
    # Public Reown (WalletConnect) project id; enables the playground's QR connect button.
    # Not a secret: it is rendered into the page. WALLETCONNECT_PROJECT_ID overrides it.
    walletconnect_project_id: str = "36c9bdd1d2bfac1b08a0ec21a93b6dd7"

    def networks(self) -> list[Network]:
        requested = [item.strip() for item in self.x402_networks.split(",") if item.strip()]
        if not is_usable_pay_to(self.pay_to()):
            # Do not accept real USDC until a real receiving wallet is configured.
            networks = [SEPOLIA]
        else:
            networks = requested or [MAINNET]
        if self.solana_enabled() and SOLANA not in networks:
            networks.append(SOLANA)
        return networks

    def pay_to(self) -> str:
        for candidate in (self.payment_wallet_address, self.x402_pay_to):
            value = candidate.strip()
            if value:
                return value
        return "0x0000000000000000000000000000000000000000"

    def solana_pay_to(self) -> str:
        return self.solana_wallet_address.strip()

    def solana_enabled(self) -> bool:
        return is_usable_solana(self.solana_pay_to())

    def pay_to_for(self, network: Network) -> str:
        if str(network).startswith("solana:"):
            return self.solana_pay_to()
        return self.pay_to()

    def uses_cdp(self) -> bool:
        return bool(self.cdp_api_key_id and self.cdp_api_key_secret)

    def facilitator_kind(self) -> str:
        return "cdp" if self.uses_cdp() else "payai"


@lru_cache
def get_settings() -> Settings:
    return Settings()
