<?php
/**
 * Create-only, idempotent publishing.
 *
 * Order matters: validate everything, create a DRAFT that already carries the ownership
 * and idempotency markers, attach the language marker and SEO fields, verify them, and
 * only then publish. A failure after the draft exists leaves a draft (never a live post)
 * that a replay with the same key reports, without creating or changing anything.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Writer {
	const ALL_STATUSES = array( 'publish', 'future', 'draft', 'pending', 'private', 'trash' );

	public static function find_by( $meta_key, $value ) {
		return get_posts(
			array(
				'post_type'        => 'post',
				'post_status'      => self::ALL_STATUSES,
				'meta_key'         => $meta_key, // phpcs:ignore WordPress.DB.SlowDBQuery
				'meta_value'       => $value, // phpcs:ignore WordPress.DB.SlowDBQuery
				'fields'           => 'ids',
				'numberposts'      => 3,
				'orderby'          => 'ID',
				'order'            => 'ASC',
				'suppress_filters' => true,
			)
		);
	}

	public static function reconcile( $key ) {
		$ids = self::find_by( Thuha_Contract::META_KEY, $key );
		if ( count( $ids ) > 1 ) {
			return Thuha_Contract::error( 'thuha_duplicate_key', 'More than one post carries this idempotency key.', 500 );
		}
		if ( ! $ids ) {
			return array( 'contract' => Thuha_Contract::CONTRACT, 'found' => false );
		}
		$id = (int) $ids[0];
		if ( Thuha_Contract::OWNER !== get_post_meta( $id, Thuha_Contract::META_OWNER, true ) ) {
			return Thuha_Contract::error( 'thuha_foreign_post', 'The post with this key is not owned by the factory.', 409 );
		}
		if ( ! current_user_can( 'edit_post', $id ) ) {
			return Thuha_Contract::error( 'thuha_forbidden', 'The user cannot edit this post.', 403 );
		}
		return array( 'contract' => Thuha_Contract::CONTRACT, 'found' => true, 'post' => Thuha_Readback::post( $id ) );
	}

	private static function fail_draft( $post_id, $code, $message, $status ) {
		update_post_meta( $post_id, Thuha_Contract::META_STATE, $code );
		$post = get_post( $post_id );
		if ( $post && 'publish' === $post->post_status ) {
			wp_update_post( array( 'ID' => $post_id, 'post_status' => 'draft' ) );
		}
		return Thuha_Contract::error( $code, $message, $status );
	}

	public static function create( $fields ) {
		$language = $fields['language'];
		$payload  = Thuha_Contract::payload_hash( $fields );

		// 1. Idempotency: the same key is a replay, a different payload under it is refused.
		$existing = self::reconcile( $fields['idempotency_key'] );
		if ( is_wp_error( $existing ) ) {
			return $existing;
		}
		if ( ! empty( $existing['found'] ) ) {
			if ( $existing['post']['payload_sha256'] !== $payload ) {
				return Thuha_Contract::error( 'thuha_key_payload_mismatch', 'The idempotency key was used with a different payload.', 409 );
			}
			return array( 'contract' => Thuha_Contract::CONTRACT, 'created' => false, 'idempotent_replay' => true, 'post' => $existing['post'] );
		}
		// One topic is created once, even if its article changed and produced another key.
		if ( self::find_by( Thuha_Contract::META_TOPIC, $fields['topic_id'] ) ) {
			return Thuha_Contract::error( 'thuha_topic_already_created', 'A post already exists for this topic.', 409 );
		}

		// 2. The language of the category chain must match; a category never sets the language.
		$chain = Thuha_Language::category_chain_language( $fields['category_id'] );
		if ( $chain !== $language ) {
			return Thuha_Contract::error( 'thuha_category_language_mismatch', 'The category and its ancestors must all be ' . $language . '.', 422 );
		}
		if ( ! current_user_can( 'assign_term', $fields['category_id'] ) ) {
			return Thuha_Contract::error( 'thuha_forbidden', 'The user cannot assign this category.', 403 );
		}

		// 3. Featured media must be an existing, readable attachment with alt text.
		if ( $fields['featured_media'] > 0 ) {
			$media = get_post( $fields['featured_media'] );
			if ( ! $media || 'attachment' !== $media->post_type || ! current_user_can( 'read_post', $fields['featured_media'] )
				|| '' === trim( (string) get_post_meta( $fields['featured_media'], '_wp_attachment_image_alt', true ) ) ) {
				return Thuha_Contract::error( 'thuha_media_invalid', 'Featured media must be a readable attachment with alt text.', 422 );
			}
		}

		// 4. The slug must be free (posts share one slug space across languages) before anything is created.
		if ( wp_unique_post_slug( $fields['slug'], 0, 'publish', 'post', 0 ) !== $fields['slug'] || get_page_by_path( $fields['slug'], OBJECT, 'page' ) ) {
			return Thuha_Contract::error( 'thuha_slug_conflict', 'The slug is already taken by a post or page.', 409 );
		}

		// 5. Draft with ownership markers first; nothing is public yet.
		$post_id = wp_insert_post(
			array(
				'post_type'     => 'post',
				'post_status'   => 'draft',
				'post_title'    => $fields['title'],
				'post_content'  => $fields['content'],
				'post_name'     => $fields['slug'],
				'post_author'   => get_current_user_id(),
				'post_category' => array( $fields['category_id'] ),
				'meta_input'    => array(
					Thuha_Contract::META_OWNER    => Thuha_Contract::OWNER,
					Thuha_Contract::META_KEY      => $fields['idempotency_key'],
					Thuha_Contract::META_PAYLOAD  => $payload,
					Thuha_Contract::META_TOPIC    => $fields['topic_id'],
					Thuha_Contract::META_LANGUAGE => $language,
					Thuha_Contract::META_STATE    => 'DRAFT_CREATED',
				),
			),
			true
		);
		if ( is_wp_error( $post_id ) || ! $post_id ) {
			return Thuha_Contract::error( 'thuha_insert_failed', 'WordPress could not create the draft.', 500 );
		}
		$post_id = (int) $post_id;

		// 6. Language marker BEFORE publish, then verify both documented markers.
		if ( 'vi' === $language ) {
			RBHVI_Language::set_vi( $post_id, true );
		}
		$markers = Thuha_Language::post_markers( $post_id );
		if ( $markers['is_vi'] !== ( 'vi' === $language ) || $markers['taxonomy_vi'] !== ( 'vi' === $language ) ) {
			return self::fail_draft( $post_id, 'thuha_language_marker_failed', 'The native language marker did not match; the post stays a draft.', 500 );
		}

		// 7. SEO fields and featured image, each read back.
		foreach ( Thuha_Contract::yoast_meta() as $field => $meta_key ) {
			update_post_meta( $post_id, $meta_key, $fields['seo'][ $field ] );
			if ( get_post_meta( $post_id, $meta_key, true ) !== $fields['seo'][ $field ] ) {
				return self::fail_draft( $post_id, 'thuha_seo_failed', 'An SEO field did not persist; the post stays a draft.', 500 );
			}
		}
		if ( $fields['featured_media'] > 0 ) {
			set_post_thumbnail( $post_id, $fields['featured_media'] );
			if ( (int) get_post_thumbnail_id( $post_id ) !== $fields['featured_media'] ) {
				return self::fail_draft( $post_id, 'thuha_media_failed', 'The featured image did not attach; the post stays a draft.', 500 );
			}
		}
		$cats = array_map( 'intval', (array) wp_get_post_categories( $post_id ) );
		if ( array( $fields['category_id'] ) !== $cats ) {
			return self::fail_draft( $post_id, 'thuha_category_failed', 'The category assignment differs; the post stays a draft.', 500 );
		}

		// 8. Publish only if the final slug stays exactly as requested.
		if ( wp_unique_post_slug( $fields['slug'], $post_id, 'publish', 'post', 0 ) !== $fields['slug'] ) {
			return self::fail_draft( $post_id, 'thuha_slug_conflict', 'The slug changed before publication; the post stays a draft.', 409 );
		}
		$published = wp_update_post( array( 'ID' => $post_id, 'post_status' => 'publish' ), true );
		if ( is_wp_error( $published ) ) {
			return self::fail_draft( $post_id, 'thuha_publish_failed', 'WordPress refused to publish the draft.', 500 );
		}
		$post = get_post( $post_id );
		$link = (string) get_permalink( $post_id );
		$vi   = 0 === strpos( $link, home_url( '/vi/' ) );
		if ( 'publish' !== $post->post_status || $post->post_name !== $fields['slug'] || $vi !== ( 'vi' === $language ) ) {
			return self::fail_draft( $post_id, 'thuha_permalink_mismatch', 'The permalink is outside the language namespace; the post was returned to draft.', 409 );
		}
		update_post_meta( $post_id, Thuha_Contract::META_STATE, 'PUBLISHED' );
		return array( 'contract' => Thuha_Contract::CONTRACT, 'created' => true, 'idempotent_replay' => false, 'post' => Thuha_Readback::post( $post_id ) );
	}
}
