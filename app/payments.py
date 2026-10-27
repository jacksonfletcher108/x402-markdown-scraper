from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

from app.catalog import PRODUCTS, Product, bazaar_extension
from app.config import MAINNET, SEPOLIA, Settings, is_usable_pay_to


def payment_options(settings: Settings, price: str) -> list[PaymentOption]:
    return [
        PaymentOption(
            scheme="exact",
            pay_to=settings.x402_pay_to,
            price=price,
            network=network,
        )
        for network in settings.networks()
    ]


def route_config(settings: Settings, product: Product) -> RouteConfig:
    return RouteConfig(
        accepts=payment_options(settings, product.price),
        mime_type="application/json",
        description=product.description,
        service_name=product.name[:32],
        tags=list(product.tags)[:5],
        extensions=bazaar_extension(product),
    )


def paid_routes(settings: Settings) -> dict[str, RouteConfig]:
    routes: dict[str, RouteConfig] = {}
    for product in PRODUCTS:
        key = f"{product.method} {product.path}"
        routes[key] = route_config(settings, product)

    # Keep the original scrape path so existing clients still work.
    scrape = next(product for product in PRODUCTS if product.sku == "scrape.md")
    scrape_config = route_config(settings, scrape)
    routes["GET /scrape"] = scrape_config
    routes["POST /scrape"] = RouteConfig(
        accepts=payment_options(settings, scrape.price),
        mime_type="application/json",
        description=scrape.description,
        service_name=scrape.name[:32],
        tags=list(scrape.tags)[:5],
        extensions=None,
    )
    return routes


def resource_server(settings: Settings) -> x402ResourceServer:
    networks = settings.networks()
    urls: list[str] = []
    if MAINNET in networks:
        urls.append(settings.facilitator_url)
    if SEPOLIA in networks and settings.sepolia_facilitator_url not in urls:
        urls.append(settings.sepolia_facilitator_url)
    if not urls:
        urls.append(settings.sepolia_facilitator_url)

    clients = [HTTPFacilitatorClient(FacilitatorConfig(url=url)) for url in urls]
    server = x402ResourceServer(clients)
    for network in networks:
        server.register(network, ExactEvmServerScheme())
    return server


def paywall_is_testnet(settings: Settings) -> bool:
    return settings.networks() == [SEPOLIA]


def settlement_ready(settings: Settings) -> bool:
    return is_usable_pay_to(settings.x402_pay_to)
