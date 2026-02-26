from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import caldav
import requests
import vobject

T = TypeVar("T")

class Manager(ABC, Generic[T]):
    def __init__(self, webdav_url: str, username: str, password: str):
        if not webdav_url.endswith("/"):
            webdav_url += "/"
        self.base = webdav_url
        self.auth = (username, password)
        self.client = caldav.DAVClient(self.base, username=username, password=password)

    @abstractmethod
    def list(self, *args, **kwargs) -> list[T]:
        raise NotImplementedError

    @abstractmethod
    def add(self, *args, **kwargs) -> T:
        raise NotImplementedError

    @abstractmethod
    def delete(self, item: T) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self, item: T, *args, **kwargs) -> T:
        raise NotImplementedError

    @abstractmethod
    def summary(self, *args, **kwargs) -> str:
        raise NotImplementedError

    @abstractmethod
    def get(self, uid: str) -> T:
        raise NotImplementedError

    def request(self, url: str, **kwargs):
        r = requests.get(url, auth=self.auth, timeout=20, **kwargs)
        r.raise_for_status()
        return vobject.readOne(r.text)

    @staticmethod
    def display(item: T) -> str:
        """
        Default: dump the raw DAV representation (ICS/VCF) if possible.
        Managers may override to provide a prettier view.
        """
        if hasattr(item, "data"):
            return item.data
        return item.serialize()

