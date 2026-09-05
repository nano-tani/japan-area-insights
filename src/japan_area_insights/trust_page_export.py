from __future__ import annotations

from html import escape
from pathlib import Path

from .site_config import SITE_DESCRIPTION, SITE_NAME, absolute_url


def _header(prefix: str) -> str:
    return (
        '<header class="site-header">'
        f'<a class="brand" href="{prefix}">{escape(SITE_NAME)} <span>BETA</span></a>'
        '<nav class="site-nav" aria-label="主要ナビゲーション">'
        f'<a href="{prefix}#recommend">おすすめから探す</a>'
        f'<a href="{prefix}stations.html">街・駅名から探す</a>'
        f'<a href="{prefix}#discover">条件で探す</a>'
        '</nav></header>'
    )


def _footer(prefix: str) -> str:
    return (
        '<footer>'
        f'<p>{escape(SITE_DESCRIPTION)}</p>'
        '<p class="site-trust-links" data-site-trust-links>'
        f'<a href="{prefix}methodology/">計算方法</a><span> / </span>'
        f'<a href="{prefix}sources/">データ出典</a><span> / </span>'
        '<a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">コード</a>'
        '</p></footer>'
    )


def _page(title: str, description: str, canonical_path: str, body: str) -> str:
    canonical = absolute_url(canonical_path)
    return f'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(title)} | {escape(SITE_NAME)}</title>
  <meta name="description" content="{escape(description, quote=True)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical, quote=True)}">
  <link rel="stylesheet" href="../styles.css">
  <link rel="stylesheet" href="../polish.css">
  <link rel="stylesheet" href="../navigation.css?v=20260905-5">
  <link rel="stylesheet" href="../trust-pages.css?v=20260905-1">
</head>
<body class="trust-page">
  {_header('../')}
  <main>
    <nav class="trust-breadcrumb" aria-label="パンくず"><a href="../">{escape(SITE_NAME)}</a><span>›</span><strong>{escape(title)}</strong></nav>
    {body}
  </main>
  {_footer('../')}
