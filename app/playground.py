"""Browser playground on the landing page: pays a real x402 request from the visitor's wallet.

Client-side only. It calls the same paid routes as any agent (unpaid POST -> 402 ->
EIP-3009 signature via eth_signTypedData_v4 -> retry with PAYMENT-SIGNATURE), so the
backend paywall is untouched.
"""

from __future__ import annotations

import html

from app.catalog import Product

PLAYGROUND_LABELS = {
    "scrape.md": "Basic Scrape",
    "page.summary": "AI Summary",
    "page.metadata": "Extract Metadata",
    "doc.pdf": "Parse PDF",
    "site.crawl": "Deep Crawl",
}

PLAYGROUND_CSS = """
    .playground { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1.25rem; margin:1.5rem 0; }
    .playground h2 { margin-top:0; }
    .pg-grid { display:grid; grid-template-columns:2fr 1fr auto; gap:.75rem; align-items:end; }
    .pg-grid label { display:flex; flex-direction:column; gap:.3rem; font-size:.85rem; color:var(--muted); min-width:0; }
    .pg-grid label[hidden] { display:none; }
    .pg-grid input, .pg-grid select { font:inherit; color:var(--ink); padding:.5rem .6rem; border:1px solid var(--line); border-radius:8px; background:#fff; min-width:0; }
    .pg-actions { display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; margin-top:.9rem; }
    .pg-btn { font:inherit; font-weight:600; border:0; border-radius:8px; padding:.55rem 1rem; cursor:pointer; background:var(--ink); color:#fff; }
    .pg-btn.primary { background:var(--accent); }
    .pg-btn.ghost { background:#fff; color:var(--ink); border:1px solid var(--line); }
    .pg-btn:disabled { opacity:.55; cursor:progress; }
    .pg-account { font-size:.85rem; color:var(--muted); font-family:ui-monospace,monospace; }
    .pg-steps[hidden] { display:none; }
    .pg-steps { list-style:none; display:flex; flex-wrap:wrap; gap:.4rem; padding:0; margin:1rem 0 .4rem; }
    .pg-steps li { font-size:.8rem; padding:.2rem .6rem; border-radius:999px; background:#f1f5f9; color:var(--muted); }
    .pg-steps li.active { background:#fef3c7; color:#92400e; }
    .pg-steps li.done { background:#d1fae5; color:#065f46; }
    .pg-status { min-height:1.4rem; font-size:.9rem; }
    .pg-status.error { color:#b91c1c; }
    .pg-output { margin-top:.75rem; }
    .pg-out-head { display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; margin-bottom:.4rem; }
    .pg-out-head a { font-size:.85rem; color:var(--accent); }
    .pg-out-head .pg-btn { margin-left:auto; padding:.3rem .7rem; font-size:.85rem; }
    #pg-result { display:block; white-space:pre-wrap; word-break:break-word; max-height:28rem; }
    .pg-nowallet { margin-top:.9rem; padding:.9rem 1rem; border:1px solid #fde68a; background:#fffbeb; border-radius:10px; }
    .pg-nowallet[hidden] { display:none; }
    .pg-nowallet p { margin:.3rem 0 .6rem; font-size:.9rem; color:var(--muted); }
    .pg-links { display:flex; flex-wrap:wrap; gap:.5rem; }
    .pg-links a { text-decoration:none; font-size:.9rem; font-weight:600; padding:.45rem .8rem; border-radius:8px; background:var(--ink); color:#fff; }
    .pg-toast { position:fixed; left:50%; bottom:1.25rem; transform:translateX(-50%); width:min(32rem, calc(100% - 2rem)); background:var(--ink); color:#fff; border-radius:10px; padding:.8rem 1rem; display:flex; gap:.75rem; align-items:center; box-shadow:0 10px 25px rgba(15,23,42,.25); z-index:10; }
    .pg-toast[hidden] { display:none; }
    .pg-toast span { flex:1; font-size:.9rem; }
    .pg-toast button { font:inherit; font-size:.85rem; border:0; border-radius:6px; padding:.35rem .7rem; cursor:pointer; }
    @media (max-width: 640px) { .pg-grid { grid-template-columns:1fr; } }
"""

