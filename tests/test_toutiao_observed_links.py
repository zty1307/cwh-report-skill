import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from discover_toutiao_comment_seeds import observed_article_id, parse_search_articles


def test_nested_observed_search_link_retains_actual_id_and_title():
    gid = '7000000000000000011'
    url = 'http://www.toutiao.com/a' + gid + '/?source=search_tab'
    for _ in range(2):
        url = 'https://sou.toutiao.com/search/jump?url=' + quote(url, safe='') + '&aid=4916'
    page = f'<a href="{url}">本期<em>政策</em>分析</a>'
    assert observed_article_id(url) == gid
    assert parse_search_articles(page) == {gid: '本期政策分析'}


def test_external_profile_and_unobserved_query_numbers_are_not_article_ids():
    for url in ['https://example.test/a7000000000000000011/',
                'https://www.toutiao.com/c/user/token/7000000000000000011/',
                'https://so.toutiao.com/search?q=7000000000000000011',
                'https://sou.toutiao.com/search/jump?url=https%3A%2F%2Fydata.woa.com%2Fa7000000000000000011',
                'javascript:void(0)']:
        assert observed_article_id(url) == ''


def test_legacy_cards_and_new_links_coexist_without_duplicates():
    page = ('<div cr-params="{&quot;gid&quot;:&quot;7000000000000000011&quot;,&quot;title&quot;:&quot;旧标题&quot;}"></div>'
            '<a href="https://www.toutiao.com/article/7000000000000000011/">完整标题</a>')
    assert parse_search_articles(page) == {'7000000000000000011': '完整标题'}


def test_result_card_scope_excludes_navigation_hotlist_links():
    page = ('<script>{"gid":7000000000000000099}</script>'
            '<div><a href="https://www.toutiao.com/a7000000000000000099/">推荐热榜</a></div>'
            '<div class="cs-card"><div><a href="https://www.toutiao.com/a7000000000000000011/">本期文章</a>'
            '<a href="https://www.toutiao.com/a7000000000000000011/"></a></div></div>')
    assert parse_search_articles(page) == {'7000000000000000011': '本期文章'}
