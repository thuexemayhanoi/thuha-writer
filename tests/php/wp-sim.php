<?php
/**
 * A deliberately small WordPress simulation, just enough to execute the adapter plugin's own PHP.
 *
 * It is NOT WordPress and proves nothing about the live site: it checks the plugin's logic
 * (validation, ordering, ownership, language gates) against stand-ins for the core and native-VI
 * functions the plugin calls. Real behaviour of those functions stays PENDING live verification.
 */
define( 'ABSPATH', '/simulated-wordpress/' );
define( 'WPSEO_VERSION', 'sim' );
define( 'RBHVI_VERSION', '1.0.0' );
define( 'OBJECT', 'OBJECT' );

class WPWorld {
	public static $actions = array();
	public static $posts, $terms, $termmeta, $options, $routes, $log, $user, $next_id, $vi_posts, $vi_terms;
	public static $native, $fail_set_vi, $hide_vi_in_queries, $vi_permalink_bug, $fail_insert, $denied_posts;
	public static $pre_get_posts_hides_vi, $content_filter, $break_permalink_on_publish, $block_revert;

	public static function reset() {
		self::$posts = array();
		self::$terms = array();
		self::$termmeta = array();
		self::$options = array( 'rbhvi_settings' => array( 'sitemap_pairs_only' => false ) );
		self::$routes = array();
		self::$log = array();
		self::$user = null;
		self::$next_id = 1000;
		self::$vi_posts = array();
		self::$vi_terms = array();
		self::$native = true;
		self::$fail_set_vi = false;
		self::$hide_vi_in_queries = false;
		self::$vi_permalink_bug = false;
		self::$fail_insert = false;
		self::$denied_posts = array();
		self::$pre_get_posts_hides_vi = false;
		self::$content_filter = null;
		self::$break_permalink_on_publish = false;
		self::$block_revert = false;
		unset( $GLOBALS['wp_filter'] );
		Thuha_Auth::reset_for_tests();
		// English tree: Blog(10) > Travel(20). Vietnamese tree: Cam nang(140) > Gia thue(152).
		self::term( 10, 0, 'Blog', 'blog', false );
		self::term( 20, 10, 'Travel', 'travel', false );
		self::term( 140, 0, 'Cẩm nang', 'cam-nang', true );
		self::term( 152, 140, 'Giá thuê và chi phí', 'gia-thue-va-chi-phi', true );
		self::term( 160, 10, 'Mixed child', 'mixed-child', true ); // Vietnamese term under an English parent.
		self::$posts[50] = self::blank( 50, 'attachment', 'inherit', 'Image', 'image' );
		self::$posts[50]['meta']['_wp_attachment_image_alt'] = 'Alt text';
		self::$posts[51] = self::blank( 51, 'attachment', 'inherit', 'No alt', 'no-alt' );
		do_action( 'noop' );
	}

	public static function term( $id, $parent, $name, $slug, $vi ) {
		self::$terms[ $id ] = (object) array( 'term_id' => $id, 'parent' => $parent, 'name' => $name, 'slug' => $slug, 'count' => 0 );
		self::$termmeta[ $id ] = $vi ? array( '_rbhvi_lang' => 'vi' ) : array();
		self::$vi_terms[ $id ] = $vi;
	}

	public static function blank( $id, $type, $status, $title, $slug ) {
		return array(
			'ID' => $id, 'post_type' => $type, 'post_status' => $status, 'post_title' => $title, 'post_content' => '',
			'post_name' => $slug, 'post_password' => '', 'post_author' => 1, 'post_modified_gmt' => '2026-10-22 00:00:00', 'meta' => array(), 'cats' => array(), 'thumb' => 0,
		);
	}

	public static function add_post( $type, $status, $title, $slug, $vi = false, $cats = array( 20 ) ) {
		$id = self::$next_id++;
		self::$posts[ $id ] = self::blank( $id, $type, $status, $title, $slug );
		self::$posts[ $id ]['cats'] = $cats;
		self::$vi_posts[ $id ] = $vi;
		return $id;
	}

	public static function login( $caps, $app_password = true ) {
		self::$user = (object) array( 'ID' => 7, 'caps' => $caps );
		if ( $app_password ) {
			do_action( 'application_password_did_authenticate', self::$user, array() );
		}
	}

	public static function posts_of( $type = 'post' ) {
		return array_values( array_filter( self::$posts, function ( $p ) use ( $type ) { return $p['post_type'] === $type; } ) );
	}
}

class WP_Error {
	private $code, $message, $data;
	public function __construct( $code = '', $message = '', $data = '' ) { $this->code = $code; $this->message = $message; $this->data = $data; }
	public function get_error_code() { return $this->code; }
	public function get_error_message() { return $this->message; }
	public function get_error_data() { return $this->data; }
}
function is_wp_error( $x ) { return $x instanceof WP_Error; }

