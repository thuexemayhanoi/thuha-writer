<?php
/**
 * Language markers. Both documented markers must agree, otherwise the item is 'conflict'.
 * A Vietnamese category on its own never makes a post Vietnamese.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Language {
	const TAXONOMY  = 'rbhvi_language';
	const TERM_SLUG = 'vi';
	const TERM_META = '_rbhvi_lang';

	public static function native_available() {
		return class_exists( 'RBHVI_Language' )
			&& is_callable( array( 'RBHVI_Language', 'set_vi' ) )
			&& is_callable( array( 'RBHVI_Language', 'is_vi' ) )
			&& is_callable( array( 'RBHVI_Language', 'term_is_vi' ) )
			&& taxonomy_exists( self::TAXONOMY );
	}

	public static function post_markers( $post_id ) {
		return array(
			'is_vi'       => (bool) RBHVI_Language::is_vi( (int) $post_id ),
			'taxonomy_vi' => (bool) has_term( self::TERM_SLUG, self::TAXONOMY, (int) $post_id ),
		);
	}

	public static function post_language( $post_id ) {
		$m = self::post_markers( $post_id );
		if ( $m['is_vi'] !== $m['taxonomy_vi'] ) {
			return 'conflict';
		}
		return $m['is_vi'] ? 'vi' : 'en';
	}

	public static function term_language( $term_id ) {
		$api  = (bool) RBHVI_Language::term_is_vi( (int) $term_id );
		$meta = self::TERM_SLUG === get_term_meta( (int) $term_id, self::TERM_META, true );
		if ( $api !== $meta ) {
			return 'conflict';
		}
		return $api ? 'vi' : 'en';
	}

	/** Language of a category and all its ancestors, or 'conflict'/'mixed'. */
	public static function category_chain_language( $term_id ) {
		$seen   = array();
		$id     = (int) $term_id;
		$result = null;
		while ( $id ) {
			if ( isset( $seen[ $id ] ) ) {
				return 'conflict';
			}
			$seen[ $id ] = true;
			$term        = get_term( $id, 'category' );
			if ( ! $term || is_wp_error( $term ) ) {
				return 'conflict';
			}
			$language = self::term_language( $id );
			if ( 'conflict' === $language ) {
				return 'conflict';
			}
			if ( null === $result ) {
				$result = $language;
			} elseif ( $result !== $language ) {
				return 'mixed';
			}
			$id = (int) $term->parent;
		}
		return $result ? $result : 'conflict';
	}
}
