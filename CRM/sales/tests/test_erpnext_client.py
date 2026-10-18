import json
import os
import runpy
import socket
import sys
import time
import urllib.error
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from sales import erpnext
from sales.erpnext import Client, Refused, Unavailable, client_from_settings
from sales.tests.fakes import FakeERPNext

KEY, SECRET = "crm-key-7f3a", "s3cr3t-xyz"
T403 = "ERPNext refused the integration user (permissions); ask the ERP admin."
UNEXPECTED = "ERPNext sent an unexpected reply."
LINK = ("ERPNEXT_URL", "ERPNEXT_SITE", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET", "ERPNEXT_DESK_URL")


def ok(body):
    return BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())


def http_error(status, body=b""):
    body = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError("http://erp.test/api/v2/x", status, "error", {}, BytesIO(body))


def errors(*messages):
    return {"errors": [{"message": m, "exception": "Traceback (most recent call last): LinkValidationError"}
                       for m in messages]}


class ClientTests(SimpleTestCase):
    def setUp(self):
        self.erp = Client("http://erp.test/", "localhost", KEY, SECRET)
        patcher = mock.patch("urllib.request.urlopen")
        self.urlopen = patcher.start()
        self.addCleanup(patcher.stop)
        self.reply({"data": {"name": "X"}})

    def reply(self, value):
        """value: a body for a 200 (a fresh stream per call), or an exception for urlopen to raise."""
        self.urlopen.side_effect = value if isinstance(value, BaseException) else (lambda *args, **kwargs: ok(value))

    def sent(self):
        request = self.urlopen.call_args.args[0]
        body = json.loads(request.data) if request.data else None
        return request, urlsplit(request.full_url), body

    def refused(self, error, call=None):
        self.reply(error)
        with self.assertRaises(Refused) as caught:
            (call or (lambda: self.erp.create_order({"crm_reference": "QT-2026-00133"})))()
        return str(caught.exception)

    # -- transport -----------------------------------------------------------------------

    def test_headers_and_timeout(self):  # SEND-6, transport
        self.erp.get_customer("Tanjung Electrical Contractors Sdn Bhd")
        request, _, _ = self.sent()
        self.assertEqual(request.get_header("Host"), "localhost")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_header("Authorization"), f"token {KEY}:{SECRET}")
        self.assertEqual(self.urlopen.call_args.kwargs["timeout"], 10)

    def test_find_order_request(self):  # IDEM-1
        row = {"name": "SAL-ORD-2026-00020", "docstatus": 1, "net_total": 235.88, "grand_total": 259.47}
        self.reply({"data": [row]})
        self.assertEqual(self.erp.find_order("QT-2026-00133"), row)
        request, url, body = self.sent()
        self.assertEqual(
            (request.get_method(), url.netloc, url.path), ("GET", "erp.test", "/api/v2/document/Sales%20Order")
        )
        self.assertIsNone(body)
        query = parse_qs(url.query)
        self.assertEqual(json.loads(query["fields"][0]), ["name", "docstatus", "net_total", "grand_total"])
        self.assertEqual(
            json.loads(query["filters"][0]), [["crm_reference", "=", "QT-2026-00133"], ["docstatus", "<", 2]]
        )
        self.assertNotIn(" ", url.query)
        self.reply({"data": []})
        self.assertIsNone(self.erp.find_order("QT-2026-00133"))

    def test_customer_name_is_url_quoted(self):  # CUST-12, Review Focus 1
        self.reply({"data": {"name": "A&B Steel / Fab #1 Sdn Bhd"}})
        self.assertEqual(self.erp.get_customer("A&B Steel / Fab #1 Sdn Bhd"), {"name": "A&B Steel / Fab #1 Sdn Bhd"})
        _, url, _ = self.sent()
        self.assertEqual(url.path, "/api/v2/document/Customer/A%26B%20Steel%20%2F%20Fab%20%231%20Sdn%20Bhd")
        for name in ("A&B / Ng's Sdn Bhd #2", "Syarikat Wong 黄氏 Sdn Bhd", "Kilang Besi Ömbak?x=1"):
            self.erp.get_customer(name)
            request, url, _ = self.sent()
            path = request.full_url.removeprefix("http://erp.test/api/v2/document/Customer/")
            self.assertEqual(unquote(path), name)
            self.assertFalse(set(path) & set("/#?&' "), path)
            self.assertTrue(path.isascii(), path)

    def test_missing_customer_is_none(self):  # CUST-13
        self.reply(http_error(404, errors("Customer Nope not found")))
        self.assertIsNone(self.erp.get_customer("Nope"))

    def test_creates_post_json(self):  # calls 3, 4, 5
        calls = [
            (self.erp.create_customer, "/api/v2/document/Customer", {"customer_name": "SKS", "territory": "Malaysia"}),
            (self.erp.create_address, "/api/v2/document/Address", {"address_title": "SKS", "city": "Seri Kembangan"}),
            (self.erp.create_order, "/api/v2/document/Sales%20Order", {"crm_reference": "QT-1", "docstatus": 1}),
        ]  # fmt: skip
        for call, path, payload in calls:
            self.reply({"data": {"name": "N-1", "docstatus": 1}})
            self.assertEqual(call(payload), {"name": "N-1", "docstatus": 1})
            request, url, body = self.sent()
            self.assertEqual((request.get_method(), url.path, body), ("POST", path, payload))

    def test_submit_order_puts_docstatus_1(self):  # call 5b: a draft is submitted, so ERPNext computes its status
        submitted = {"name": "SAL-ORD-2026-00020", "docstatus": 1, "status": "To Deliver and Bill", "net_total": 235.88}
        self.reply({"data": submitted})
        self.assertEqual(self.erp.submit_order("SAL-ORD-2026-00020"), submitted)
        request, url, body = self.sent()
        self.assertEqual(
            (request.get_method(), url.path, body),
            ("PUT", "/api/v2/document/Sales%20Order/SAL-ORD-2026-00020", {"docstatus": 1}),
        )

    def test_decimal_payload_goes_as_a_json_number(self):  # TOT-1 transport
        self.erp.create_order({"discount_amount": Decimal("19.12")})
        request, _, _ = self.sent()
        self.assertIn(b'"discount_amount": 19.12', request.data)

    def test_tax_rows_copies_four_keys(self):  # call 4b
        sst = {"charge_type": "On Net Total", "account_head": "SST Payable - OMW", "rate": 10, "description": "SST 10%"}
        row = {**sst, "name": "abc", "parent": "Malaysia SST - OMW", "idx": 1, "doctype": "Sales Taxes and Charges"}
        self.reply({"data": {"name": "Malaysia SST - OMW", "taxes": [row]}})
        self.assertEqual(self.erp.tax_rows("Malaysia SST - OMW"), [sst])
        _, url, _ = self.sent()
        self.assertEqual(url.path, "/api/v2/document/Sales%20Taxes%20and%20Charges%20Template/Malaysia%20SST%20-%20OMW")

    # -- error mapping -------------------------------------------------------------------

    def test_unavailable(self):  # ERR-2, ERR-3
        for failure in (
            urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")),
            TimeoutError("timed out"),
            socket.timeout("timed out"),
            ConnectionResetError(104, "reset"),
            http_error(401, errors("Invalid token")),
            http_error(500, b"<html>Internal Server Error</html>"),
            http_error(502, b"Bad Gateway"),
            http_error(503, b""),
        ):
            self.reply(failure)
            with self.assertRaises(Unavailable, msg=repr(failure)):
                self.erp.find_order("QT-2026-00133")

    def test_403_is_refused_with_fixed_text(self):  # ERR-4
        self.assertEqual(self.refused(http_error(403, errors("Not permitted: <b>Sales Order</b>"))), T403)

    def test_refusal_message_is_plain_text(self):  # ERR-5
        text = self.refused(http_error(417, errors("Could not find Item: <strong>FG-XX-999</strong>")))
        self.assertEqual(text, "Could not find Item: FG-XX-999")

    def test_entities_unescaped(self):  # ERR-6
        text = self.refused(http_error(417, errors("Customer &quot;A&amp;B&quot; is disabled")))
        self.assertEqual(text, 'Customer "A&B" is disabled')

    def test_messages_joined_with_one_space(self):  # ERR-7, Clar.
        error = http_error(417, errors("Value missing for: Delivery Date", "Row 1:\n  Rate is <b>mandatory</b>"))
        self.assertEqual(self.refused(error), "Value missing for: Delivery Date Row 1: Rate is mandatory")

    def test_long_message_capped(self):  # ERR-8
        message = "".join(f"word{i:03d} " for i in range(125))  # 1,000 chars
        text = self.refused(http_error(417, errors(message)))
        self.assertLessEqual(len(text), 300)
        self.assertTrue(text.startswith(message[:100]))

    def test_non_json_error_body(self):  # ERR-9, Clar.
        text = self.refused(http_error(417, b"<html><body>Bad request</body></html>"))
        self.assertEqual(text, "ERPNext rejected the request (417).")
        self.assertEqual(self.refused(http_error(422, {"errors": []})), "ERPNext rejected the request (422).")

    def test_404_and_409_on_create_are_refused(self):  # ERR-12
        self.assertEqual(self.refused(http_error(404, errors("DocType Sales Order not found"))),
                         "DocType Sales Order not found")  # fmt: skip
        text = self.refused(http_error(409, errors("Duplicate entry 'QT-2026-00133' for key 'crm_reference'")))
        self.assertEqual(text, "Duplicate entry 'QT-2026-00133' for key 'crm_reference'")

    def test_secret_never_in_text(self):  # ERR-10, Review Focus 2
        echo = f"Bad header Authorization: token {KEY}:{SECRET} on " + "x" * 400 + SECRET
        text = self.refused(http_error(417, errors(echo)))
        self.assertLessEqual(len(text), 300)
        self.assertIn("token ***:***", text)
        for failure in (http_error(401, errors(f"token {KEY}:{SECRET} invalid")), urllib.error.URLError("down"),
                        ValueError(f"Invalid header value 'token {KEY}:{SECRET}\\n'")):  # fmt: skip
            self.reply(failure)
            with self.assertRaises(Unavailable) as caught:
                self.erp.find_order("QT-2026-00133")
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertNotIn(KEY, str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)  # no chained traceback with request details

    def test_unexpected_reply(self):  # Review Focus 3
        calls = (
            lambda: self.erp.find_order("QT-1"),
            lambda: self.erp.create_order({}),
            lambda: self.erp.get_customer("X"),
            lambda: self.erp.tax_rows("Malaysia SST - OMW"),
            lambda: self.erp.submit_order("SAL-ORD-2026-00020"),
        )
        for body in (b"<html>pong</html>", b"", {}, {"message": "ok"}, [1, 2], {"data": None}, {"data": "SAL-ORD"}):
            for call in calls:
                self.assertEqual(self.refused(body, call), UNEXPECTED, msg=(body, call))
        self.assertEqual(self.refused({"data": {"name": "X"}}, lambda: self.erp.find_order("QT-1")), UNEXPECTED)
        self.assertEqual(self.refused({"data": [{"name": "X"}]}, lambda: self.erp.create_order({})), UNEXPECTED)
        self.assertEqual(self.refused({"data": {"name": "T"}}, lambda: self.erp.tax_rows("T")), UNEXPECTED)

    def test_never_reads_exception_field(self):  # ACT-E6
        source = Path(erpnext.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"[\"']exception[\"']")


