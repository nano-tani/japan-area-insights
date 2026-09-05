from __future__ import annotations

from html import escape
from pathlib import Path

from .site_config import SITE_DESCRIPTION, SITE_NAME, absolute_url

GITHUB_URL = "https://github.com/nano-tani/japan-area-insights"
ISSUES_URL = f"{GITHUB_URL}/issues"


def _header() -> str:
    return (
        '<header class="site-header">'
        f'<a class="brand" href="../">{escape(SITE_NAME)} <span>BETA</span></a>'
        '<nav class="site-nav" aria-label="主要ナビゲーション">'
        '<a href="../#recommend">おすすめから探す</a>'
        '<a href="../stations.html">街・駅名から探す</a>'
        '<a href="../#discover">条件で探す</a>'
        '</nav></header>'
    )


def _footer() -> str:
    return (
        '<footer>'
        f'<p>{escape(SITE_DESCRIPTION)}</p>'
        '<p class="site-trust-links" data-site-trust-links>'
        '<a href="../about/">運営について</a><span> / </span>'
        '<a href="../methodology/">計算方法</a><span> / </span>'
        '<a href="../sources/">データ出典</a><span> / </span>'
        '<a href="../advertising/">広告について</a><span> / </span>'
        '<a href="../privacy/">プライバシー</a><span> / </span>'
        f'<a href="{GITHUB_URL}" target="_blank" rel="noreferrer">コード</a>'
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
  {_header()}
  <main>
    <nav class="trust-breadcrumb" aria-label="パンくず"><a href="../">{escape(SITE_NAME)}</a><span>›</span><strong>{escape(title)}</strong></nav>
    {body}
  </main>
  {_footer()}
</body>
</html>
'''


def about_html() -> str:
    body = f'''
    <section class="trust-hero">
      <p class="eyebrow">ABOUT</p>
      <h1>運営について</h1>
      <p>{escape(SITE_NAME)}は、公的データを同じルールで整理し、住む駅や地域を比較するときの判断材料を提供する独立プロジェクトです。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">PURPOSE</p><h2>人気投票ではなく、判断材料をそろえる</h2>
      <p>駅中心1km圏や250mメッシュを使い、現在の人口だけでなく2045年までの将来人口、生活施設、交通、不動産取引、防災・地形などを同じ画面で確認できることを目指しています。総合点は参考値にとどめ、元になる数値や出典をできる限り併記します。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">INDEPENDENCE</p><h2>行政機関・不動産会社の公式サービスではありません</h2>
      <p>本サイトは国・自治体・不動産会社・鉄道事業者等が運営する公式サービスではありません。公開情報の取得・集計に誤りがあり得るため、契約や居住判断の前には各公式情報と現地状況も確認してください。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">EDITORIAL POLICY</p><h2>広告と評価ロジックを分離する</h2>
      <div class="trust-grid">
        <article><strong>評価</strong><p>スコア、ランキング、比較結果は公開データと公開した計算ルールから生成し、広告報酬の有無を入力値にしません。</p></article>
        <article><strong>広告</strong><p>今後アフィリエイト広告等を利用する場合も、広告リンクであることを表示し、評価結果から分離します。</p></article>
      </div>
    </section>

    <section class="trust-section">
      <p class="section-kicker">CORRECTIONS</p><h2>誤りや改善提案</h2>
      <p>コードと計算処理は公開しています。データの誤り、表示不具合、計算方法への指摘は、公開リポジトリのIssuesから確認・提案できます。</p>
      <p><a href="{ISSUES_URL}" target="_blank" rel="noreferrer">GitHub Issues →</a></p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">LIMITS</p><h2>本サイトだけで最終判断しない</h2>
      <p>表示内容は居住・購入・売却・投資その他の個別助言ではありません。将来人口や価格の推移は将来の成果を保証せず、防災データも住所・建物単位の安全性を保証しません。</p>
    </section>
    '''
    return _page(
        "運営について",
        "サイトの目的、独立性、広告と評価の分離、訂正方針、情報利用上の注意を説明します。",
        "about/",
        body,
    )


def privacy_html() -> str:
    body = '''
    <section class="trust-hero">
      <p class="eyebrow">PRIVACY</p>
      <h1>プライバシー</h1>
      <p>会員登録を前提にせず、街・駅の比較に必要な情報だけを扱う設計を基本とします。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">ACCOUNT</p><h2>アカウント登録</h2>
      <p>現在の公開サイトにはユーザーアカウント登録機能はありません。氏名・住所・電話番号などをサイト上で入力して保存する仕組みも設けていません。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">LOCAL STORAGE</p><h2>候補駅の保存</h2>
      <p>「候補に保存」した駅は、ログインなしで使えるよう利用端末のブラウザのlocalStorageに保存します。候補情報はその端末・ブラウザ内に保持され、サイトのデータベースへユーザーごとの候補として送信する設計ではありません。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">HOSTING & LINKS</p><h2>ホスティングと外部リンク</h2>
      <p>サイト配信基盤やリンク先のサービスでは、セキュリティ・運用上のアクセスログ等が各事業者の方針に基づき処理される場合があります。外部サイトへ移動した後の情報の取り扱いは、各リンク先のプライバシーポリシーを確認してください。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">ANALYTICS & ADS</p><h2>アクセス解析・広告を導入する場合</h2>
      <p>外部のアクセス解析、広告配信、コンバージョン計測等を導入する場合は、利用するサービス、Cookie等の利用、必要なオプトアウト方法を本ページに追記してから運用します。広告方針は「広告について」に分けて公開します。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">CHANGES</p><h2>方針の変更</h2>
      <p>機能や利用サービスの変更に応じて内容を更新します。重要な変更がある場合は、実際の実装と本ページの説明が一致する状態を優先します。</p>
    </section>
    '''
    return _page(
        "プライバシー",
        "アカウント、候補駅のlocalStorage保存、外部サービス、アクセス解析・広告導入時の情報取扱方針。",
        "privacy/",
        body,
    )


def advertising_html() -> str:
    body = '''
    <section class="trust-hero">
      <p class="eyebrow">ADVERTISING POLICY</p>
      <h1>広告について</h1>
      <p>サイトの運営費を支えるため広告・アフィリエイトを利用する場合がありますが、評価ロジックと広告報酬を分離します。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">SEPARATION</p><h2>順位やおすすめを広告で変えない</h2>
      <p>広告主、提携先、成果報酬の単価、広告リンクの有無を、駅・地域のスコア、テーマ別ランキング、おすすめ検索の計算入力には使用しません。掲載候補の順位を広告報酬のために上げる設計にはしません。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">DISCLOSURE</p><h2>広告リンクは分かる形で表示する</h2>
      <p>成果報酬型リンクを掲載する場合は「広告」「PR」等の表示を行い、検索エンジン向けにも原則として <code>rel="sponsored"</code> を付けます。通常の参考リンクや公的データ出典とは区別します。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">PLACEMENT</p><h2>判断の後段に置く</h2>
      <p>広告は、将来人口・防災・価格等のデータを確認する途中に無理に挟むのではなく、候補駅を比較・検討した後の「物件を探す」「引越しを検討する」など、ユーザーの次の行動と一致する場所への配置を基本とします。</p>
    </section>

    <section class="trust-section">
      <p class="section-kicker">PARTNER DATA</p><h2>提携先の情報</h2>
      <p>外部サービスの価格、掲載物件、キャンペーン、成果条件等は提携先側で変更される場合があります。リンク先で表示される最新条件を確認してください。本サイトは外部事業者の契約成立やサービス内容を保証しません。</p>
    </section>
    '''
    return _page(
        "広告について",
        "アフィリエイト広告とランキング・おすすめの分離、広告表示、リンク属性、配置方針を説明します。",
        "advertising/",
        body,
    )


def export_legal_pages(output_dir: str | Path) -> int:
    web_root = Path(output_dir).parent
    pages = {
        "about": about_html(),
        "privacy": privacy_html(),
        "advertising": advertising_html(),
    }
    for directory, html in pages.items():
        target = web_root / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")
    return len(pages)
