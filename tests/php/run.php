<?php
/**
 * Executes the adapter plugin's PHP against the small WordPress simulation (wp-sim.php) and prints JSON.
 * Usage: php tests/php/run.php
 */
require __DIR__ . '/wp-sim.php';

$results = array( 'passed' => array(), 'failed' => array() );
$GLOBALS['current'] = '';

function check( $condition, $message ) {
	if ( ! $condition ) { throw new Exception( $message ); }
}
function code_of( $result ) { return is_wp_error( $result ) ? $result->get_error_code() : 'ok'; }
function status_of( $result ) { return is_wp_error( $result ) ? $result->get_error_data()['status'] : ( $result->status ?? 200 ); }
function run_test( $name, $fn ) {
	global $results;
	WPWorld::reset();
	Thuha_Routes::register();
	try { $fn(); $results['passed'][] = $name; } catch ( Throwable $e ) { $results['failed'][] = $name . ': ' . $e->getMessage(); }
}
function publisher() { WPWorld::login( array( 'edit_posts', 'publish_posts', 'read_post', 'edit_post', 'assign_term' ) ); }
function route( $path, $method = 'GET' ) {
	foreach ( WPWorld::$routes as $r ) {
		if ( $r[1] === $path && $r[2]['methods'] === $method ) { return $r[2]; }
	}
	throw new Exception( 'route missing ' . $path );
}
function call( $path, $request, $method = 'GET' ) {
	$route = route( $path, $method );
	$allowed = call_user_func( $route['permission_callback'], $request );
	if ( true !== $allowed ) { return $allowed; }
	return call_user_func( $route['callback'], $request );
}
function key_for( $n ) { return str_pad( dechex( $n ), 64, '0', STR_PAD_LEFT ); }
function body( $over = array() ) {
	$n = $over['_n'] ?? 1;
	unset( $over['_n'] );
	$lang = $over['language'] ?? 'vi';
	$topic = $over['topic_id'] ?? ( 'vi' === $lang ? 'TH-VI-' : 'TH-EN-' ) . str_pad( $n, 4, '0', STR_PAD_LEFT );
	$marker = '<!-- thuha:v5 topic=' . $topic . ' sha256=' . str_repeat( 'a', 64 ) . ' -->';
	$base = array(
		'contract' => 'thuha-writer/1', 'idempotency_key' => key_for( $n ), 'topic_id' => $topic, 'language' => $lang,
		'slug' => 'vi' === $lang ? 'dat-coc-xe-may-' . $n : 'rental-deposit-' . $n,
		'title' => 'vi' === $lang ? 'Đặt cọc thuê xe máy cần hỏi gì' : 'What to ask about a rental deposit',
		'content' => '<h2>Heading</h2><p>Body text.</p>' . "\n" . $marker,
		'category_id' => 'vi' === $lang ? 152 : 20, 'featured_media' => 50,
		'seo' => array( 'title' => 'SEO title ' . $n, 'description' => 'SEO description ' . $n, 'focus_keyword' => 'keyword ' . $n ),
		'marker' => $marker,
	);
	return array_replace( $base, $over );
}
function post_request( $over = array(), $headers = array() ) { return new WP_REST_Request( body( $over ), array(), $headers ); }
function raw_post_request( $json ) { return new WP_REST_Request( $json ); }

run_test( 'no public route and exact route set', function () {
	check( count( WPWorld::$routes ) === 5, 'five routes expected' );
	foreach ( WPWorld::$routes as $r ) {
		check( 'thuha-writer/v1' === $r[0], 'namespace' );
		check( isset( $r[2]['permission_callback'] ) && '__return_true' !== $r[2]['permission_callback'], 'permission callback required: ' . $r[1] );
	}
	$contract = json_decode( file_get_contents( dirname( __DIR__, 2 ) . '/wordpress/thuha-native-vi-publisher/contract.json' ), true );
	$have = array_map( function ( $r ) { return $r[1] . ' ' . $r[2]['methods']; }, WPWorld::$routes );
	$want = array_map( function ( $r ) { return $r[1] . ' ' . $r[0]; }, array_values( $contract['routes'] ) );
	sort( $have ); sort( $want );
	check( $have === $want, 'contract.json routes differ from registered routes' );
} );