_SCRIPT = """
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const CHAINS = {
    8453: { chainId: "0x2105", chainName: "Base", nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
            rpcUrls: ["https://mainnet.base.org"], blockExplorerUrls: ["https://basescan.org"] },
    84532: { chainId: "0x14a34", chainName: "Base Sepolia", nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
             rpcUrls: ["https://sepolia.base.org"], blockExplorerUrls: ["https://sepolia.basescan.org"] },
  };
  const STEPS = ["connect", "sign", "settle", "done"];
  const sku = $("pg-sku"), run = $("pg-run"), connectBtn = $("pg-connect");
  let account = null;
  let lastText = "";

  // EIP-6963: wallets that don't claim window.ethereum still announce themselves.
  const announced = [];
  window.addEventListener("eip6963:announceProvider", (event) => {
    if (event.detail && event.detail.provider) announced.push(event.detail.provider);
  });
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  let wcProvider = null;
  const wallet = () => wcProvider || window.ethereum || announced[0];
  const wcButton = $("pg-wc");
  const option = () => sku.options[sku.selectedIndex];
  const isMobile = () => /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
    || (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));

  function showNoWallet() {
    const links = $("pg-wallet-links");
    links.replaceChildren();
    const here = location.host + location.pathname + "#playground";
    const items = isMobile()
      ? [["Open in MetaMask app", "https://metamask.app.link/dapp/" + here],
         ["Open in Coinbase Wallet app", "https://go.cb-w.com/dapp?cb_url=" + encodeURIComponent("https://" + here)]]
      : [["Install MetaMask", "https://metamask.io/download/"],
         ["Install Coinbase Wallet", "https://www.coinbase.com/wallet/downloads"],
         ["Install Rabby", "https://rabby.io/"]];
    items.forEach(([label, href]) => {
      const a = document.createElement("a");
      a.textContent = label;
      a.href = href;
      a.target = "_blank";
      a.rel = "noopener";
      links.appendChild(a);
    });
    $("pg-nowallet-text").textContent = isMobile()
      ? "Mobile browsers can't reach a wallet. Open this page inside your wallet app's browser, then tap Connect wallet again."
      : wcButton
        ? "Click WalletConnect (QR) to scan with a phone wallet app, or install a browser extension and reload. You need a little USDC on Base (no ETH for gas)."
        : "Install a browser wallet extension, add a little USDC on Base (no ETH needed for gas), then reload this page.";
    $("pg-nowallet").hidden = false;
  }

  function decodeB64Json(value) {
    let s = value.replace(/-/g, "+").replace(/_/g, "/");
    s += "=".repeat((4 - (s.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function encodeB64Json(obj) {
    let bin = "";
    new TextEncoder().encode(JSON.stringify(obj)).forEach((b) => { bin += String.fromCharCode(b); });
    return btoa(bin);
  }
  function randomNonce() {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    return "0x" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function setStep(active) {
    const idx = STEPS.indexOf(active);
    document.querySelectorAll("#pg-steps li").forEach((li) => {
      const i = STEPS.indexOf(li.dataset.step);
      li.classList.toggle("done", active === "done" ? true : i < idx);
      li.classList.toggle("active", active !== "done" && i === idx);
    });
  }
  function resetSteps() {
    $("pg-steps").hidden = false;
    document.querySelectorAll("#pg-steps li").forEach((li) => li.classList.remove("done", "active"));
  }
  function status(text, isError) {
    const el = $("pg-status");
    el.textContent = text;
    el.classList.toggle("error", !!isError);
  }
  function toast(text, actionLabel, action) {
    const el = $("pg-toast");
    el.querySelector("span").textContent = text;
    const btn = el.querySelector("button");
    btn.textContent = actionLabel || "Dismiss";
    btn.onclick = async () => { el.hidden = true; if (action) await action(); };
    el.hidden = false;
  }

  function syncSku() {
    const opt = option();
    run.textContent = (opt.dataset.verb || "Scrape") + " (" + opt.dataset.price + ")";
    $("pg-depth-wrap").hidden = opt.dataset.sku !== "site.crawl";
  }

  async function connect() {
    if (!wallet()) {
      showNoWallet();
      const err = new Error("No browser wallet found.");
      err.quiet = true;  // the help panel already explains it
      throw err;
    }
    $("pg-nowallet").hidden = true;
    setStep("connect");
    status("Connecting Wallet...");
    let accounts;
    try {
      accounts = await wallet().request({ method: "eth_requestAccounts" });
    } catch (err) {
      if (err && err.code === -32002) throw new Error("A connection request is already open. Click your wallet extension icon to approve it.");
      if (err && err.code === 4001) throw new Error("Connection rejected in wallet.");
      throw err;
    }
    setAccount(accounts[0]);
    return account;
  }

  function setAccount(next) {
    account = next || null;
    $("pg-account").textContent = account ? account.slice(0, 6) + "…" + account.slice(-4) : "";
    connectBtn.textContent = account ? "Wallet connected" : "Connect wallet";
    if (account) status("");
  }

  async function connectWalletConnect() {
    wcButton.disabled = true;
    try {
      status("Opening WalletConnect...");
      const { EthereumProvider } = await import("https://cdn.jsdelivr.net/npm/@walletconnect/ethereum-provider@2.26.0/+esm");
      const provider = await EthereumProvider.init({
        projectId: wcButton.dataset.projectId,
        chains: [8453],
        optionalChains: [84532],
        showQrModal: true,
        metadata: { name: "x402 Agent Store", description: "Pay-per-request web scraping in USDC on Base.",
                    url: location.origin, icons: [] },
      });
      await provider.enable();
      wcProvider = provider;
      provider.on("accountsChanged", (accounts) => setAccount(accounts[0]));
      provider.on("disconnect", () => { wcProvider = null; setAccount(null); });
      $("pg-nowallet").hidden = true;
      setAccount(provider.accounts[0]);
    } catch (err) {
      status(err && err.message ? "WalletConnect: " + err.message : "WalletConnect was closed.", true);
    } finally {
      wcButton.disabled = false;
    }
  }

  async function ensureChain(chainId) {
    const current = parseInt(await wallet().request({ method: "eth_chainId" }), 16);
    if (current === chainId) return;
    const chain = CHAINS[chainId];
    try {
      await wallet().request({ method: "wallet_switchEthereumChain", params: [{ chainId: chain.chainId }] });
    } catch (err) {
      if (err && err.code === 4902) {
        await wallet().request({ method: "wallet_addEthereumChain", params: [chain] });
      } else {
        toast("Your wallet is on the wrong network. Switch to " + chain.chainName + " to pay.",
              "Switch to " + chain.chainName, () => ensureChain(chainId));
        throw new Error("Wrong network: switch to " + chain.chainName + ".");
      }
    }
  }

  function requestBody() {
    const body = { url: $("pg-url").value.trim() };
    if (option().dataset.sku === "site.crawl") body.max_depth = parseInt($("pg-depth").value, 10);
    return body;
  }

  function pickRequirement(challenge) {
    const accepts = challenge.accepts || [];
    return accepts.find((a) => a.scheme === "exact" && a.network === "eip155:8453")
        || accepts.find((a) => a.scheme === "exact" && a.network === "eip155:84532");
  }

  async function signPayment(challenge, req) {
    const chainId = parseInt(req.network.split(":")[1], 10);
    await ensureChain(chainId);
    const now = Math.floor(Date.now() / 1000);
    const authorization = {
      from: account,
      to: req.payTo,
      value: String(req.amount),
      validAfter: "0",
      validBefore: String(now + (req.maxTimeoutSeconds || 300)),
      nonce: randomNonce(),
    };
    const typedData = {
      types: {
        EIP712Domain: [
          { name: "name", type: "string" }, { name: "version", type: "string" },
          { name: "chainId", type: "uint256" }, { name: "verifyingContract", type: "address" },
        ],
        TransferWithAuthorization: [
          { name: "from", type: "address" }, { name: "to", type: "address" },
          { name: "value", type: "uint256" }, { name: "validAfter", type: "uint256" },
          { name: "validBefore", type: "uint256" }, { name: "nonce", type: "bytes32" },
        ],
      },
      primaryType: "TransferWithAuthorization",
      domain: { name: req.extra.name, version: req.extra.version, chainId, verifyingContract: req.asset },
      message: authorization,
    };
    setStep("sign");
    status("Awaiting Wallet Signature... (" + (Number(req.amount) / 1e6).toFixed(2) + " USDC)");
    const signature = await wallet().request({
      method: "eth_signTypedData_v4",
      params: [account, JSON.stringify(typedData)],
    });
    const payload = { x402Version: 2, accepted: req, payload: { authorization, signature } };
    if (challenge.resource) payload.resource = challenge.resource;
    if (challenge.extensions) payload.extensions = challenge.extensions;
    return encodeB64Json(payload);
  }

  function render(data, receipt) {
    let text;
    if (data && typeof data.markdown === "string") {
      text = Array.isArray(data.summary)
        ? data.summary.map((b) => "- " + b).join("\\n") + "\\n\\n---\\n\\n" + data.markdown
        : data.markdown;
    } else {
      text = JSON.stringify(data, null, 2);
    }
    lastText = text;
    $("pg-result").textContent = text;
    const tx = $("pg-tx");
    if (receipt && receipt.transaction) {
      const explorer = receipt.network === "eip155:84532" ? "https://sepolia.basescan.org" : "https://basescan.org";
      tx.href = explorer + "/tx/" + receipt.transaction;
      tx.textContent = "View USDC transfer ↗";
      tx.hidden = false;
    } else {
      tx.hidden = true;
    }
    $("pg-output").hidden = false;
  }

  async function errorText(response) {
    try {
      const body = await response.json();
      return body.detail || body.error || JSON.stringify(body);
    } catch (_) {
      return "HTTP " + response.status;
    }
  }

  async function play() {
    const url = $("pg-url").value.trim();
    if (!/^https?:\\/\\//i.test(url)) { status("Enter a full http(s) URL to scrape.", true); return; }
    run.disabled = true;
    resetSteps();
    try {
      if (!account) await connect();
      setStep("sign");
      status("Requesting price...");
      const path = option().value;
      const init = { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
                     body: JSON.stringify(requestBody()) };
      const probe = await fetch(path, init);
      if (probe.status !== 402) throw new Error("Expected HTTP 402, got " + probe.status + ": " + await errorText(probe));
      const header = probe.headers.get("PAYMENT-REQUIRED");
      if (!header) throw new Error("402 response had no PAYMENT-REQUIRED header.");
      const challenge = decodeB64Json(header);
      const req = pickRequirement(challenge);
      if (!req) throw new Error("No Base USDC payment option offered.");
      const signatureHeader = await signPayment(challenge, req);
      setStep("settle");
      status("Settling x402 Transfer...");
      const paid = await fetch(path, { ...init, headers: { ...init.headers, "PAYMENT-SIGNATURE": signatureHeader } });
      if (!paid.ok) {
        const retry = paid.headers.get("PAYMENT-REQUIRED");
        const reason = retry ? (decodeB64Json(retry).error || "payment rejected") : await errorText(paid);
        throw new Error("Payment not accepted: " + reason);
      }
      const receiptHeader = paid.headers.get("PAYMENT-RESPONSE");
      render(await paid.json(), receiptHeader ? decodeB64Json(receiptHeader) : null);
      setStep("done");
      status("Done!");
    } catch (err) {
      const msg = err && err.code === 4001 ? "Signature cancelled in wallet. Nothing was charged." : (err.message || String(err));
      if (err && err.quiet) {
        status("");
        $("pg-steps").hidden = true;
      } else {
        status(msg, true);
      }
      document.querySelectorAll("#pg-steps li.active").forEach((li) => li.classList.remove("active"));
    } finally {
      run.disabled = false;
    }
  }

  sku.addEventListener("change", syncSku);
  connectBtn.addEventListener("click", () => connect().catch((e) => status(e.quiet ? "" : (e.message || String(e)), !e.quiet)));
  if (wcButton) wcButton.addEventListener("click", connectWalletConnect);
  run.addEventListener("click", play);
  $("pg-copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(lastText);
    $("pg-copy").textContent = "Copied";
    setTimeout(() => { $("pg-copy").textContent = "Copy Markdown"; }, 1500);
  });
  if (wallet() && wallet().on) {
    wallet().on("accountsChanged", (accounts) => setAccount(accounts[0]));
  }
  syncSku();
})();
</script>
"""