class WP_REST_Request {
	public $params, $headers, $json;
	public function __construct( $json = null, $params = array(), $headers = array() ) { $this->json = $json; $this->params = $params; $this->headers = array_change_key_case( $headers, CASE_LOWER ); }
	public function get_param( $k ) { return $this->params[ $k ] ?? null; }
	public function get_header( $k ) { return $this->headers[ strtolower( $k ) ] ?? null; }
	public function get_json_params() { return $this->json; }
}
class WP_REST_Response {
	public $data, $status = 200;
	public function __construct( $data = null ) { $this->data = $data; }
	public function set_status( $s ) { $this->status = $s; }
}
function rest_ensure_response( $d ) { return $d instanceof WP_REST_Response ? $d : new WP_REST_Response( $d ); }
function register_rest_route( $ns, $route, $args ) { WPWorld::$routes[] = array( $ns, $route, $args ); }
function add_action( $hook, $cb, $prio = 10, $n = 1 ) { WPWorld::$actions[ $hook ][] = $cb; }
function do_action( $hook, ...$args ) { foreach ( WPWorld::$actions[ $hook ] ?? array() as $cb ) { call_user_func_array( $cb, $args ); } }
function is_user_logged_in() { return null !== WPWorld::$user; }
function get_current_user_id() { return WPWorld::$user ? WPWorld::$user->ID : 0; }
function wp_get_current_user() { return WPWorld::$user ?: (object) array( 'ID' => 0 ); }
function current_user_can( $cap, $arg = null ) {
	if ( ! WPWorld::$user ) { return false; }
	if ( ( 'read_post' === $cap || 'edit_post' === $cap ) && in_array( $arg, WPWorld::$denied_posts, true ) ) { return false; }
	return in_array( $cap, WPWorld::$user->caps, true );
}
function get_option( $k, $d = false ) { return WPWorld::$options[ $k ] ?? $d; }
function add_option( $k, $v, $deprecated = '', $autoload = 'yes' ) { if ( array_key_exists( $k, WPWorld::$options ) ) { return false; } WPWorld::$options[ $k ] = $v; return true; }
function delete_option( $k ) { unset( WPWorld::$options[ $k ] ); return true; }
function wp_slash( $v ) { return is_array( $v ) ? array_map( 'wp_slash', $v ) : ( is_string( $v ) ? addslashes( $v ) : $v ); }
function wp_unslash( $v ) { return is_array( $v ) ? array_map( 'wp_unslash', $v ) : ( is_string( $v ) ? stripslashes( $v ) : $v ); }
function taxonomy_exists( $t ) { return WPWorld::$native && 'rbhvi_language' === $t; }
function wp_strip_all_tags( $s ) { return trim( strip_tags( $s ) ); }
function wp_json_encode( $d ) { return json_encode( $d, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES ); }
function home_url( $path = '' ) { return 'https://rentbikehanoi.com' . $path; }

