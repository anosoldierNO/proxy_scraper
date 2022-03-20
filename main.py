import json
import random
import re
import time
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum, auto

import requests


TIMEOUT = 10
IP_REGEX = r'[0-9]+(?:\.[0-9]+){3}'
PORT_REGEX = r'[0-9]+'
IP_PORT_REGEX = rf'({IP_REGEX}):({PORT_REGEX})'
IP_PORT_TABLE_REGEX = rf'({IP_REGEX})\s*</td>\s*<td>\s*({PORT_REGEX})'


class Proto(Enum):
    HTTP = auto()
    SOCKS4 = auto()
    SOCKS5 = auto()


@dataclass(frozen=True)
class Proxy:
    ip: str
    port: str
    proto: Proto

    def to_str(self):
        scheme = {
            Proto.HTTP: 'http',
            Proto.SOCKS4: 'socks4',
            Proto.SOCKS5: 'socks5',
        }[self.proto]
        return f'{scheme}://{self.ip}:{self.port}'


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1',
    'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
]


def get_headers():
    return {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'User-Agent': random.choice(USER_AGENTS),
        'Referer': 'https://www.google.com/',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Sec-Gpc': '1',
        'Upgrade-Insecure-Requests': '1',
    }


class Provider:
    def __init__(self, url, proto):
        self.url = url
        self.proto = proto

    def scrape(self):
        return self.parse(self.fetch(self.url))

    def fetch(self, url):
        response = requests.get(url=url, timeout=TIMEOUT, headers=get_headers())
        response.raise_for_status()
        return response.text

    def parse(self, data):
        raise NotImplementedError

    def __str__(self):
        return f'{self.proto} | {self.url}'


class RegexProvider(Provider):
    def __init__(self, url, proto, regex):
        super().__init__(url, proto)
        self.regex = regex

    def parse(self, data):
        for ip, port in re.findall(self.regex, data):
            yield Proxy(ip, port, self.proto)


class PubProxyProvider(RegexProvider):
    def __init__(self, url, proto, regex=IP_PORT_REGEX):
        super().__init__(url, proto, regex)

    def scrape(self):
        for _ in range(10):
            yield from super().scrape()
            time.sleep(1)


class GeonodeProvider(Provider):
    def parse(self, data):
        data = json.loads(data)
        for row in data['data']:
            yield Proxy(row['ip'], row['port'], self.proto)


class HideMyNameProvider(RegexProvider):
    def __init__(self, url, proto, regex=IP_PORT_TABLE_REGEX, pages=(1, 10)):
        self.pages = pages
        super().__init__(url, proto, regex)

    def scrape(self):
        for page in range(*self.pages):
            url = self.url
            if page != 1:
                url = url + '&start=' + str(64 * (page - 1))

            result = list(self.parse(self.fetch(url)))
            if not result:
                return

            yield from result


class ProxyListProvider(RegexProvider):
    def __init__(self, url, proto, regex=r"Proxy\('([\w=]+)'\)"):
        super().__init__(url, proto, regex)

    def scrape(self):
        for page in range(1, 20):
            url = self.url + '?p=' + str(page)
            result = list(self.parse(self.fetch(url)))
            if not result:
                return
            yield from result
            time.sleep(1)

    def parse(self, data):
        for proxy in re.findall(self.regex, data):
            ip, port = b64decode(proxy).decode().split(':')
            yield Proxy(ip, port, self.proto)


