from __future__ import annotations

import json
import requests

from urllib.parse import quote, urlencode
from parsel import Selector

from ..exceptions import *
from ..helpers import extract_tag_contents, deep_get, parse_url

from typing import TYPE_CHECKING, ClassVar, Iterator, Optional

if TYPE_CHECKING:
    from ..tiktok import TikTokApi
    from .video import Video


class User:
    """
    A TikTok User.

    Example Usage
    ```py
    user = api.user(username='therock')
    # or
    user_id = '5831967'
    sec_uid = 'MS4wLjABAAAA-VASjiXTh7wDDyXvjk10VFhMWUAoxr8bgfO1kAL1-9s'
    user = api.user(user_id=user_id, sec_uid=sec_uid)
    ```

    """

    parent: ClassVar[TikTokApi]

    user_id: str
    """The user ID of the user."""
    sec_uid: str
    """The sec UID of the user."""
    username: str
    """The username of the user."""
    as_dict: dict
    """The raw data associated with this user."""

    def __init__(
        self,
        username: Optional[str] = None,
        user_id: Optional[str] = None,
        sec_uid: Optional[str] = None,
        data: Optional[dict] = None,
    ):
        """
        You must provide the username or (user_id and sec_uid) otherwise this
        will not function correctly.
        """
        self.__update_id_sec_uid_username(user_id, sec_uid, username)
        if data is not None:
            self.as_dict = data
            self.__extract_from_data()

    def info(self, **kwargs):
        """
        Returns a dictionary of TikTok's User object

        Example Usage
        ```py
        user_data = api.user(username='therock').info()
        ```
        """
        return self.info_full(**kwargs)["user"]

    def info_full(self, **kwargs) -> dict:
        """
        Returns a dictionary of information associated with this User.
        Includes statistics about this user.

        Example Usage
        ```py
        user_data = api.user(username='therock').info_full()
        ```
        """

        # TODO: Find the one using only user_id & sec_uid
        if not self.username:
            raise TypeError(
                "You must provide the username when creating this class to use this method."
            )
        quoted_username = quote(self.username)
        try:
            page_html = User.parent.get_html("https://www.tiktok.com/@{}?lang=en".format(quoted_username),
                                             **kwargs)

            sel = Selector(text=page_html)
            js_json_text = sel.xpath("//script[contains(@id, 'SIGI_STATE')]/text()").extract_first('').strip()
            json_results = json.loads(js_json_text)

            # # uncomment these lines for debug
            # file_name = f'{self.username}-tiktok-stats-data.json'
            # with open(file_name, 'w', encoding='utf-8') as f:
            #     json.dump(js_json_text, f, ensure_ascii=False, sort_keys=True, indent=4)

            try:
                unique_id = deep_get(json_results, 'UserPage.uniqueId')
                sec_uid = deep_get(json_results, 'UserPage.secUid')
                self.user_id = unique_id
                self.sec_uid = sec_uid

                user_stats = deep_get(json_results, f'UserModule.stats.{unique_id}')
                user_info = deep_get(json_results, f'UserModule.users.{unique_id}')

                user_stats = dict(unique_id=unique_id,
                                  sec_uid=sec_uid,
                                  user_info=user_info,
                                  user_stats=user_stats,
                                  )
                user_posts = []
                if kwargs.get("include_video", True):
                    videos_list = deep_get(json_results, 'ItemModule')
                    user_posts = [item for _, item in videos_list.items()]

                return dict(user=dict(
                        stats=user_stats,
                        posts=user_posts
                ))
            except (ValueError, IndexError):
                return {}

        except HTMLNotAvailableException as ex:
            # Fetch cookies
            spawn = requests.head(
                    "https://www.tiktok.com",
                    proxies=User.parent._format_proxy(kwargs.get("proxy", None)),
                    **User.parent._requests_extra_kwargs,
                    headers={'User-Agent': User.parent._user_agent_pc}
            )

            r = requests.get(
                "https://tiktok.com/@{}?lang=en".format(quoted_username),
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                    "path": "/@{}".format(quoted_username),
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "User-Agent": User.parent._user_agent,
                },
                proxies=User.parent._format_proxy(kwargs.get("proxy", None)),
                cookies=spawn.cookies,
                **User.parent._requests_extra_kwargs,
            )
            data = extract_tag_contents(r.text)
            user = json.loads(data)

            user_props = user["props"]["pageProps"]
            if user_props["statusCode"] == 404:
                raise NotFoundException(
                    "TikTok user with username {} does not exist".format(self.username)
                )
            return user_props["userInfo"]
        except CaptchaException as ex:
            # There is a route for user info, but uses msToken
            processed = User.parent._process_kwargs(kwargs)
            kwargs["custom_device_id"] = processed.device_id

            query = {
                "uniqueId": self.user_id,
                "secUid": "",
                # "msToken": User.parent._get_cookies()["msToken"]
            }

            path = "api/user/detail/?{}&{}".format(
                User.parent._add_url_params(), urlencode(query)
            )

            res = User.parent.get_data(path, subdomain="m", **kwargs)
            # print(res)

            return res["userInfo"]

    def videos(self, count: int = 30, cursor: int = 0,
               get_all: bool = False, **kwargs) -> Iterator[Video]:
        """
        Returns an iterator yielding Video objects.

        - Parameters:
            - count (int): The amount of videos you want returned.
            - cursor (int): The unix epoch to get uploaded videos since.
            - get_all (bool): Retrieve all videos

        Example Usage
        ```py
        user = api.user(username='therock')
        for video in user.videos(count=100):
            # do something
        ```
        """
        processed = User.parent._process_kwargs(kwargs)
        kwargs["custom_device_id"] = processed.device_id

        if not self.user_id and not self.sec_uid:
            self.__find_attributes()

        first = True
        amount_yielded = 0

        while get_all or amount_yielded < count:
            query = {
                "count": 30,
                "id": self.user_id,
                "cursor": cursor,
                "type": 1,
                "secUid": self.sec_uid,
                "sourceType": 8,
                "appId": 1233,
                "region": processed.region,
                "priority_region": processed.region,
                "language": processed.language,
            }
            path = "api/post/item_list/?{}&{}".format(
                User.parent._add_url_params(), urlencode(query)
            )

            res = User.parent.get_data(path, send_tt_params=True, **kwargs)

            videos = res.get("itemList", [])
            for video in videos:
                amount_yielded += 1
                yield self.parent.video(data=video)

            if not res.get("hasMore", False) and not first:
                User.parent.logger.info(
                    "TikTok isn't sending more TikToks beyond this point."
                )
                return

            cursor = res["cursor"]
            first = False

    def liked(self, count: int = 30, cursor: int = 0,
              get_all: bool = False, **kwargs) -> Iterator[Video]:
        """
        Returns a dictionary listing TikToks that a given a user has liked.

        **Note**: The user's likes must be **public** (which is not the default option)

        - Parameters:
            - count (int): The amount of videos you want returned.
            - cursor (int): The unix epoch to get uploaded videos since.
            - get_all (bool): Retrieve all liked

        Example Usage
        ```py
        for liked_video in api.user(username='public_likes'):
            # do something
        ```
        """
        processed = User.parent._process_kwargs(kwargs)
        kwargs["custom_device_id"] = processed.device_id

        amount_yielded = 0
        first = True

        if self.user_id is None and self.sec_uid is None:
            self.__find_attributes()

        while get_all or amount_yielded < count:
            query = {
                "count": 30,
                "id": self.user_id,
                "type": 2,
                "secUid": self.sec_uid,
                "cursor": cursor,
                "sourceType": 9,
                "appId": 1233,
                "region": processed.region,
                "priority_region": processed.region,
                "language": processed.language,
            }
            path = "api/favorite/item_list/?{}&{}".format(
                User.parent._add_url_params(), urlencode(query)
            )

            res = self.parent.get_data(path, **kwargs)

            if "itemList" not in res.keys():
                if first:
                    User.parent.logger.error("User's likes are most likely private")
                return

            videos = res.get("itemList", [])
            for video in videos:
                amount_yielded += 1
                yield self.parent.video(data=video)

            if not res.get("hasMore", False) and not first:
                User.parent.logger.info(
                    "TikTok isn't sending more TikToks beyond this point."
                )
                return

            cursor = res["cursor"]
            first = False

    def __extract_from_data(self):
        data = self.as_dict
        keys = data.keys()

        if "user_info" in keys:
            self.__update_id_sec_uid_username(
                data["user_info"]["uid"],
                data["user_info"]["sec_uid"],
                data["user_info"]["unique_id"],
            )
        elif "uniqueId" in keys:
            self.__update_id_sec_uid_username(
                data["id"], data["secUid"], data["uniqueId"]
            )

        if None in (self.username, self.user_id, self.sec_uid):
            User.parent.logger.error(
                f"Failed to create User with data: {data}\nwhich has keys {data.keys()}"
            )

    def __update_id_sec_uid_username(self, id, sec_uid, username):
        self.user_id = id
        self.sec_uid = sec_uid
        self.username = username

    def __find_attributes(self) -> None:
        # It is more efficient to check search first, since self.user_object() makes HTML request.
        found = False
        for u in self.parent.search.users(self.username):
            if u.username == self.username:
                found = True
                self.__update_id_sec_uid_username(u.user_id, u.sec_uid, u.username)
                break

        if not found:
            user_object = self.info()
            self.__update_id_sec_uid_username(
                user_object["id"], user_object["secUid"], user_object["uniqueId"]
            )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"TikTokApi.user(username='{self.username}', user_id='{self.user_id}', sec_uid='{self.sec_uid}')"

    def __getattr__(self, name):
        if name in ["as_dict"]:
            self.as_dict = self.info()
            self.__extract_from_data()
            return self.__getattribute__(name)

        raise AttributeError(f"{name} doesn't exist on TikTokApi.api.User")
