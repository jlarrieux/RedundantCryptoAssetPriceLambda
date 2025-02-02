def transform_asset(asset: str) -> str:
    if asset == "gem":
        asset = "gemswap"
    if asset == "safe":
        asset = "yieldfarming-insure"
    if asset == "yamv2":
        asset = "yam-v2"
    if asset == "uni":
        asset = "uniswap"
    if asset == "ethemaapy":
        asset = "eth-26-ma-crossover-yield-ii"
    if asset == "vcrvplain3andsusd":
        asset = "susd"
    if asset == "mir":
        asset = "mirror-protocol"
    if asset == "bdp":
        asset = "big-data-protocol"
    if asset == "eth" or asset == "weth":
        asset = "ethereum"
    if asset == "GRT" or asset == "grt":
        asset = "the-graph"
    if asset == "snx":
        asset = "havven"
    if asset == "knc":
        asset = "kyber-network"
    if asset == "cvx":
        asset = "convex-finance"
    if asset == "rune":
        asset = "thorchain-erc20"
    if asset == "toke":
        asset = "tokemak"
    if asset == "rdpx":
        asset = "dopex-rebate-token"
    if asset == "sdt" or asset == "SDT":
        asset = "stake-dao"
    if asset == "gmx":
        asset = "GMX"
    if asset == "imx":
        asset = "immutable-x"
    if asset == "silo":
        asset = "silo-finance"
    if asset == "alpha":
        asset = "alpha-finance"
    if asset == "lyra":
        asset = "lyra-finance"
    if asset == "jpeg":
        asset = "jpeg-d"
    if asset == "ast":
        asset = "airswap"
    if asset == "pls":
        asset = "plutusdao"
    if asset == "usdc":
        asset = "usd-coin"
    if asset == "lyra":
        asset = "lyra-finance"
    if asset == "cnc":
        asset = "conic-finance"
    if asset == "gear":
        asset = "gearbox"
    if asset == "xgrail":
        asset = "grail"
    if asset == "crv":
        asset = "curve-dao-token"
    if asset == 'wbtc':
        asset = 'wrapped-bitcoin'
    if asset == 'alp':
        asset = 'arbitrove-alp'

    return asset


if __name__ == '__main__':
    event1 = dict()
    event1["httpMethod"] = "GET"
    asset1 = dict()
    asset1["asset"] = "weth"
    event1["queryStringParameters"] = asset1
""