run_test( 'authentication: anonymous, cookie session, wrong capability, browser origin', function () {
	$r = call( '/posts', post_request(), 'POST' );
	check( 'thuha_unauthenticated' === code_of( $r ) && 401 === status_of( $r ), 'anonymous must get 401' );
	WPWorld::login( array( 'edit_posts', 'publish_posts' ), false );
	check( 'thuha_app_password_required' === code_of( call( '/posts', post_request(), 'POST' ) ), 'cookie session refused' );
	WPWorld::login( array( 'edit_posts' ), true );
	check( 'thuha_forbidden' === code_of( call( '/posts', post_request(), 'POST' ) ), 'contributor cannot publish' );
	check( 'ok' === code_of( call( '/preflight', new WP_REST_Request() ) ), 'edit_posts may read' );
	publisher();
	$r = call( '/posts', post_request( array(), array( 'Origin' => 'https://evil.example' ) ), 'POST' );
	check( 'thuha_origin_forbidden' === code_of( $r ), 'foreign browser origin refused' );
	WPWorld::$options['thuha_adapter_allowed_origins'] = array( 'https://rentbikehanoi.com' );
	check( 'ok' === code_of( call( '/posts', post_request( array(), array( 'Origin' => 'https://rentbikehanoi.com' ) ), 'POST' ) ), 'listed origin accepted' );
} );

run_test( 'preflight reports native API and settings; missing native plugin blocks writes', function () {
	publisher();
	$p = call( '/preflight', new WP_REST_Request() )->data;
	check( $p['native_vi']['usable'] && $p['native_vi']['set_vi'] && 'rbhvi_language' === $p['native_vi']['taxonomy'], 'native usable' );
	check( false === $p['settings']['sitemap_pairs_only'] && $p['yoast']['present'], 'settings/yoast' );
	WPWorld::$native = false;
	check( 'thuha_native_vi_missing' === code_of( call( '/posts', post_request(), 'POST' ) ), 'writes blocked without native plugin' );
	check( 'thuha_native_vi_missing' === code_of( call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'publish' ) ) ) ), 'inventory blocked' );
	check( 0 === count( WPWorld::posts_of() ), 'no post created' );
} );

run_test( 'Vietnamese post: draft first, language marker before publish, SEO and /vi/ URL', function () {
	publisher();
	$r = call( '/posts', post_request(), 'POST' );
	check( ! is_wp_error( $r ) && 201 === $r->status, 'created ' . code_of( $r ) );
	$post = $r->data['post'];
	check( 'publish' === $post['status'] && 'vi' === $post['language'], 'published as vi' );
	check( $post['language_markers']['is_vi'] && $post['language_markers']['taxonomy_vi'], 'both markers' );
	check( 0 === strpos( $post['link'], 'https://rentbikehanoi.com/vi/' ), 'vi permalink' );
	check( 'SEO title 1' === $post['meta']['_yoast_wpseo_title'] && 'keyword 1' === $post['meta']['_yoast_wpseo_focuskw'], 'yoast meta' );
	check( $post['marker_present'] && 'thuha-writer' === $post['owner'] && array( 152 ) === $post['categories'] && array( 'vi' ) === $post['category_languages'], 'ownership and category' );
	$events = array_map( function ( $e ) { return $e[0] . ( isset( $e[2] ) && 'status' === $e[0] ? ':' . $e[2] : '' ); }, array_filter( WPWorld::$log, function ( $e ) { return in_array( $e[0], array( 'insert', 'set_vi', 'status' ), true ); } ) );
	check( array( 'insert', 'set_vi', 'status:publish' ) === array_values( $events ), 'order must be insert draft, set_vi, publish: ' . json_encode( array_values( $events ) ) );
	check( 'draft' === WPWorld::$log[0][2], 'inserted as draft' );
} );

run_test( 'English post is never marked Vietnamese and lives at the root', function () {
	publisher();
	$r = call( '/posts', post_request( array( 'language' => 'en' ) ), 'POST' );
	check( 201 === $r->status, 'created' );
	$p = $r->data['post'];
	check( 'en' === $p['language'] && ! $p['language_markers']['is_vi'] && ! $p['language_markers']['taxonomy_vi'], 'english markers' );
	check( 0 !== strpos( $p['link'], 'https://rentbikehanoi.com/vi/' ), 'root url' );
	foreach ( WPWorld::$log as $e ) { check( 'set_vi' !== $e[0], 'set_vi must not run for English' ); }
} );