</body>
</html>
'''


def methodology_html() -> str:
    body = '''
    <section class="trust-hero">
      <p class="eyebrow">METHODOLOGY</p>
      <h1>計算方法</h1>
      <p>このサイトは「高い点数の街を当てる」ためではなく、住む場所を比較するときに、同じ定義・同じ公的データで判断材料をそろえることを目的にしています。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">STATION AREA</p><h2>駅エリアは駅中心1km圏</h2>
      <div class="trust-grid">
        <article><strong>生活圏</strong><p>駅グループの代表座標から約1km以内に中心点を持つ250mメッシュを集め、人口・将来人口・生活施設・交通などを集計します。行政区境をまたぐ場合も一つの駅エリアとして扱います。</p></article>
        <article><strong>不動産取引</strong><p>取引価格は物件位置を1km圏へ推測配分しません。不動産情報ライブラリ XIT001 を駅グループコードで検索した取引を別枠で表示します。</p></article>
      </div>
    </section>

    <section class="trust-section">
      <p class="section-kicker">REFERENCE SCORE</p><h2>総合100点は参考値</h2>
      <div class="trust-score-list">
        <span><b>価格動向</b><strong>20</strong></span><span><b>人口動向（推計）</b><strong>20</strong></span><span><b>将来人口</b><strong>20</strong></span><span><b>生活利便性</b><strong>15</strong></span><span><b>交通利便性</b><strong>15</strong></span><span><b>取引活性度</b><strong>10</strong></span>
      </div>
      <p>各項目は東京23区内の駅1km圏という同じ母集団の中で相対評価します。区スコアとは入力値も比較母集団も異なるため直接比較できません。必要項目が欠けた場合は欠損を0点にせず、総合点そのものを出しません。</p>
      <p>駅の総合点は、6項目完備に加え、直近5完了年の取引30件以上、価格データ3年以上などの適格条件を満たす場合だけ表示します。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">NOW → 2045</p><h2>将来人口を総合点より先に見る</h2>
      <p>2025・2030・2035・2040・2045年の250mメッシュ別将来推計人口を駅1km圏で集計し、2025年を100とした人口維持率を表示します。推計値は将来を保証するものではありません。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">DECISION THEMES</p><h2>テーマ別ランキングの式</h2>
      <div class="trust-grid trust-grid-3">
        <article><strong>将来人口</strong><p>将来人口スコアを100換算して順位化します。実数の2045/2025人口維持率も併記します。</p></article>
        <article><strong>価格 × 将来</strong><p>価格動向スコア50% + 将来人口スコア50%。片方が欠ける駅はランキング対象外です。</p></article>
        <article><strong>将来 × 防災</strong><p>将来人口60% + 防災参考値40%。防災参考値は洪水曝露人口とJ-SHISの震度6弱以上30年確率を、低いほど高評価になるよう換算し、取得できている項目だけで計算します。</p></article>
      </div>
    </section>

    <section class="trust-section">
      <p class="section-kicker">QUALITY GATE</p><h2>検索対象にするページの品質条件</h2>
      <p>駅コード・駅名・座標・1km圏メッシュ、2025年と2045年の将来人口、生活または交通の実データ、出典情報がそろった駅だけを検索対象にします。総合点が未算出でも、これらがそろえば駅ページ自体には独立した情報価値があるため公開対象にできます。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">HAZARD & AI</p><h2>防災とAIの扱い</h2>
      <p>洪水・地震・液状化・標高などの防災情報は総合100点へ混ぜず、独立した判断材料として表示します。住所・物件単位の安全性を保証するものではないため、契約前には各自治体等の公式ハザード情報で確認してください。</p>
      <p>AIは説明文の補助に利用することがありますが、スコア計算や公的データの数値そのものをAIに生成させません。</p>
    </section>
    '''
    return _page(
        "計算方法",
        "駅1km圏、250mメッシュ、将来人口、参考総合評価、テーマ別ランキング、防災情報の計算方法と公開品質ルール。",
        "methodology/",
        body,
    )


def sources_html() -> str:
    body = '''
    <section class="trust-hero">
      <p class="eyebrow">DATA SOURCES</p>
      <h1>データ出典</h1>
      <p>表示値は公的機関が公開する統計・地理データを取得し、サイト側で同じ集計ルールにそろえたものです。駅ページでは実際に利用した出典情報も併記します。</p>
    </section>

    <section class="trust-section">
      <div class="source-list">
        <article><div><span>国土交通省 不動産情報ライブラリ</span><strong>XIT001</strong></div><h2>不動産取引価格</h2><p>駅グループコードを条件に、取引件数・単価中央値・価格変化などを集計します。物件位置を駅1km圏へ推測しません。</p><a href="https://www.reinfolib.mlit.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>国土交通省 不動産情報ライブラリ</span><strong>XKT013</strong></div><h2>250mメッシュ別将来推計人口</h2><p>駅中心1km圏の2025〜2045年人口と人口維持率、区内250mメッシュ表示に利用します。</p><a href="https://www.reinfolib.mlit.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>政府統計総合窓口 e-Stat</span><strong>国勢調査</strong></div><h2>人口・世帯</h2><p>自治体単位の人口・世帯、人口変化などの基礎統計に利用します。利用表IDは更新処理と公開出典に保持します。</p><a href="https://www.e-stat.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>国土交通省 不動産情報ライブラリ</span><strong>XKT006 / 007 / 010 / 017 / 018</strong></div><h2>生活利便施設</h2><p>学校、保育園・幼稚園等、医療機関、図書館、公共施設を駅1km圏・自治体単位で集計します。</p><a href="https://www.reinfolib.mlit.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>国土交通省 不動産情報ライブラリ</span><strong>XKT015</strong></div><h2>駅・路線・乗降客数</h2><p>駅1km圏の駅数・路線数、駅別乗降客数など交通指標に利用します。</p><a href="https://www.reinfolib.mlit.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>防災科学技術研究所</span><strong>J-SHIS</strong></div><h2>地震ハザード</h2><p>250mメッシュの地盤関連値と、今後30年で一定震度以上となる確率を表示・集計します。</p><a href="https://www.j-shis.bosai.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>国土地理院</span><strong>標高</strong></div><h2>地形・標高</h2><p>250mメッシュ中心付近の標高代表値を使い、駅1km圏では人口加重平均などを算出します。</p><a href="https://maps.gsi.go.jp/" target="_blank" rel="noreferrer">公式サイト →</a></article>
        <article><div><span>国土数値情報等</span><strong>防災レイヤー</strong></div><h2>洪水・高潮・津波・土砂・液状化等</h2><p>公式区分を可能な範囲で保持し、対象地域の2025推計人口に対する曝露率などを別指標として集計します。</p><a href="https://nlftp.mlit.go.jp/ksj/" target="_blank" rel="noreferrer">公式サイト →</a></article>
      </div>
    </section>

    <section class="trust-section">
      <p class="section-kicker">FRESHNESS</p><h2>更新日と欠損</h2>
      <p>公的データはデータセットごとに更新時期が異なります。取得できなかった値を推測補完してランキングへ混ぜず、欠損は欠損として扱います。駅ページのデータ基準日・出典と、公開JSONの生成時刻を確認できる構造にしています。</p>
    </section>
    '''
    return _page(
        "データ出典",
        "不動産情報ライブラリ、e-Stat、J-SHIS、国土地理院など、このサイトで使用する公的データの出典と利用方法。",
        "sources/",
        body,
    )


def export_trust_pages(output_dir: str | Path) -> int:
    data_dir = Path(output_dir)
    web_root = data_dir.parent
    pages = {
        web_root / "methodology" / "index.html": methodology_html(),
        web_root / "sources" / "index.html": sources_html(),
    }
    for path, html in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    return len(pages)
