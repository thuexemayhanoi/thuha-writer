<?php
/**
 * Read-only views of posts and categories. Raw content is returned, never the
 * output of the_content, so no shortcode or third-party filter runs.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Readback {
	public static function post( $post_id ) {
		$post = get_post( (int) $post_id );
		if ( ! $post ) {
			return null;
		}
		$id      = (int) $post->ID;
		$meta    = array();
		foreach ( Thuha_Contract::yoast_meta() as $key ) {
			$meta[ $key ] = (string) get_post_meta( $id, $key, true );
		}
		$language = Thuha_Language::post_language( $id );
		$markers  = Thuha_Language::post_markers( $id );
		$cats     = array_values( array_map( 'intval', (array) wp_get_post_categories( $id ) ) );
		sort( $cats );
		$cat_languages = array();
		foreach ( $cats as $cid ) {
			$cat_languages[] = Thuha_Language::term_language( $cid );
		}
		$content = (string) $post->post_content;
		$marker  = (string) get_post_meta( $id, Thuha_Contract::META_OWNER, true ) === Thuha_Contract::OWNER;
		return array(
			'id'                => $id,
			'type'              => $post->post_type,
			'status'            => $post->post_status,
			'language'          => $language,
			'language_markers'  => $markers,
			'slug'              => $post->post_name,
			'link'              => get_permalink( $id ),
			'title'             => html_entity_decode( wp_strip_all_tags( $post->post_title ), ENT_QUOTES, 'UTF-8' ),
			'content'           => $content,
			'content_raw'       => $content,
			'modified_gmt'      => $post->post_modified_gmt,
			'categories'        => $cats,
			'category_languages' => $cat_languages,
			'featured_media'    => (int) get_post_thumbnail_id( $id ),
			'meta'              => $meta,
			'owner'             => (string) get_post_meta( $id, Thuha_Contract::META_OWNER, true ),
			'idempotency_key'   => (string) get_post_meta( $id, Thuha_Contract::META_KEY, true ),
			'topic_id'          => (string) get_post_meta( $id, Thuha_Contract::META_TOPIC, true ),
			'payload_sha256'    => (string) get_post_meta( $id, Thuha_Contract::META_PAYLOAD, true ),
			'state'             => (string) get_post_meta( $id, Thuha_Contract::META_STATE, true ),
			'marker_present'    => $marker && 1 === preg_match( '/<!-- thuha:v5 topic=[A-Z0-9-]+ sha256=[a-f0-9]{64} -->\s*$/', $content ),
			'incomplete'        => 'publish' !== $post->post_status,
		);
	}

	public static function category( $term ) {
		return array(
			'id'       => (int) $term->term_id,
			'parent'   => (int) $term->parent,
			'name'     => html_entity_decode( $term->name, ENT_QUOTES, 'UTF-8' ),
			'slug'     => $term->slug,
			'link'     => get_term_link( $term ),
			'count'    => (int) $term->count,
			'language' => Thuha_Language::term_language( $term->term_id ),
		);
	}
}
