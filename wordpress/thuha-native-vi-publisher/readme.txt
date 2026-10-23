=== ThuHa Native VI Publisher ===
Requires at least: 6.2
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later

Authenticated companion API for the ThuHa Writer factory (rentbikehanoi.com).

== Description ==

Adds five authenticated REST routes under /wp-json/thuha-writer/v1/:

* GET  /preflight         adapter, native-VI API, Yoast, capability and sitemap checks
* GET  /inventory         read-only list of posts or pages with a verified language (vi/en)
* GET  /categories        categories with a verified language
* GET  /posts/by-key/{k}  read back a factory-created post by its idempotency key
* POST /posts             create-only: draft with ownership marker -> RBHVI_Language::set_vi
                          -> SEO fields -> verification -> publish

Safety properties: no public route; Application Password authentication only (cookie sessions
and browser origins are refused); capability checks (edit_posts to read, publish_posts to write,
plus per-post and per-category checks); strict request schema; no raw SQL; no request-supplied
code; a replayed idempotency key never creates or changes a post; a failure after the draft
exists leaves a draft, never a live post.

It needs the existing rentbikehanoi-native-vi plugin (class RBHVI_Language, taxonomy
rbhvi_language). Without it every route except /preflight answers 503.

== Installation ==

1. Plugins > Add New > Upload Plugin, choose thuha-native-vi-publisher-1.0.0.zip, Activate.
2. Create an Application Password for a user who may publish posts (Users > Profile).
3. Give the publisher environment that user name and password as secrets.
4. Run the publisher's adapter-preflight; publishing stays disabled until it passes.

== Optional setting ==

Option thuha_adapter_allowed_origins (array of exact origins) is empty by default: any request
that carries an Origin header is refused. Server-to-server calls do not send one.

== Status ==

Version 1.0.0 has been exercised only against an offline simulation of WordPress. It has not
been installed on or tested against the live site.

== Changelog ==

= 1.0.0 =
* First release.