run_test( 'category language mismatch is refused and creates nothing', function () {
	publisher();
	check( 'thuha_category_language_mismatch' === code_of( call( '/posts', post_request( array( 'language' => 'vi', 'category_id' => 20 ) ), 'POST' ) ), 'vi into en category' );
	check( 'thuha_category_language_mismatch' === code_of( call( '/posts', post_request( array( 'language' => 'en', 'category_id' => 152, '_n' => 2 ) ), 'POST' ) ), 'en into vi category' );
	check( 'thuha_category_language_mismatch' === code_of( call( '/posts', post_request( array( 'language' => 'vi', 'category_id' => 160, '_n' => 3 ) ), 'POST' ) ), 'vi child under en parent' );
	check( 'thuha_category_language_mismatch' === code_of( call( '/posts', post_request( array( 'category_id' => 999, '_n' => 4 ) ), 'POST' ) ), 'unknown category' );
	check( 0 === count( WPWorld::posts_of() ), 'nothing created' );
} );

run_test( 'a Vietnamese category alone never makes a post Vietnamese', function () {
	publisher();
	WPWorld::$fail_set_vi = true; // marker cannot be attached
	$r = call( '/posts', post_request(), 'POST' );
	check( 'thuha_language_marker_failed' === code_of( $r ), 'must fail' );
	$posts = WPWorld::posts_of();
	check( 1 === count( $posts ) && 'draft' === $posts[0]['post_status'], 'stays a draft, never published' );
	foreach ( WPWorld::$log as $e ) { check( ! ( 'status' === $e[0] && 'publish' === $e[2] ), 'never published' ); }
	$replay = call( '/posts', post_request(), 'POST' );
	check( ! is_wp_error( $replay ) && 200 === $replay->status && true === $replay->data['idempotent_replay'] && $replay->data['post']['incomplete'], 'replay reports the incomplete draft' );
	check( 1 === count( WPWorld::posts_of() ), 'replay creates nothing' );
} );

run_test( 'idempotent replay, payload mismatch and topic duplication', function () {
	publisher();
	$a = call( '/posts', post_request(), 'POST' );
	$b = call( '/posts', post_request(), 'POST' );
	check( 201 === $a->status && 200 === $b->status && true === $b->data['idempotent_replay'], 'replay answered' );
	check( $a->data['post']['id'] === $b->data['post']['id'] && 1 === count( WPWorld::posts_of() ), 'one post only' );
	$reordered = body();
	$reordered = array_reverse( $reordered, true );
	$reordered['seo'] = array_reverse( $reordered['seo'], true );
	check( 200 === call( '/posts', new WP_REST_Request( $reordered ), 'POST' )->status, 'key order does not change the payload hash' );
	check( 'thuha_key_payload_mismatch' === code_of( call( '/posts', post_request( array( 'title' => 'Different title' ) ), 'POST' ) ), 'same key, new payload' );
	check( 'thuha_topic_already_created' === code_of( call( '/posts', post_request( array( 'idempotency_key' => key_for( 99 ), 'slug' => 'another-slug-123' ) ), 'POST' ) ), 'same topic, new key' );
	check( 1 === count( WPWorld::posts_of() ), 'still one post' );
} );

run_test( 'strict schema: unknown fields, malformed values and unsafe markup are refused', function () {
	publisher();
	$bad = array(
		'unknown field' => array_merge( body(), array( 'post_status' => 'publish' ) ),
		'array not object' => array( 1, 2, 3 ),
		'bad contract' => body( array( 'contract' => 'other/1' ) ),
		'bad key' => body( array( 'idempotency_key' => 'abc' ) ),
		'bad language' => body( array( 'language' => 'fr' ) ),
		'topic language differs' => body( array( 'topic_id' => 'TH-EN-0001' ) ),
		'uppercase slug' => body( array( 'slug' => 'Dat-Coc' ) ),
		'html title' => body( array( 'title' => '<b>Bold</b>' ) ),
		'string category' => body( array( 'category_id' => '152' ) ),
		'script' => body( array( 'content' => '<script>x</script>' . "\n" . body()['marker'] ) ),
		'inline handler' => body( array( 'content' => '<p onclick="x()">a</p>' . "\n" . body()['marker'] ) ),
		'no marker' => body( array( 'content' => '<p>text</p>' ) ),
		'foreign marker topic' => body( array( 'marker' => '<!-- thuha:v5 topic=TH-VI-0009 sha256=' . str_repeat( 'a', 64 ) . ' -->' ) ),
		'seo unknown key' => body( array( 'seo' => array( 'title' => 'a', 'description' => 'b', 'focus_keyword' => 'c', 'extra' => 'd' ) ) ),
		'oversize' => body( array( 'content' => str_repeat( 'a', 200001 ) . "\n" . body()['marker'] ) ),
	);
	foreach ( $bad as $name => $payload ) {
		$r = call( '/posts', raw_post_request( $payload ), 'POST' );
		check( is_wp_error( $r ) && in_array( status_of( $r ), array( 400, 422 ), true ), 'must refuse: ' . $name . ' got ' . code_of( $r ) );
	}
	check( 0 === count( WPWorld::posts_of() ), 'nothing created by refused requests' );
} );

