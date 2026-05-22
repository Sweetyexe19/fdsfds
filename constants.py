CRYPTO_NETWORKS = [
    ("usdt_trc20", "USDT TRC20", "crypto_usdt_trc20"),
    ("usdt_bep20", "USDT BEP20", "crypto_usdt_bep20"),
    ("usdt_erc20", "USDT ERC20", "crypto_usdt_erc20"),
    ("usdt_aptos", "USDT Aptos", "crypto_usdt_aptos"),
    ("usdt_ton", "USDT TON", "crypto_usdt_ton"),
    ("usdt_solana", "USDT Solana", "crypto_usdt_solana"),
]

CRYPTO_LABELS = {key: label for key, label, _ in CRYPTO_NETWORKS}
