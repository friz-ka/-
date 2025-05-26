import requests
import time
import re
from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urljoin, urlparse
import sys
import threading

class WikipediaPathFinder:
    def __init__(self, rate_limit=10):
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WikipediaPathFinder/1.0 (Educational Purpose)'
        })
        self.cache = {}
        self.semaphore = threading.Semaphore(rate_limit)
        self.request_times = deque()

    def _rate_limit_request(self):
        """Ограничение скорости запросов"""
        current_time = time.time()

        while self.request_times and current_time - self.request_times[0] > 1:
            self.request_times.popleft()

        if len(self.request_times) >= self.rate_limit:
            sleep_time = 1 - (current_time - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.request_times.append(current_time)

    def get_page_content(self, url):
        """Получение содержимого страницы с кешированием"""
        if url in self.cache:
            return self.cache[url]

        with self.semaphore:
            self._rate_limit_request()

            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()

                self.cache[url] = response.text
                return response.text

            except requests.RequestException as e:
                print(f"Ошибка при получении {url}: {e}")
                return None

    def extract_wikipedia_links(self, html_content, base_url):
        """Извлечение ссылок на Wikipedia из основного содержимого и References"""
        if not html_content:
            return set()

        soup = BeautifulSoup(html_content, 'html.parser')
        links = set()

        parsed_url = urlparse(base_url)
        wiki_domain = parsed_url.netloc

        main_content = soup.find('div', {'id': 'mw-content-text'})
        if main_content:
            for element in main_content.find_all(
                    ['div'], class_=[
                        'navbox',
                        'infobox',
                        'metadata',
                        'ambox',
                    ]
            ):
                element.decompose()

            content_div = main_content.find('div', class_='mw-parser-output')
            if content_div:
                for p in content_div.find_all(['p', 'li']):
                    for link in p.find_all('a', href=True):
                        href = link['href']
                        if self._is_valid_wikipedia_link(href, wiki_domain):
                            full_url = urljoin(base_url, href)
                            links.add(full_url)

        references_section = soup.find('span', {'id': 'References'})
        if not references_section:
            references_section = soup.find(
                'h2',
                string=re.compile(r'References|Примечания|Источники'),
            )

        if references_section:
            current = references_section.parent if references_section.parent else references_section
            while current and current.next_sibling:
                current = current.next_sibling
                if hasattr(current, 'find_all'):
                    for link in current.find_all('a', href=True):
                        href = link['href']
                        if self._is_valid_wikipedia_link(href, wiki_domain):
                            full_url = urljoin(base_url, href)
                            links.add(full_url)
                    if current.name == 'h2':
                        break

        return links

    def _is_valid_wikipedia_link(self, href, wiki_domain):
        """Проверка, является ли ссылка валидной ссылкой на статью Wikipedia"""
        if not href:
            return False

        if href.startswith('/wiki/'):
            excluded_prefixes = [
                'File:', 'Category:', 'Template:', 'Help:', 'Special:',
                'User:', 'Wikipedia:', 'Talk:', 'User_talk:', 'Wikipedia_talk:',
                'Template_talk:', 'Help_talk:', 'Category_talk:', 'Portal:',
                'Файл:', 'Категория:', 'Шаблон:', 'Справка:', 'Участник:',
                'Обсуждение:', 'Служебная:', 'Портал:'
            ]

            if '#' in href:
                return False

            for prefix in excluded_prefixes:
                if href.startswith(f'/wiki/{prefix}'):
                    return False

            return True

        if wiki_domain in href and '/wiki/' in href:
            return self._is_valid_wikipedia_link(
                href.split('/wiki/')[-1],
                wiki_domain,
            )

        return False

    def normalize_url(self, url):
        """Нормализация URL для сравнения"""
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return normalized.rstrip('/')

    def find_path(self, start_url, target_url, max_depth=5):
        """Поиск пути между двумя статьями Wikipedia с использованием BFS"""
        start_url = self.normalize_url(start_url)
        target_url = self.normalize_url(target_url)

        if start_url == target_url:
            return [start_url]

        visited = set()
        queue = deque([(start_url, [start_url])])
        visited.add(start_url)

        while queue:
            current_url, path = queue.popleft()

            if len(path) > max_depth:
                continue

            print(f"Обрабатываю: {current_url} (глубина: {len(path)})")

            content = self.get_page_content(current_url)
            if not content:
                continue

            links = self.extract_wikipedia_links(content, current_url)

            for link in links:
                normalized_link = self.normalize_url(link)

                if normalized_link == target_url:
                    return path + [normalized_link]

                if normalized_link not in visited and len(path) < max_depth:
                    visited.add(normalized_link)
                    queue.append((normalized_link, path + [normalized_link]))

        return None

    def find_bidirectional_path(self, url1, url2, max_depth=5):
        """Поиск пути в обоих направлениях"""
        print(f"Поиск пути от {url1} к {url2}")
        path1to2 = self.find_path(url1, url2, max_depth)

        print(f"\nПоиск пути от {url2} к {url1}")
        path2to1 = self.find_path(url2, url1, max_depth)

        return path1to2, path2to1

def format_path(path):
    """Форматирование пути для вывода с реальными URL"""
    if not path:
        return None

    if len(path) == 1:
        return path[0]

    formatted_links = []
    for i, url in enumerate(path):
        if i == 0 or i == len(path) - 1:
            formatted_links.append(url)
        else:
            formatted_links.append(f"[{url}]")

    return " => ".join(formatted_links)

def main():
    if len(sys.argv) != 4:
        print("Использование: python script.py <url1> <url2> <rate_limit>")
        print("Пример: python script.py 'https://en.wikipedia.org/wiki/Six_degrees_of_separation' 'https://en.wikipedia.org/wiki/American_Broadcasting_Company' 10")
        return

    url1 = sys.argv[1]
    url2 = sys.argv[2]
    rate_limit = int(sys.argv[3])

    finder = WikipediaPathFinder(rate_limit)

    try:
        path1to2, path2to1 = finder.find_bidirectional_path(url1, url2)

        print("\n" + "="*50)
        print("РЕЗУЛЬТАТЫ:")
        print("="*50)

        if path1to2:
            formatted_path = format_path(path1to2)
            print(formatted_path)
        else:
            print(f"Путь от {url1} к {url2} не найден за 5 переходов")

        if path2to1:
            formatted_path = format_path(path2to1)
            print(formatted_path)
        else:
            print(f"Путь от {url2} к {url1} не найден за 5 переходов")

    except KeyboardInterrupt:
        print("\nПрерывание пользователем")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