run_test( 'slug conflicts across posts, pages and languages create no draft', function () {
	publisher();
	WPWorld::add_post( 'post', 'publish', 'Existing English', 'dat-coc-xe-may-1', false );
	check( 'thuha_slug_conflict' === code_of( call( '/posts', post_request(), 'POST' ) ), 'english slug blocks vietnamese post (one slug space)' );
	WPWorld::add_post( 'page', 'publish', 'A page', 'rental-deposit-2', false, array() );
	check( 'thuha_slug_conflict' === code_of( call( '/posts', post_request( array( 'language' => 'en', '_n' => 2 ) ), 'POST' ) ), 'page slug blocks' );
	check( 0 === count( array_filter( WPWorld::posts_of(), function ( $p ) { return isset( $p['meta']['_thuha_owner'] ); } ) ), 'no factory draft exists' );
} );

run_test( 'permalink outside the language namespace returns the post to draft', function () {
	publisher();
	WPWorld::$vi_permalink_bug = true;
	$r = call( '/posts', post_request(), 'POST' );
	check( 'thuha_permalink_mismatch' === code_of( $r ), 'refused' );
	$p = WPWorld::posts_of()[0];
	check( 'draft' === $p['post_status'], 'back to draft' );
} );

run_test( 'media and insert failures leave nothing live', function () {
	publisher();
	check( 'thuha_media_invalid' === code_of( call( '/posts', post_request( array( 'featured_media' => 51 ) ), 'POST' ) ), 'media without alt' );
	check( 'thuha_media_invalid' === code_of( call( '/posts', post_request( array( 'featured_media' => 99999, '_n' => 2 ) ), 'POST' ) ), 'missing media' );
	WPWorld::$fail_insert = true;
	check( 'thuha_insert_failed' === code_of( call( '/posts', post_request( array( '_n' => 3 ) ), 'POST' ) ), 'insert failure' );
	check( 0 === count( WPWorld::posts_of() ), 'nothing created' );
} );

run_test( 'reconcile by key: unknown, found, foreign and unreadable', function () {
	publisher();
	$unknown = call( '/posts/by-key/(?P<key>[a-f0-9]{64})', new WP_REST_Request( null, array( 'key' => key_for( 5 ) ) ) );
	check( false === $unknown->data['found'], 'unknown key is not found' );
	$made = call( '/posts', post_request(), 'POST' )->data['post'];
	$found = call( '/posts/by-key/(?P<key>[a-f0-9]{64})', new WP_REST_Request( null, array( 'key' => key_for( 1 ) ) ) )->data;
	check( $found['found'] && $found['post']['id'] === $made['id'], 'found by key' );
	WPWorld::$posts[ $made['id'] ]['meta']['_thuha_owner'] = 'somebody-else';
	check( 'thuha_foreign_post' === code_of( call( '/posts/by-key/(?P<key>[a-f0-9]{64})', new WP_REST_Request( null, array( 'key' => key_for( 1 ) ) ) ) ), 'foreign owner refused' );
	WPWorld::$posts[ $made['id'] ]['meta']['_thuha_owner'] = 'thuha-writer';
	WPWorld::$denied_posts[] = $made['id'];
	check( 'thuha_forbidden' === code_of( call( '/posts/by-key/(?P<key>[a-f0-9]{64})', new WP_REST_Request( null, array( 'key' => key_for( 1 ) ) ) ) ), 'per-post capability enforced' );
} );