class SilentServerTests(SimpleTestCase):
    def test_timeout_on_a_server_that_never_answers(self):  # SEND-7
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            erp = Client(f"http://127.0.0.1:{server.getsockname()[1]}", "localhost", KEY, SECRET, timeout=0.5)
            started = time.monotonic()
            with self.assertRaises(Unavailable):
                erp.find_order("QT-2026-00133")
            self.assertLess(time.monotonic() - started, 1.5)


class SettingsTests(SimpleTestCase):
    def test_not_configured(self):  # CFG-4, CFG-5
        with override_settings():
            for name in ("ERPNEXT_URL", "ERPNEXT_SITE", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET"):
                if hasattr(settings, name):
                    delattr(settings, name)
            self.assertIsNone(client_from_settings())
        with override_settings(ERPNEXT_URL="", ERPNEXT_SITE="localhost", ERPNEXT_API_KEY="k", ERPNEXT_API_SECRET="s"):
            self.assertIsNone(client_from_settings())

    @override_settings(ERPNEXT_URL="http://erp.test", ERPNEXT_SITE="localhost", ERPNEXT_API_KEY="k",
                       ERPNEXT_API_SECRET="s3cr3t-xyz")  # fmt: skip
    def test_configured(self):  # CFG-1 (configured side)
        erp = client_from_settings()
        self.assertIsInstance(erp, Client)
        with mock.patch("urllib.request.urlopen", return_value=ok({"data": []})) as urlopen:
            erp.find_order("QT-2026-00133")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith("http://erp.test/api/v2/document/Sales%20Order?"))
        self.assertEqual(request.get_header("Authorization"), "token k:s3cr3t-xyz")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    @staticmethod
    def loaded(argv, env):
        """crm/settings.py's values when run as `argv` with this env (and no other ERPNEXT_* vars)."""
        clean = {name: value for name, value in os.environ.items() if not name.startswith("ERPNEXT_")}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True), mock.patch.object(sys, "argv", argv):
            return runpy.run_path(str(settings.BASE_DIR / "crm" / "settings.py"))

    def test_settings_default_to_not_configured(self):  # NET (settings empty -> not configured)
        served = self.loaded(["gunicorn", "crm.wsgi"], {})
        self.assertEqual([served[name] for name in LINK], ["", "localhost", "", "", ""])

    def test_unit_tests_never_get_the_url(self):  # Task 4.1 guard: the web container may have the override's env
        env = dict(zip(LINK, ["http://backend:8000", "contract.localhost", "k", "s", "http://localhost:8080"]))
        served = self.loaded(["gunicorn", "crm.wsgi"], env)
        self.assertEqual({name: served[name] for name in LINK}, env)
        self.assertEqual(self.loaded(["manage.py", "test", "sales"], env)["ERPNEXT_URL"], "")
        self.assertIsNone(client_from_settings())  # this very run: an unpatched unit test can't reach ERPNext


