<?php
/**
 * Contract constants and strict request validation.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Contract {
	const NAMESPACE_    = 'thuha-writer/v1';
	const CONTRACT      = 'thuha-writer/1';
	const OWNER         = 'thuha-writer';
	const META_OWNER    = '_thuha_owner';
	const META_KEY      = '_thuha_idempotency_key';
	const META_PAYLOAD  = '_thuha_payload_sha256';
	const META_TOPIC    = '_thuha_topic_id';
	const META_LANGUAGE = '_thuha_language';
	const META_STATE    = '_thuha_state';
	const MAX_CONTENT   = 200000;

	private static $data = null;

	/** contract.json is the single source of the byte limits and the HTML allow-lists shared with the Python QA. */
	public static function data() {
		if ( null === self::$data ) {
			$raw        = is_readable( THUHA_ADAPTER_DIR . '/contract.json' ) ? file_get_contents( THUHA_ADAPTER_DIR . '/contract.json' ) : '';
			$decoded    = json_decode( (string) $raw, true );
			self::$data = is_array( $decoded ) ? $decoded : array();
		}
		return self::$data;
	}

	public static function limit( $name ) {
		$data = self::data();
		return isset( $data['limits'][ $name ] ) ? (int) $data['limits'][ $name ] : 0; // 0 means "unknown": every size check then fails closed
	}

	/**
	 * Strict canonical-form HTML policy (identical algorithm to src/thuha/htmlpolicy.py): lower-case allow-listed tags,
	 * double-quoted allow-listed attributes without duplicates, URL values in printable ASCII with only &amp; entities and
	 * a safe scheme, no comments, declarations or bare '<'. Anything else is refused, not interpreted.
	 */
	public static function html_violations( $markup ) {
		$data = self::data();
		if ( empty( $data['html_policy']['tags'] ) ) {
			return array( 'policy-unavailable' );
		}
		$p       = $data['html_policy'];
		$tags    = array_flip( $p['tags'] );
		$voids   = array_flip( $p['void_tags'] );
		$global  = array_flip( $p['global_attributes'] );
		$urls    = array_flip( $p['url_attributes'] );
		$schemes = array_flip( $p['url_schemes'] );
		$out     = array();
		$i       = 0;
		while ( false !== ( $i = strpos( $markup, '<', $i ) ) ) {
			if ( ! preg_match( '/\G<(\/?)([a-z][a-z0-9]*)((?:[ \t\r\n\f]+[a-z][a-z0-9-]*="[^"<>]*")*)[ \t\r\n\f]*(\/?)>/', $markup, $m, 0, $i ) ) {
				$out[] = 'malformed-markup';
				$i++;
				continue;
			}
			$i += strlen( $m[0] );
			list( , $closing, $tag, $attrs, $self ) = $m;
			if ( ! isset( $tags[ $tag ] ) ) {
				$out[] = 'tag:' . $tag;
				continue;
			}
			if ( '' !== $closing && ( '' !== trim( $attrs, " \t\r\n\f" ) || '' !== $self || isset( $voids[ $tag ] ) ) ) {
				$out[] = 'closing-tag-form:' . $tag;
			}
			if ( '' !== $self && ! isset( $voids[ $tag ] ) ) {
				$out[] = 'self-closing:' . $tag;
			}
			$allowed = isset( $p['attributes'][ $tag ] ) ? array_flip( $p['attributes'][ $tag ] ) : array();
			$seen    = array();
			preg_match_all( '/[ \t\r\n\f]+([a-z][a-z0-9-]*)="([^"<>]*)"/', $attrs, $found, PREG_SET_ORDER );
			foreach ( $found as $attr ) {
				$name  = $attr[1];
				$value = $attr[2];
				if ( isset( $seen[ $name ] ) ) {
					$out[] = 'duplicate-attribute:' . $tag . '.' . $name;
				}
				$seen[ $name ] = true;
				if ( ! isset( $global[ $name ] ) && ! isset( $allowed[ $name ] ) ) {
					$out[] = 'attribute:' . $tag . '.' . $name;
					continue;
				}
				if ( isset( $p['attribute_values'][ $name ] ) && ! in_array( $value, $p['attribute_values'][ $name ], true ) ) {
					$out[] = 'attribute-value:' . $tag . '.' . $name;
				}
				if ( isset( $urls[ $name ] ) ) {
					if ( false !== strpos( str_replace( '&amp;', '', $value ), '&' ) || preg_match( '/[^\x21-\x7e]|[\\\\"\'`<>]/', $value ) ) {
						$out[] = 'url-form:' . $tag . '.' . $name;
						continue;
					}
					$low = strtolower( str_replace( '&amp;', '&', $value ) );
					if ( preg_match( '/^[a-z][a-z0-9+.-]*:/', $low ) && ! isset( $schemes[ explode( ':', $low, 2 )[0] ] ) ) {
						$out[] = 'url-scheme:' . $tag . '.' . $name;
					}
				}
			}
		}
		return $out;
	}

	public static function create_fields() {
		return array( 'contract', 'idempotency_key', 'topic_id', 'language', 'slug', 'title', 'content', 'category_id', 'featured_media', 'seo', 'marker' );
	}

	public static function seo_fields() {
		return array( 'title', 'description', 'focus_keyword' );
	}

	public static function yoast_meta() {
		return array(
			'title'         => '_yoast_wpseo_title',
			'description'   => '_yoast_wpseo_metadesc',
			'focus_keyword' => '_yoast_wpseo_focuskw',
		);
	}

	public static function languages() {
		return array( 'vi', 'en' );
	}

	/** Key-order independent digest, so a replay with reordered JSON is still the same payload. */
	public static function payload_hash( $fields ) {
		ksort( $fields );
		ksort( $fields['seo'] );
		return hash( 'sha256', wp_json_encode( $fields ) );
	}

	public static function error( $code, $message, $status ) {
		return new WP_Error( $code, $message, array( 'status' => $status ) );
	}

	/**
	 * Returns the validated, normalised fields or a WP_Error. Unknown keys are refused so
	 * the request cannot smuggle post type, author, status, meta or taxonomy overrides.
	 */
	public static function validate_create( $body ) {
		if ( ! is_array( $body ) ) {
			return self::error( 'thuha_schema', 'Request body must be a JSON object.', 400 );
		}
		$keys = array_keys( $body );
		sort( $keys );
		$want = self::create_fields();
		sort( $want );
		if ( $keys !== $want ) {
			return self::error( 'thuha_schema', 'Fields do not match the contract.', 400 );
		}
		if ( self::CONTRACT !== $body['contract'] ) {
			return self::error( 'thuha_schema', 'Unsupported contract version.', 400 );
		}
		foreach ( array( 'idempotency_key', 'topic_id', 'language', 'slug', 'title', 'content', 'marker' ) as $name ) {
			if ( ! is_string( $body[ $name ] ) ) {
				return self::error( 'thuha_schema', 'Field ' . $name . ' must be a string.', 400 );
			}
		}
		if ( ! preg_match( '/^[a-f0-9]{64}$/D', $body['idempotency_key'] ) ) {
			return self::error( 'thuha_schema', 'Idempotency key must be 64 lowercase hex characters.', 400 );
		}
		if ( ! in_array( $body['language'], self::languages(), true ) ) {
			return self::error( 'thuha_schema', 'Language must be vi or en.', 400 );
		}
		if ( ! preg_match( '/^TH-(VI|EN)-[0-9]{4}$|^TH-[0-9]{6}$/D', $body['topic_id'], $m ) ) {
			return self::error( 'thuha_schema', 'Topic ID format is invalid.', 400 );
		}
		$topic_language = ( isset( $m[1] ) && '' !== $m[1] ) ? strtolower( $m[1] ) : 'en'; // Legacy IDs were English-only.
		if ( $topic_language !== $body['language'] ) {
			return self::error( 'thuha_language_mismatch', 'Topic ID language does not match the request language.', 422 );
		}
		if ( ! preg_match( '/^[a-z0-9]+(?:-[a-z0-9]+)*$/D', $body['slug'] ) || strlen( $body['slug'] ) > self::limit( 'slug_bytes' ) ) {
			return self::error( 'thuha_schema', 'Slug must be lowercase ASCII words joined by hyphens.', 400 );
		}
		if ( '' === $body['title'] || $body['title'] !== trim( preg_replace( '/[ \t\r\n\f]+/', ' ', $body['title'] ) ) || strlen( $body['title'] ) > self::limit( 'title_bytes' ) || wp_strip_all_tags( $body['title'] ) !== $body['title'] ) {
			return self::error( 'thuha_schema', 'Title must be plain text up to 300 bytes.', 400 );
		}
		if ( ! is_int( $body['category_id'] ) || $body['category_id'] < 1 || ! is_int( $body['featured_media'] ) || $body['featured_media'] < 0 ) {
			return self::error( 'thuha_schema', 'Category and media IDs must be integers.', 400 );
		}
		if ( ! is_array( $body['seo'] ) ) {
			return self::error( 'thuha_schema', 'SEO must be an object.', 400 );
		}
		$seo_keys = array_keys( $body['seo'] );
		sort( $seo_keys );
		$seo_want = self::seo_fields();
		sort( $seo_want );
		if ( $seo_keys !== $seo_want ) {
			return self::error( 'thuha_schema', 'SEO fields do not match the contract.', 400 );
		}
		foreach ( self::seo_fields() as $name ) {
			$value = $body['seo'][ $name ];
			if ( ! is_string( $value ) || '' === $value || strlen( $value ) > self::limit( 'seo_bytes' ) || wp_strip_all_tags( $value ) !== $value ) {
				return self::error( 'thuha_schema', 'SEO ' . $name . ' must be plain text up to 400 bytes.', 400 );
			}
		}
		$safe = self::check_content( $body['content'], $body['marker'], $body['topic_id'] );
		if ( is_wp_error( $safe ) ) {
			return $safe;
		}
		return $body;
	}

	private static function check_content( $content, $marker, $topic_id ) {
		if ( '' === $content || strlen( $content ) > self::limit( 'content_bytes' ) ) {
			return self::error( 'thuha_schema', 'Content is empty or too large.', 400 );
		}
		if ( ! preg_match( '/^<!-- thuha:v5 topic=(TH-(?:VI|EN)-[0-9]{4}|TH-[0-9]{6}) sha256=[a-f0-9]{64} -->$/D', $marker, $m ) || $m[1] !== $topic_id ) {
			return self::error( 'thuha_marker', 'Ownership marker is malformed or names another topic.', 422 );
		}
		if ( substr( $content, -strlen( $marker ) ) !== $marker || substr_count( strtolower( $content ), '<!-- thuha:' ) !== 1 ) {
			return self::error( 'thuha_marker', 'Content must end with exactly one ownership marker.', 422 );
		}
		$problems = self::html_violations( substr( $content, 0, -strlen( $marker ) ) );
		if ( $problems ) {
			return self::error( 'thuha_unsafe_html', 'Content is outside the HTML policy: ' . implode( ', ', array_slice( $problems, 0, 3 ) ), 422 );
		}
		return true;
	}
}