def playground_html(products: tuple[Product, ...], walletconnect_project_id: str = "") -> str:
    wc_button = ""
    if walletconnect_project_id:
        wc_button = (
            '<button type="button" class="pg-btn ghost" id="pg-wc" '
            f'data-project-id="{html.escape(walletconnect_project_id)}">WalletConnect (QR)</button>'
        )
    options = []
    for product in products:
        label = PLAYGROUND_LABELS.get(product.sku)
        if not label:
            continue
        verb = "Crawl" if product.sku == "site.crawl" else "Parse" if product.sku == "doc.pdf" else "Scrape"
        options.append(
            f'<option value="{html.escape(product.path)}" data-sku="{html.escape(product.sku)}" '
            f'data-price="{html.escape(product.price)}" data-verb="{verb}">'
            f"{html.escape(label)} ({html.escape(product.price)} USDC)</option>"
        )
    return f"""
    <section class="playground" id="playground" aria-labelledby="pg-title">
      <h2 id="pg-title">Web Scraping Playground</h2>
      <p class="muted">Pay a real x402 request from your browser wallet (MetaMask, Coinbase Wallet, Rabby) in USDC on Base. You sign one EIP-3009 transfer per run; cancelling the signature charges nothing.</p>
      <div class="pg-grid">
        <label>Target URL <input id="pg-url" type="url" value="https://example.com" placeholder="https://…" autocomplete="url"></label>
        <label>SKU <select id="pg-sku">{"".join(options)}</select></label>
        <label id="pg-depth-wrap" hidden>Depth <select id="pg-depth"><option>1</option><option selected>2</option><option>3</option></select></label>
      </div>
      <div class="pg-actions">
        <button type="button" class="pg-btn ghost" id="pg-connect">Connect wallet</button>
        {wc_button}
        <button type="button" class="pg-btn primary" id="pg-run">Scrape ($0.01)</button>
        <span class="pg-account" id="pg-account"></span>
      </div>
      <div class="pg-nowallet" id="pg-nowallet" hidden>
        <strong>No browser wallet detected</strong>
        <p id="pg-nowallet-text"></p>
        <div class="pg-links" id="pg-wallet-links"></div>
      </div>
      <ol class="pg-steps" id="pg-steps" hidden>
        <li data-step="connect">Connecting Wallet</li>
        <li data-step="sign">Awaiting Wallet Signature</li>
        <li data-step="settle">Settling x402 Transfer</li>
        <li data-step="done">Done!</li>
      </ol>
      <div class="pg-status" id="pg-status" role="status" aria-live="polite"></div>
      <div class="pg-output" id="pg-output" hidden>
        <div class="pg-out-head"><strong>Result</strong><a id="pg-tx" target="_blank" rel="noopener" hidden></a>
          <button type="button" class="pg-btn ghost" id="pg-copy">Copy Markdown</button></div>
        <pre id="pg-result"></pre>
      </div>
    </section>
    <div class="pg-toast" id="pg-toast" role="alert" hidden><span></span><button type="button"></button></div>
{_SCRIPT}"""