class FakeTests(SimpleTestCase):
    """The fake behaves like ERPNext where the 004 tests rely on it (test-cases.md, Fixtures)."""

    def order(self, reference="QT-2026-00133", discount=19.12, taxes=True):
        fake = self.fake
        payload = {
            "customer": "Tanjung Electrical Contractors Sdn Bhd",
            "crm_reference": reference,
            "items": [{"item_code": "FG-CT-300", "qty": 3, "rate": 85.0}],
            "discount_amount": discount,
        }
        if taxes:
            payload["taxes"] = fake.tax_rows("Malaysia SST - OMW")
        return fake.create_order(payload)

    def setUp(self):
        self.fake = FakeERPNext()

    def test_order_totals_and_lookup(self):
        sst = {"charge_type": "On Net Total", "account_head": "SST Payable - OMW", "rate": 10, "description": "SST 10%"}
        self.assertEqual(self.fake.tax_rows("Malaysia SST - OMW"), [sst])
        self.assertIsNone(self.fake.find_order("QT-2026-00133"))
        draft = self.order()  # ERPNext's default docstatus: a draft
        self.assertEqual(
            draft, {"name": "SAL-ORD-2026-00020", "docstatus": 0, "net_total": 235.88, "grand_total": 259.47}
        )
        self.assertEqual(self.fake.find_order("QT-2026-00133"), draft)  # the lookup finds drafts too
        order = self.fake.submit_order("SAL-ORD-2026-00020")
        self.assertEqual(order, {**draft, "docstatus": 1})
        self.assertEqual(self.fake.find_order("QT-2026-00133"), order)
        with self.assertRaisesMessage(Refused, "not a draft"):
            self.fake.submit_order("SAL-ORD-2026-00020")
        with self.assertRaisesMessage(Refused, "QT-2026-00133"):
            self.order()  # unique crm_reference
        sg = self.order("QT-2026-00134", discount=Decimal("0"), taxes=False)
        self.assertEqual((sg["name"], sg["net_total"], sg["grand_total"]), ("SAL-ORD-2026-00021", 255.0, 255.0))
        self.fake.orders["QT-2026-00135"] = {"name": "SAL-ORD-2026-00001", "docstatus": 2}  # cancelled
        self.assertIsNone(self.fake.find_order("QT-2026-00135"))
        with self.assertRaises(Refused):
            self.order("QT-2026-00135")

    def test_customers_match_like_mariadb(self):
        tec = self.fake.get_customer("TANJUNG ELECTRICAL CONTRACTORS SDN BHD  ")
        self.assertEqual(tec["name"], "Tanjung Electrical Contractors Sdn Bhd")
        self.assertIsNone(self.fake.get_customer("Seri Kembangan Steel Works Sdn Bhd"))
        created = self.fake.create_customer({"customer_name": "Seri Kembangan Steel Works Sdn Bhd"})
        self.assertEqual(created["name"], "Seri Kembangan Steel Works Sdn Bhd")
        self.assertEqual(self.fake.get_customer("seri kembangan steel works sdn bhd")["name"], created["name"])
        address = self.fake.create_address({"address_title": "SKS", "links": [{"link_name": created["name"]}]})
        self.assertTrue(address["name"])

    def test_calls_failures_and_hooks(self):
        seen = []
        self.fake.hooks["find_order"] = lambda: seen.append("hook")
        self.fake.fail["get_customer"] = Unavailable("timed out")
        self.fake.find_order("QT-1")
        with self.assertRaises(Unavailable):
            self.fake.get_customer("X")
        self.assertEqual(self.fake.calls, [("find_order", "QT-1"), ("get_customer", "X")])
        self.assertEqual(self.fake.names, ["find_order", "get_customer"])
        self.assertEqual(seen, ["hook"])
        self.fake.fail_after["create_order"] = Unavailable("timed out")  # the order lands, the reply is lost
        with self.assertRaises(Unavailable):
            self.order()
        self.assertEqual(self.fake.find_order("QT-2026-00133")["name"], "SAL-ORD-2026-00020")
        self.fake.fail_after.clear()  # failures stay until removed
        self.fake.net_total = 235.89
        self.assertEqual(self.order("QT-2026-00136")["net_total"], 235.89)