# noinspection LongLine
PROVIDERS = [
    # SOCKS4
    RegexProvider('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://api.proxyscrape.com/?request=displayproxies&proxytype=socks4', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://www.proxy-list.download/api/v1/get?type=socks4', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://www.my-proxy.com/free-socks-4-proxy.html', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://www.socks-proxy.net/', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://www.freeproxychecker.com/result/socks4_proxies.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('http://proxydb.net/?protocol=socks4', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://api.openproxylist.xyz/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://socks-proxy.net/', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/human1ty/proxy/main/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),
    RegexProvider('https://openproxy.space/list/socks4', Proto.SOCKS4, f'"{IP_PORT_REGEX}"'),
    PubProxyProvider('http://pubproxy.com/api/proxy?limit=5&format=txt&type=socks4', Proto.SOCKS4),
    RegexProvider('https://www.proxy-list.download/SOCKS4', Proto.SOCKS4, IP_PORT_TABLE_REGEX),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=fast&protocols=socks4', Proto.SOCKS4),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=medium&protocols=socks4', Proto.SOCKS4),
    HideMyNameProvider('https://hidemy.name/ru/proxy-list/?type=4', Proto.SOCKS4),
    RegexProvider('http://www.proxylists.net/socks4.txt', Proto.SOCKS4, IP_PORT_REGEX),

    # SOCKS5
    RegexProvider('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://api.proxyscrape.com/?request=displayproxies&proxytype=socks5', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/manuGMG/proxy-365/main/SOCKS5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://spys.me/socks.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://www.my-proxy.com/free-socks-5-proxy.html', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('http://proxydb.net/?protocol=socks5', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://www.proxy-list.download/api/v1/get?type=socks5', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://api.openproxylist.xyz/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/human1ty/proxy/main/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://openproxy.space/list/socks5', Proto.SOCKS5, f'"{IP_PORT_REGEX}"'),
    PubProxyProvider('http://pubproxy.com/api/proxy?limit=5&format=txt&type=socks5', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('https://www.proxy-list.download/SOCKS5', Proto.SOCKS5, IP_PORT_TABLE_REGEX),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=fast&protocols=socks5', Proto.SOCKS5),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=medium&protocols=socks5', Proto.SOCKS5),
    RegexProvider('https://www.freeproxychecker.com/result/socks5_proxies.txt', Proto.SOCKS5, IP_PORT_REGEX),
    RegexProvider('http://www.proxylists.net/socks5.txt', Proto.SOCKS5, IP_PORT_REGEX),
    HideMyNameProvider('https://hidemy.name/ru/proxy-list/?type=5', Proto.SOCKS5),

    # HTTP(S)
    RegexProvider('https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://api.proxyscrape.com/?request=displayproxies&proxytype=http', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/almroot/proxylist/master/list.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http%2Bhttps.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/http%2Bs.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.proxy-list.download/api/v1/get?type=http', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.proxy-list.download/api/v1/get?type=https', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://spys.me/proxy.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.sslproxies.org/', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.my-proxy.com/free-proxy-list.html', Proto.HTTP, IP_PORT_REGEX),
    *(
        RegexProvider(f'https://www.my-proxy.com/free-proxy-list-{i}.html', Proto.HTTP, IP_PORT_REGEX)
        for i in range(2, 11)
    ),
    RegexProvider('https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://proxydb.net/?protocol=http&protocol=https', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://api.openproxylist.xyz/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://www.google-proxy.net/', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://free-proxy-list.net/', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.us-proxy.org/', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://free-proxy-list.net/uk-proxy.html', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://free-proxy-list.net/anonymous-proxy.html', Proto.HTTP, IP_PORT_REGEX),
    PubProxyProvider('http://pubproxy.com/api/proxy?limit=5&format=txt&type=http', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://www.proxylists.net/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://raw.githubusercontent.com/human1ty/proxy/main/http.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://pastebin.com/raw/vQzZ8CwG', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://openproxy.space/list/http', Proto.HTTP, f'"{IP_PORT_REGEX}"'),
    RegexProvider('https://www.proxy-list.download/HTTPS', Proto.HTTP, IP_PORT_TABLE_REGEX),
    RegexProvider('https://www.proxy-list.download/HTTP', Proto.HTTP, IP_PORT_TABLE_REGEX),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=fast&protocols=http%2Chttps', Proto.HTTP),
    GeonodeProvider('https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&speed=medium&protocols=http%2Chttps', Proto.HTTP),
    RegexProvider('https://wwwDi 22-03-2022 19:40 2 (+1).freeproxychecker.com/result/http_proxies.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://www.httptunnel.ge/ProxyListForFree.aspx', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('http://api.foxtools.ru/v2/Proxy.txt', Proto.HTTP, IP_PORT_REGEX),
    RegexProvider('https://www.ipaddress.com/proxy-list/', Proto.HTTP, rf'({IP_REGEX})</a>:({PORT_REGEX})'),
    ProxyListProvider('https://proxy-list.org/english/index.php', Proto.HTTP),
    *(
        HideMyNameProvider(
            'https://hidemy.name/ru/proxy-list/?type=hs',
            Proto.HTTP,
            pages=(start, start + 20)
        )
        for start in range(1, 200, 20)
    ),
]


def scrape_all():
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {
            executor.submit(provider.scrape): provider
            for provider in PROVIDERS
        }
        for future in as_completed(futures):
            try:
                yield from future.result()
            except Exception as exc:
                print(futures[future], exc)
            else:
                print('Success', futures[future])


def update_file():
    expected_at_least = 20000
    proxies = set(scrape_all())
    if len(proxies) < expected_at_least:
        print(f'Found too few proxies: {len(proxies)}')
        exit(1)
    with open('proxies.txt', 'w') as out:
        out.writelines((proxy.to_str() + '\n' for proxy in proxies))


if __name__ == '__main__':
    update_file()


# <proxybroker.providers.Proxylist_download object at 0x7fe3577e03a0> 1957
# <proxybroker.providers.Freeproxylists_com object at 0x7fe3577e01f0> 0
# <proxybroker.providers.Xseo_in object at 0x7fe359b8be50> 45
# <proxybroker.providers.Webanetlabs_net object at 0x7fe3577e0280> 0
# <proxybroker.providers.Blogspot_com_socks object at 0x7fe357b45e50> 100
# <proxybroker.providers.Foxtools_ru object at 0x7fe357b0ef70> 73
# <proxybroker.providers.Nntime_com object at 0x7fe357b45820> 745
# <proxybroker.providers.My_proxy_com object at 0x7fe3577e0040> 0
# <proxybroker.providers.Tools_rosinstrument_com_socks object at 0x7fe357b45f70> 0
# <proxybroker.providers.Gatherproxy_com_socks object at 0x7fe357b45dc0> 0
# <proxybroker.providers.Gatherproxy_com object at 0x7fe357b45400> 0
# <proxybroker.providers.Blogspot_com object at 0x7fe357b45d30> 6522
# <proxybroker.providers.Tools_rosinstrument_com object at 0x7fe357b45ee0> 0
# <proxybroker.providers.Maxiproxies_com object at 0x7fe3577e0310> 0
# <proxybroker.providers.Proxylistplus_com object at 0x7fe359b8bbb0> 491
# <proxybroker.providers.Checkerproxy_net object at 0x7fe3577e00d0> 0
# <proxybroker.providers.Aliveproxy_com object at 0x7fe3577e0160> 0
