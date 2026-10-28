import logging
import os

from x402.extensions.bazaar import bazaar_resource_server_extension
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

from app.catalog import PRODUCTS, Product, bazaar_extension
from app.config import MAINNET, SEPOLIA, SOLANA, Settings, is_usable_pay_to

log = logging.getLogger("x402.shop")


def payment_options(settings: Settings, price: str) -> list[PaymentOption]:
    options: list[PaymentOption] = []
    for network in settings.networks():
        pay_to = settings.pay_to_for(network)
        if str(network).startswith("solana:") and not settings.solana_enabled():
            continue
        if str(network).startswith("eip155:") and not (
            is_usable_pay_to(pay_to) or network == SEPOLIA
        ):
            continue
        options.append(
            PaymentOption(
                scheme="exact",
                pay_to=pay_to,
                price=price,
                network=network,
            )
        )
    return options


def route_config(settings: Settings, product: Product, *, body_type: str | None = None) -> RouteConfig:
    return RouteConfig(
        accepts=payment_options(settings, product.price),
        mime_type="application/json",
        description=product.description,
        service_name=product.name[:32],
        tags=list(product.tags)[:5],
        extensions=bazaar_extension(product, body_type=body_type),
    )


def paid_routes(settings: Settings) -> dict[str, RouteConfig]:
    routes: dict[str, RouteConfig] = {}
    for product in PRODUCTS:
        routes[f"{product.method} {product.path}"] = route_config(settings, product)
        routes[f"POST {product.path}"] = route_config(settings, product, body_type="json")

    scrape = next(product for product in PRODUCTS if product.sku == "scrape.md")
    scrape_config = route_config(settings, scrape)
    routes["GET /scrape"] = scrape_config
    routes["POST /scrape"] = route_config(settings, scrape, body_type="json")
    return routes


def resource_server(settings: Settings) -> x402ResourceServer:
    networks = settings.networks()
    if settings.uses_cdp():
        os.environ["CDP_API_KEY_ID"] = settings.cdp_api_key_id or ""
        os.environ["CDP_API_KEY_SECRET"] = settings.cdp_api_key_secret or ""
        from cdp.x402 import create_facilitator_config

        clients = [HTTPFacilitatorClient(create_facilitator_config())]
    else:
        urls: list[str] = []
        if MAINNET in networks or SOLANA in networks:
            urls.append(settings.facilitator_url)
        if SEPOLIA in networks and settings.sepolia_facilitator_url not in urls:
            urls.append(settings.sepolia_facilitator_url)
        if not urls:
            urls.append(settings.sepolia_facilitator_url)
        clients = [HTTPFacilitatorClient(FacilitatorConfig(url=url)) for url in urls]

    server = x402ResourceServer(clients)
    server.register_extension(bazaar_resource_server_extension)
    evm_scheme = ExactEvmServerScheme()
    svm_scheme = None
    if settings.solana_enabled():
        from x402.mechanisms.svm.exact import ExactSvmServerScheme

        svm_scheme = ExactSvmServerScheme()
    for network in networks:
        if str(network).startswith("solana:"):
            if svm_scheme is not None:
                server.register(network, svm_scheme)
            else:
                log.warning("solana network requested but SOLANA_WALLET_ADDRESS is unset")
        else:
            server.register(network, evm_scheme)
    return server


def paywall_is_testnet(settings: Settings) -> bool:
    return settings.networks() == [SEPOLIA]


def settlement_ready(settings: Settings) -> bool:
    return is_usable_pay_to(settings.pay_to())
