from lxml import html
from urllib.parse import urljoin
from abc import ABC, abstractmethod

KEY_QUERIER_MODE = 'mode'
KEY_QUERIER_DRIVER = 'driver'
KEY_QUERIER_ARGSLINE = 'argsline'
KEY_QUERIER_CACHED = 'cached'
KEY_URL = 'url'
KEY_PAGERS = 'pagers'
KEY_PAGERS_ACTION = 'action'
KEY_PAGERS_VALUE = 'value'
QUERIER_PLAIN = 'plain'
QUERIER_SECURE = 'secure'
QUERIER_DYNAMIC = 'dynamic'

class DataQuerier(ABC):
  @abstractmethod
  def __enter__(self):
    raise NotImplementedError
  @abstractmethod
  def __exit__(self, type, value, tb):
    raise NotImplementedError
  @abstractmethod
  def get_content(self, link):
    raise NotImplementedError
  @abstractmethod
  def post_content(self, link):
    raise NotImplementedError
  def get(self, link):
      return html.fromstring(self.get_content(link))
  def post(self, link):
      return html.fromstring(self.post_content(link))
  def pages(self, scrape_profile):
    url = scrape_profile[KEY_URL]
    tree = self.get(url)
    data = DataQuerier.PageData(tree, self, url)
    yield data
    if KEY_PAGERS not in scrape_profile: return
    pagers_value = scrape_profile[KEY_PAGERS]
    if isinstance(pagers_value, dict): return
    while True:
      pagers = tree.xpath(pagers_value)
      if pagers:
        url = data.rebase_link(str(pagers[0].attrib['href']))
        tree = self.get(url)
        data = DataQuerier.PageData(tree, self, url)
        yield data
      else:
        break
  @staticmethod
  def Create(querierconfig):
    mode = querierconfig[KEY_QUERIER_MODE] if KEY_QUERIER_MODE in querierconfig else QUERIER_PLAIN
    cached = querierconfig[KEY_QUERIER_CACHED] if KEY_QUERIER_CACHED in querierconfig else False
    if mode == QUERIER_SECURE: querier = SecureDataQuerier()
    elif mode == QUERIER_PLAIN: querier = PlainDataQuerier()
    elif mode == QUERIER_DYNAMIC: querier = DynamicDataQuerier(querierconfig)
    else: raise KeyError(mode)
    if cached:
      querier = CachedDataQuerier(querier)
    return querier
  class PageData(object):
    def __init__(self, tree, querier, url):
      self.__tree = tree
      self.__querier = querier
      self.__url = url
    def rebase_link(self, link):
      if link.startswith('#'):
        link = self.__url + link
      else:
        link = urljoin(self.__url, link)
      return link
    def xpath(self, query):
      return self.__tree.xpath(query)
    def get(self, link):
      return html.fromstring(self.__querier.get_content(self.rebase_link(link)))

class PlainDataQuerier(DataQuerier):
  def __init__(self):
    from requests import get, post
    self.__get = get
    self.__post = post
  def __enter__(self):
    return self
  def __exit__(self, type, value, tb):
    pass
  def get_content(self, link):
    return self.__get(link).content
  def post_content(self, link):
    return self.__post(link).content

class SecureDataQuerier(DataQuerier):
  def __enter__(self):
    from requests import Session
    from torpy import TorClient
    from torpy.http.adapter import TorHttpAdapter
    self.tor = TorClient()
    self.guard = self.tor.get_guard()
    self.adapter = TorHttpAdapter(self.guard, 3)
    self.request = Session()
    self.request.headers.update({'User-Agent': 'Mozilla/5.0'})
    self.request.mount('http://', self.adapter)
    self.request.mount('https://', self.adapter)
    self.__get = self.request.get
    self.__post = self.request.post
    return self
  def __exit__(self, type, value, tb):
    self.request.close()
    self.adapter.close()
    self.guard.close()
    self.tor.close()
  def get_content(self, link):
    from torpy.guard import GuardState
    if not self.guard or self.guard._state != GuardState.Connected: raise RuntimeError
    return self.__get(link).content
  def post_content(self, link):
    from torpy.guard import GuardState
    if not self.guard or self.guard._state != GuardState.Connected: raise RuntimeError
    return self.__post(link).content

class DynamicDataQuerier(DataQuerier):
  def __init__(self, querierconfig):
    super().__init__()
    from importlib import import_module
    webdriver = import_module('selenium.webdriver')
    drivername = querierconfig[KEY_QUERIER_DRIVER]
    self.__driverFactory = getattr(webdriver, drivername)
    self.__args = None
    if KEY_QUERIER_ARGSLINE in querierconfig:
      options = getattr(webdriver, '%sOptions' % drivername)
      self.__args = options()
      self.__args.add_argument(querierconfig[KEY_QUERIER_ARGSLINE])
  def __enter__(self):
    self.__driver = self.__driverFactory(options=self.__args)
    return self
  def __exit__(self, type, value, tb):
    self.__driver.quit()
  def get_content(self, link):
    self.__driver.get(link)
    return self.__driver.find_element_by_tag_name('html').get_attribute('outerHTML')
  def post_content(self, link):
    self.__driver.post(link)
    return self.__driver.find_element_by_tag_name('html').get_attribute('outerHTML')
  def pages(self, scrape_profile):
    if KEY_PAGERS in scrape_profile and isinstance(scrape_profile[KEY_PAGERS], dict):
      url = scrape_profile[KEY_URL]
      pagers_config = scrape_profile[KEY_PAGERS]
      action = pagers_config[KEY_PAGERS_ACTION]
      value = pagers_config[KEY_PAGERS_VALUE]
      self.__driver.get(url)
      while True:
        paging = self.__driver.find_element_by_xpath(value)
        if paging:
          getattr(paging, action)()
        else:
          break
      tree = html.fromstring(self.__driver.page_source)
      yield DataQuerier.PageData(tree, self, url)
    else:
      for page in super().pages(scrape_profile):
        yield page

class CachedDataQuerier(DataQuerier):
  def __init__(self, querier):
    self.__querier = querier
    self.__cached_content = {
      "get": {},
      "post": {}
    }
  def __enter__(self):
    self.__querier.__enter__()
    return self
  def __exit__(self, type, value, tb):
    self.__querier.__exit__(type, value, tb)
  def get_content(self, link):
    cached_content = self.__cached_content["get"]
    if link not in cached_content:
      cached_content[link] = self.__querier.get_content(link)
    return cached_content[link]
  def post_content(self, link):
    cached_content = self.__cached_content["post"]
    if link not in cached_content:
      cached_content[link] = self.__querier.post_content(link)
    return cached_content[link]
