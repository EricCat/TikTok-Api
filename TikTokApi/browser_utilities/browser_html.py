import logging
from operator import itemgetter
from .browser_interface import BrowserInterface
import threading
from ..utilities import LOGGER_NAME
from playwright.async_api import async_playwright

logger = logging.getLogger(LOGGER_NAME)


class browserHTML(BrowserInterface):

    def __init__(self, **kwargs):
        pass

    @staticmethod
    async def create(
        **kwargs,
    ):
        self = browserHTML()
        self.kwargs = kwargs
        self.debug = kwargs.get("debug", False)
        self.proxy = kwargs.get("proxy", None)
        self.url = kwargs.get("url", "https://www.tiktok.com/@disneys_2")
        self.referrer = kwargs.get("referer", "https://www.tiktok.com/")
        self.language = kwargs.get("language", "en")
        self.executable_path = kwargs.get("executable_path", None)
        self.device_id = kwargs.get("custom_device_id", None)

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
        self.browser = await self.playwright.chromium.launch(
            args=self.args, **self.options
        )
        context = await self._create_context()
        page = await context.new_page()
        await page.goto(self.url, wait_until='load')
        # Find Discover part on the left side
        await page.wait_for_selector("p[data-e2e=nav-discover-title]")
        self.cookies = self.parsed_cookies(await context.cookies())
        await self.get_params(page)
        await context.close()

        return self

    async def _create_context(self):
        context = await self.browser.new_context(viewport={"width": 2560, "height": 1440})
        return context

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

    @staticmethod
    def parsed_cookies(cookies):
        parsed = {}
        if cookies is not None:
            return dict(map(itemgetter("name", "value"), cookies))
            # for item in cookies:
            #     if item["name"] == "ttwid":
            #         parsed["ttwid"] = item["value"]
            #     if item["name"] == "tt_csrf_token":
            #         parsed["tt_csrf_token"] = item["value"]
            #     if item["name"] == "tt_chain_token":
            #         parsed["tt_chain_token"] = item["value"]
            #     if item["name"] == "msToken":
            #         parsed["msToken"] = item["value"]
        return parsed

    async def sign_url(self, url,  calc_tt_params=False, **kwargs):
        context = await self._create_context()
        page = await context.new_page()

        await page.goto(url, wait_until='load')
        # Find Discover part on the left side
        await page.wait_for_selector("p[data-e2e=nav-discover-title]")
        page_html = await page.content()

        await context.close()
        return page_html

    async def _clean_up(self):
        await self.browser.close()
        await self.playwright.stop()
