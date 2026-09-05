# Custom domain and Search Console runbook

This runbook keeps the current GitHub Pages URL as the safe default until the new brand and domain are actually secured.

## Repository variables

Configure these under GitHub Actions repository variables only when the migration is ready.

- `JAI_SITE_NAME`: final public brand name
- `JAI_SITE_URL`: canonical public origin, for example `https://example.jp`
- `JAI_SITE_DESCRIPTION`: optional public description
- `JAI_CUSTOM_DOMAIN`: hostname only, for example `example.jp`
- `JAI_GOOGLE_SITE_VERIFICATION`: optional Google Search Console URL-prefix HTML meta verification token

Leaving any variable empty keeps the existing safe defaults. Do not point `JAI_SITE_URL` at a custom domain before that domain is configured and reachable.

## Deployment behavior

`python scripts/build_public_pages.py` now does the following automatically:

1. Generates all station, ranking, trust and legal pages using `JAI_SITE_NAME` / `JAI_SITE_URL`.
2. Rebuilds canonical URLs, `sitemap.xml` and `robots.txt` against the configured site URL.
3. Writes `web/CNAME` when `JAI_CUSTOM_DOMAIN` is set, and removes a stale generated CNAME when it is not set.
4. Adds the Google `google-site-verification` meta tag to the homepage when `JAI_GOOGLE_SITE_VERIFICATION` is set.
5. `scripts/check_deployment_readiness.py` fails the Pages deployment if the custom domain, canonical site URL, sitemap, robots file or verification tag are internally inconsistent.

The generated `CNAME` and validation are consistency guards for the site artifact. They do not replace configuring the custom domain in the repository's GitHub Pages settings or configuring DNS at the domain provider.

## Cut-over order

1. Finalize brand after the trademark/name checks documented in `BRAND_DOMAIN_RESEARCH_20260905.md`.
2. Register the domain.
3. Configure the domain's DNS for GitHub Pages using the records shown by the current GitHub Pages documentation/settings.
4. Add and verify the custom domain in GitHub Pages settings.
5. Wait until HTTPS is available for the custom domain.
6. Set `JAI_SITE_NAME`, `JAI_SITE_URL` and `JAI_CUSTOM_DOMAIN` repository variables together.
7. Run `Deploy GitHub Pages` and confirm the deployment succeeds.
8. Confirm the homepage, one station page, one ranking page, `robots.txt` and `sitemap.xml` all use the custom-domain canonical URL.
9. Add the new property in Google Search Console and submit `sitemap.xml`.

## Search Console verification

There are two practical verification paths.

### Domain property

Use Google's DNS TXT verification at the DNS provider. This covers the whole domain and its protocols/subdomains. The repository cannot complete that DNS ownership step automatically.

### URL-prefix property

If Google provides an HTML meta verification token, put only the token value into `JAI_GOOGLE_SITE_VERIFICATION`. The build injects:

```html
<meta name="google-site-verification" content="...">
```

into the homepage. After the Pages deployment succeeds, complete verification in Search Console.

The token is expected to be public because it is rendered into page HTML; do not store credentials or API secrets in this variable.

## Rollback

If the custom-domain deployment has a problem:

1. Clear `JAI_CUSTOM_DOMAIN`, `JAI_SITE_URL`, `JAI_SITE_NAME` and `JAI_GOOGLE_SITE_VERIFICATION` as needed.
2. Re-run `Deploy GitHub Pages`.
3. The build returns to the current GitHub Pages URL and removes generated custom-domain/verification artifacts.

Do not delete the old GitHub Pages project path or change station URL IDs during the domain migration. Keeping page paths stable makes canonical/domain migration much safer.