function get_post( $id ) {
	$p = WPWorld::$posts[ $id ] ?? null;
	return $p ? (object) $p : null;
}
function get_permalink( $post ) {
	$id = is_object( $post ) ? $post->ID : $post;
	$p = is_object( $post ) ? (array) $post : WPWorld::$posts[ $id ];
	if ( 'publish' !== $p['post_status'] ) { return home_url( '/?p=' . $id ); }
	$vi = ! empty( WPWorld::$vi_posts[ $id ] ) && ! WPWorld::$vi_permalink_bug;
	return home_url( ( $vi ? '/vi/' : '/' ) . $p['post_name'] . '/' );
}
function get_posts( $args ) {
	$status = $args['post_status'] ?? 'publish';
	$list = array_values( array_filter( WPWorld::$posts, function ( $p ) use ( $args, $status ) {
		if ( $p['post_type'] !== ( $args['post_type'] ?? 'post' ) ) { return false; }
		if ( 'any' === $status ? 'trash' === $p['post_status'] : ! in_array( $p['post_status'], (array) $status, true ) ) { return false; }
		if ( isset( $args['meta_key'] ) && ( $p['meta'][ $args['meta_key'] ] ?? null ) !== $args['meta_value'] ) { return false; }
		if ( WPWorld::$hide_vi_in_queries && ! empty( WPWorld::$vi_posts[ $p['ID'] ] ) ) { return false; }
		if ( WPWorld::$pre_get_posts_hides_vi && ! empty( $GLOBALS['wp_filter']['pre_get_posts'] ) && ! empty( WPWorld::$vi_posts[ $p['ID'] ] ) ) { return false; }
		return true;
	} ) );
	usort( $list, function ( $a, $b ) { return $a['ID'] <=> $b['ID']; } );
	if ( isset( $args['numberposts'] ) && $args['numberposts'] > 0 ) { $list = array_slice( $list, 0, $args['numberposts'] ); }
	return array_map( function ( $p ) { return $p['ID']; }, $list );
}
function wp_count_posts( $type = 'post' ) {
	$c = new stdClass();
	foreach ( WPWorld::$posts as $p ) {
		if ( $p['post_type'] === $type ) { $s = $p['post_status']; $c->$s = ( $c->$s ?? 0 ) + 1; }
	}
	return $c;
}
function wp_unique_post_slug( $slug, $post_id, $status, $type, $parent ) {
	if ( in_array( $status, array( 'draft', 'pending', 'auto-draft' ), true ) ) { return $slug; }
	foreach ( WPWorld::$posts as $p ) {
		if ( $p['ID'] !== $post_id && $p['post_type'] === $type && 'trash' !== $p['post_status'] && $p['post_name'] === $slug ) { return $slug . '-2'; }
	}
	return $slug;
}
function get_page_by_path( $slug, $output, $type ) {
	foreach ( WPWorld::$posts as $p ) {
		if ( $p['post_type'] === $type && $p['post_name'] === $slug && 'trash' !== $p['post_status'] ) { return (object) $p; }
	}
	return null;
}
function wp_insert_post( $arr, $wp_error = false ) {
	if ( WPWorld::$fail_insert ) { return $wp_error ? new WP_Error( 'insert', 'failed' ) : 0; }
	$id = WPWorld::$next_id++;
	$p = WPWorld::blank( $id, $arr['post_type'], $arr['post_status'], $arr['post_title'], $arr['post_name'] );
	$p['post_title'] = wp_unslash( $arr['post_title'] ); // core's wp_insert_post unslashes its input
	$p['post_content'] = wp_unslash( $arr['post_content'] );
	if ( WPWorld::$content_filter ) { $p['post_content'] = call_user_func( WPWorld::$content_filter, $p['post_content'] ); }
	$p['post_author'] = $arr['post_author'];
	$p['cats'] = $arr['post_category'] ?? array();
	$p['meta'] = array_map( 'wp_unslash', $arr['meta_input'] ?? array() ); // add_metadata unslashes values too
	WPWorld::$posts[ $id ] = $p;
	WPWorld::$vi_posts[ $id ] = false;
	WPWorld::$log[] = array( 'insert', $id, $arr['post_status'] );
	return $id;
}
function wp_update_post( $arr, $wp_error = false ) {
	$id = $arr['ID'];
	if ( isset( $arr['post_status'] ) ) {
		if ( 'publish' === $arr['post_status'] ) {
			$unique = wp_unique_post_slug( WPWorld::$posts[ $id ]['post_name'], $id, 'publish', 'post', 0 );
			WPWorld::$posts[ $id ]['post_name'] = $unique;
		}
		if ( 'draft' === $arr['post_status'] && WPWorld::$block_revert ) { return $id; } // simulates a revert that does not take
		WPWorld::$posts[ $id ]['post_status'] = $arr['post_status'];
		if ( 'publish' === $arr['post_status'] && WPWorld::$break_permalink_on_publish ) { WPWorld::$vi_permalink_bug = true; }
		WPWorld::$log[] = array( 'status', $id, $arr['post_status'], ! empty( WPWorld::$vi_posts[ $id ] ) );
	}
	return $id;
}
function get_post_meta( $id, $key, $single = false ) { return WPWorld::$posts[ $id ]['meta'][ $key ] ?? ''; }
function update_post_meta( $id, $key, $value ) { WPWorld::$posts[ $id ]['meta'][ $key ] = wp_unslash( $value ); WPWorld::$log[] = array( 'meta', $id, $key ); return true; }
function wp_get_post_categories( $id ) { return WPWorld::$posts[ $id ]['cats']; }
function set_post_thumbnail( $id, $media ) { WPWorld::$posts[ $id ]['thumb'] = $media; return true; }
function get_post_thumbnail_id( $id ) { return WPWorld::$posts[ $id ]['thumb']; }
function get_term( $id, $tax = '' ) { return WPWorld::$terms[ $id ] ?? null; }
function get_terms( $args ) { return array_values( WPWorld::$terms ); }
function get_term_meta( $id, $key, $single = false ) { return WPWorld::$termmeta[ $id ][ $key ] ?? ''; }
function get_term_link( $term ) { return home_url( ( ! empty( WPWorld::$vi_terms[ $term->term_id ] ) ? '/vi/chuyen-muc/' : '/blog/' ) . $term->slug . '/' ); }
function has_term( $term, $tax, $id ) { return 'rbhvi_language' === $tax && 'vi' === $term && ! empty( WPWorld::$vi_posts[ $id ] ); }

class RBHVI_Language {
	public static function set_vi( $post_id, $flag ) {
		if ( WPWorld::$fail_set_vi ) { return false; }
		WPWorld::$vi_posts[ $post_id ] = (bool) $flag;
		WPWorld::$log[] = array( 'set_vi', $post_id );
		return true;
	}
	public static function is_vi( $post_id ) { return ! empty( WPWorld::$vi_posts[ $post_id ] ); }
	public static function term_is_vi( $term_id ) { return ! empty( WPWorld::$vi_terms[ $term_id ] ); }
}

require_once dirname( __DIR__, 2 ) . '/wordpress/thuha-native-vi-publisher/thuha-native-vi-publisher.php';