run_test( 'reconcile also finds a trashed factory post', function () {
	publisher();
	$made = call( '/posts', post_request(), 'POST' )->data['post'];
	WPWorld::$posts[ $made['id'] ]['post_status'] = 'trash';
	$found = call( '/posts/by-key/(?P<key>[a-f0-9]{64})', new WP_REST_Request( null, array( 'key' => key_for( 1 ) ) ) )->data;
	check( $found['found'] && 'trash' === $found['post']['status'] && $found['post']['incomplete'], 'trash reported, not hidden' );
} );

run_test( 'inventory counts both languages and excludes pages, drafts and trash from published posts', function () {
	publisher();
	for ( $i = 0; $i < 3; $i++ ) { WPWorld::add_post( 'post', 'publish', 'EN ' . $i, 'en-' . $i, false ); }
	for ( $i = 0; $i < 2; $i++ ) { WPWorld::add_post( 'post', 'publish', 'VI ' . $i, 'vi-' . $i, true, array( 152 ) ); }
	WPWorld::add_post( 'post', 'draft', 'Draft', 'draft-1', false );
	WPWorld::add_post( 'post', 'trash', 'Trash', 'trash-1', true, array( 152 ) );
	WPWorld::add_post( 'page', 'publish', 'Page', 'page-1', true, array() );
	$posts = call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'publish', 'page' => 1, 'per_page' => 100 ) ) )->data;
	check( 5 === $posts['total'] && 1 === $posts['total_pages'], 'five published posts' );
	$by = array( 'en' => 0, 'vi' => 0 );
	foreach ( $posts['items'] as $row ) { $by[ $row['language'] ]++; check( ! isset( $row['idempotency_key'] ), 'no private fields in inventory' ); }
	check( 3 === $by['en'] && 2 === $by['vi'], 'language split ' . json_encode( $by ) );
	$pages = call( '/inventory', new WP_REST_Request( null, array( 'type' => 'page', 'status' => 'publish' ) ) )->data;
	check( 1 === $pages['total'] && 'vi' === $pages['items'][0]['language'], 'pages are listed apart from posts' );
	$paged = call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'publish', 'page' => 2, 'per_page' => 2 ) ) )->data;
	check( 3 === $paged['total_pages'] && 2 === count( $paged['items'] ), 'pagination proven by total_pages' );
	check( 'thuha_schema' === code_of( call( '/inventory', new WP_REST_Request( null, array( 'type' => 'attachment', 'status' => 'publish' ) ) ) ), 'unsupported type' );
	check( 'thuha_schema' === code_of( call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'trash' ) ) ) ), 'trash is not listable as inventory' );
} );

run_test( 'a filter hiding Vietnamese posts is an error, not a short list', function () {
	publisher();
	WPWorld::add_post( 'post', 'publish', 'EN', 'en-a', false );
	WPWorld::add_post( 'post', 'publish', 'VI', 'vi-a', true, array( 152 ) );
	WPWorld::$hide_vi_in_queries = true;
	$r = call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'publish' ) ) );
	check( 'thuha_inventory_filtered' === code_of( $r ), 'must expose the hidden post' );
} );

run_test( 'disagreeing language markers are reported as conflict', function () {
	publisher();
	$id = WPWorld::add_post( 'post', 'publish', 'Odd', 'odd', true, array( 152 ) );
	WPWorld::$vi_posts[ $id ] = true;
	$rows = call( '/inventory', new WP_REST_Request( null, array( 'type' => 'post', 'status' => 'publish' ) ) )->data['items'];
	check( 'vi' === $rows[0]['language'], 'baseline vi' );
	// has_term follows vi_posts too; force a disagreement through the term marker on categories instead.
	WPWorld::$termmeta[152]['_rbhvi_lang'] = '';
	$cats = call( '/categories', new WP_REST_Request() )->data['items'];
	$by = array(); foreach ( $cats as $c ) { $by[ $c['id'] ] = $c['language']; }
	check( 'conflict' === $by[152] && 'vi' === $by[140] && 'en' === $by[10], 'term markers must agree: ' . json_encode( $by ) );
} );

echo json_encode( $results, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE ) . "\n";
exit( $results['failed'] ? 1 : 0 );
