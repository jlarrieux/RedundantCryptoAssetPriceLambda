import unittest
import price_service
import time

qp = "queryStringParameters"
http_error = "httpError"


class Test(unittest.TestCase):

    def setUp(self):
        self.event = dict()

    def test_no_parameter_raises(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler()

    def test_empty_event_only_raises(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler("")

    def test_none_event_only_raised(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler(None)

    def test_none_event_and_empty_context_raises(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler(None, "")

    def test_empty_event_and_empty_context_raises(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler("", "")

    def test_none_event_and_none_context_raises(self):
        with self.assertRaises(TypeError):
            lambda_function.lambda_handler(None, None)

    def test_empty_dict_event_and_none_context_raises(self):
        with self.assertRaises(KeyError, msg=http_error):
            lambda_function.lambda_handler(self.event, None)

    def test_single_asset_does_not_raise(self):
        self.add_http_method_to_event()
        self.event[qp] = {"asset": "eth"}
        actual = lambda_function.lambda_handler(self.event, None)

    def test_asset_list_does_not_raise(self):
        self.add_http_method_to_event()
        self.event[qp] = {'asset': 'items={\'["bacon", "yfi", "dai"]\'}'}
        print(lambda_function.lambda_handler(self.event, None))

    def test_asset_list_time_length(self):
        start = time.time()
        self.add_http_method_to_event()
        self.event[qp] = {'asset': 'items={\'["BACON", "YFI", "DAI", "LEND", "UMA", "MTA", "LINK", "BAL", "KNC", "YAM", "$BASED", "CRV", "aLINK", "SWRV", "USDC", "FARM", "MLN", "PICKLE", "OMG", "REN", "AST", "wNXM", "SNX", "GEM", "YAMv2", "UNI", "TUSD", "MLN", "RAC", "KATANA", "AAVE", "WOA", "KNC", "ROOK", "OCTO", "zLOT", "HEGIC", "SYN", "AUDIO", "DNT", "ARCH", "SUSHI", "SAND", "GNO", "WBTC", "GRT", "1INCH", "RUNE", "PERP", "ALPHA", "xSUSHI", "NFTX", "LRC", "ALCX", "MATIC", "DEGEN", "RGT", "WETH", "MIR", "BDP", "VISION"]\'}'}
        print(lambda_function.lambda_handler(self.event, None))
        print(f"It took {time.time() - start} seconds")

    def add_http_method_to_event(self, method: str = "GET"):
        self.event["httpMethod"] = method


if __name__ == '__main__':
    unittest.main()

