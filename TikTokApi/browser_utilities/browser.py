import random
import time
import string
from typing import Any, Optional
from operator import itemgetter
import requests
import logging
import time
import random
import json
import re
from .browser_interface import BrowserInterface
from urllib.parse import parse_qsl, urlparse
import threading
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from ..utilities import LOGGER_NAME
from .get_acrawler import _get_acrawler, _get_tt_params_script, _get_signer_script, _get_webmssdk_script
from TikTokApi.helpers import encrypt_tt_param_v2

logger = logging.getLogger(LOGGER_NAME)


class browser(BrowserInterface):

    def __init__(self, **kwargs):
        pass

    @staticmethod
    async def create(
        **kwargs,
    ):
        self = browser()
        self.kwargs = kwargs
        self.debug = kwargs.get("debug", False)
        self.proxy = kwargs.get("proxy", None)
        self.api_url = kwargs.get("api_url", None)
        self.web_url = kwargs.get("web_url", "https://www.tiktok.com/@tiktok")
        self.referrer = kwargs.get("referer", "https://www.tiktok.com/")
        self.language = kwargs.get("language", "en")
        self.executable_path = kwargs.get("executable_path", None)
        self.device_id = kwargs.get("custom_device_id", None)
        self.device_mobile = kwargs.get("device_mobile", True)

        args = kwargs.get("browser_args", [])
        options = kwargs.get("browser_options", {})

        if len(args) == 0:
            self.args = []
        else:
            self.args = args

        self.options = {
            "headless": True,
            "handle_sigint": True,
            "handle_sigterm": True,
            "handle_sighup": True,
        }

        if self.proxy is not None:
            if "@" in self.proxy:
                server_prefix = self.proxy.split("://")[0]
                address = self.proxy.split("@")[1]
                self.options["proxy"] = {
                    "server": server_prefix + "://" + address,
                    "username": self.proxy.split("://")[1].split("@")[0].split(":")[0],
                    "password": self.proxy.split("://")[1].split("@")[0].split(":")[1],
                }
            else:
                self.options["proxy"] = {"server": self.proxy}

        self.options.update(options)

        if self.executable_path is not None:
            self.options["executable_path"] = self.executable_path

        self._thread_locals = threading.local()
        self._thread_locals.playwright = await async_playwright().start()
        self.playwright = self._thread_locals.playwright
        if kwargs.get("browser_instance_remote", True):
            self.browser = await self.playwright.chromium.connect(ws_endpoint='ws://localhost:3000/playwright')
        else:
            self.browser = await self.playwright.chromium.launch(
                    args=self.args, **self.options
            )
        context = await self._create_context(set_useragent=True)
        page = await context.new_page()
        if not self.device_mobile:
            await page.goto(self.web_url, wait_until='load')
            # Find Discover part on the left side
            # await page.wait_for_selector("p[data-e2e=nav-discover-title]")
            self.cookies = self.parsed_cookies(await context.cookies())

        await self.get_params(page)
        await context.close()

        return self

    async def get_params(self, page) -> None:
        self.browser_language = self.kwargs.get(
            "browser_language",
            await page.evaluate("""() => { return navigator.language; }"""),
        )
        self.browser_version = await page.evaluate(
            """() => { return window.navigator.appVersion; }"""
        )

        if len(self.browser_language.split("-")) == 0:
            self.region = self.kwargs.get("region", "US")
            self.language = self.kwargs.get("language", "en")
        elif len(self.browser_language.split("-")) == 1:
            self.region = self.kwargs.get("region", "US")
            self.language = self.browser_language.split("-")[0]
        else:
            self.region = self.kwargs.get("region", self.browser_language.split("-")[1])
            self.language = self.kwargs.get(
                "language", self.browser_language.split("-")[0]
            )

        self.timezone_name = self.kwargs.get(
            "timezone_name",
            await page.evaluate(
                """() => { return Intl.DateTimeFormat().resolvedOptions().timeZone; }"""
            ),
        )
        self.width = await page.evaluate("""() => { return screen.width; }""")
        self.height = await page.evaluate("""() => { return screen.height; }""")

    async def _create_context(self, set_useragent=False):
        if self.device_mobile:
            iphone = self.playwright.devices["iPhone 11 Pro"]
            iphone["viewport"] = {
                "width": random.randint(320, 1920),
                "height": random.randint(320, 1920),
            }
            iphone["device_scale_factor"] = random.randint(1, 3)
            iphone["is_mobile"] = random.randint(1, 2) == 1
            iphone["has_touch"] = random.randint(1, 2) == 1

            iphone["bypass_csp"] = True

            context = await self.browser.new_context(**iphone)
            if set_useragent:
                self.user_agent = iphone["user_agent"]
        else:
            # desktop_chrome = self.playwright.devices["Desktop Chrome"]
            # desktop_chrome["viewport"] = {
            #         "width":  2560,
            #         "height": 1440,
            # }
            context = await self.browser.new_context(viewport={"width": 2560, "height": 1440})
            if set_useragent:
                self.user_agent = "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
        return context

    @staticmethod
    def parsed_cookies(cookies):
        parsed = {}
        if cookies is not None:
            return dict(map(itemgetter("name", "value"), cookies))
        return parsed

    def _base36encode(self, number, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        """Converts an integer to a base36 string."""
        base36 = ""
        sign = ""

        if number < 0:
            sign = "-"
            number = -number

        if 0 <= number < len(alphabet):
            return sign + alphabet[number]

        while number != 0:
            number, i = divmod(number, len(alphabet))
            base36 = alphabet[i] + base36

        return sign + base36

    def gen_verifyFp(self):
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"[:]
        chars_len = len(chars)
        scenario_title = self._base36encode(int(time.time() * 1000))
        uuid = [0] * 36
        uuid[8] = "_"
        uuid[13] = "_"
        uuid[18] = "_"
        uuid[23] = "_"
        uuid[14] = "4"

        for i in range(36):
            if uuid[i] != 0:
                continue
            r = int(random.random() * chars_len)
            uuid[i] = chars[int((3 & r) | 8 if i == 19 else r)]

        return f'verify_{scenario_title.lower()}_{"".join(uuid)}'

    async def sign_url(self, url, calc_tt_params=False, **kwargs):
        api_req = kwargs.get("api_req", True)
        if api_req:
            async def process(route):
                await route.abort()

            tt_params = None
            context = await self._create_context()
            page = await context.new_page()

            # if calc_tt_params:
            #     await page.route(
            #         re.compile(r"(\.png)|(\.jpeg)|(\.mp4)|(x-expire)"), process
            #     )
            #     await page.goto(
            #         kwargs.get("default_url", "https://www.tiktok.com/@tiktok"),
            #         wait_until="load",
            #     )

            verifyFp = "".join(
                random.choice(
                    string.ascii_lowercase + string.ascii_uppercase + string.digits
                )
                for i in range(16)
            )
            if kwargs.get("gen_new_verifyFp", False):
                verifyFp = self.gen_verifyFp()
            else:
                verifyFp = kwargs.get("custom_verify_fp", verifyFp,)

            if kwargs.get("custom_device_id") is not None:
                device_id = kwargs.get("custom_device_id", None)
            elif self.device_id is None:
                device_id = str(random.randint(10000, 999999999))
            else:
                device_id = self.device_id

            url = "{}&verifyFp={}&device_id={}".format(url, verifyFp, device_id)

            # # Get x-tt-params
            if calc_tt_params:
                # await page.add_script_tag(content=_get_tt_params_script())
                tt_params_url = url + "&is_encryption=1"
                query_to_dict = dict(parse_qsl(urlparse(tt_params_url).query))
                if kwargs.get('tt_params_ord_lst', None):
                    try:
                        playload = {key : query_to_dict[key] for key in kwargs.get('tt_params_ord_lst')}
                    except KeyError as ke:
                        print(ke)
                        playload = query_to_dict
                else:
                    playload = query_to_dict

                # tt_params = await page.evaluate(
                #         """() => {
                #             return window.genXTTParams("""
                #         + json.dumps(playload)
                #         + """);
                #                 }"""
                # )
                tt_params = encrypt_tt_param_v2(playload)
                print(f"req parameter --> x-tt-params: {tt_params}")

            # # Get _signature
            await page.add_script_tag(content=_get_acrawler())
            # await page.add_script_tag(content=_get_signer_script())
            signature = await page.evaluate(
                '''() => {
                var url = "'''
                + url
                + """"
                var token = window.byted_acrawler.sign({url: url});
                
                return token;
                }"""
            )
            print(f"req parameter --> _signature: {signature}")
            url = "{}&_signature={}".format(url, signature)


            # # FIXME: Get x-bogus
            # try:
            #     await page.add_script_tag(content=_get_webmssdk_script())
            #     x_bogus = await page.evaluate(
            #             '''() => {
            #                 var params = "'''
            #                 + str(urlparse(url).query) + ";"
            #                 + """"
            #                 window.byted_acrawler.init({aid: 24,dfp: true,});
            #                 var token = window._0x32d649(params);
            #                 return token;
            #             }"""
            #     )
            # except (SyntaxError, TypeError) as ex:
            #     x_bogus = "DFSzswVL-XGANHVWS0OnS2XyYJUm"
            x_bogus = "DFSzswVL-XGANHVWS0OnS2XyYJUm"

            print(f"req parameter --> X-Bogus: {x_bogus}")
            url = "{}&X-Bogus={}".format(url, x_bogus)

            await context.close()
            return (verifyFp, device_id, signature, x_bogus, tt_params)
        else:
            try:
                context = await self._create_context()
                page = await context.new_page()

                await page.goto(url, wait_until='load')
                # Find Discover part on the left side
                # await page.wait_for_selector("p[data-e2e=nav-discover-title]")
                # await page.pause()
                page_html = await page.content()

                await context.close()
                return page_html
            except Exception:
                raise Exception()

    async def _clean_up(self):
        await self.browser.close()
        await self.playwright.stop()

    def find_redirect(self, url):
        self.page.goto(url, {"waitUntil": "load"})
        self.redirect_url = self.page.url

    def __format_proxy(self, proxy):
        if proxy is not None:
            return {"http": proxy, "https": proxy}
        else:
            return None

    def __get_js(self):
        return requests.get(
            "https://sf16-muse-va.ibytedtos.com/obj/rc-web-sdk-gcs/acrawler.js",
            proxies=self.__format_proxy(self.proxy),
        ).text
