<?php
/**
 * Create-only, idempotent publishing.
 *
 * Order matters: validate everything, create a DRAFT that already carries the ownership and idempotency markers,
 * attach the language marker and SEO fields, verify them, check the would-be permalink on a copy that already has
 * the published status, and only then publish. A failure after the draft exists leaves a draft; a replay with the
 * same key reports it without creating or changing anything. After publication the checks run once more as a
 * safety net, but publication side effects (feeds, sitemaps, pings) cannot be undone by returning a post to draft,
 * which is why the decisive checks happen BEFORE the status change.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Writer {
	const ALL_STATUSES = array( 'publish', 'future', 'draft', 'pending', 'private', 'trash' );

	public static function find_by( $meta_key, $value ) {
		return Thuha_Query::unfiltered(
			function () use ( $meta_key, $value ) {
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

	/** Two identical POSTs racing past the key lookup would both insert; an atomic add_option is the lock. */
	private static function lock( $key ) {
		$name = 'thuha_lock_' . substr( $key, 0, 40 );
		if ( add_option( $name, (string) time(), '', 'no' ) ) {
			return $name;
		}
		$held = (int) get_option( $name, 0 );
		if ( $held && time() - $held > 300 ) { // a crashed request; take the lock over
			delete_option( $name );
			if ( add_option( $name, (string) time(), '', 'no' ) ) {
				return $name;
			}
		}
		return false;
	}

	/**
	 * Returns the post to draft and CHECKS that it worked. If it did not, say so loudly: the post may be live.
	 */
	private static function fail_draft( $post_id, $code, $message, $status ) {
		update_post_meta( $post_id, Thuha_Contract::META_STATE, $code );
		$post = get_post( $post_id );
		if ( $post && 'draft' !== $post->post_status ) {
			wp_update_post( array( 'ID' => $post_id, 'post_status' => 'draft' ) );
			$after = get_post( $post_id );
			if ( ! $after || 'draft' !== $after->post_status ) {
				update_post_meta( $post_id, Thuha_Contract::META_STATE, 'thuha_revert_failed' );
				return Thuha_Contract::error( 'thuha_revert_failed', $message . ' The post could NOT be returned to draft and may be LIVE: check it in WordPress now.', 500 );
			}
		}
		return Thuha_Contract::error( $code, $message, $status );
	}

	public static function create( $fields ) {
		$language = $fields['language'];
		$payload  = Thuha_Contract::payload_hash( $fields );
		$lock     = self::lock( $fields['idempotency_key'] );
		if ( ! $lock ) {
			return Thuha_Contract::error( 'thuha_in_progress', 'Another request for this idempotency key is running; reconcile by key instead of retrying.', 409 );
		}
		try {
			return self::create_locked( $fields, $language, $payload );
		} finally {
			delete_option( $lock );
		}
	}

	private static function create_locked( $fields, $language, $payload ) {
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

		// 3. Featured media is optional (0 means no image); chosen media must be readable.
		if ( $fields['featured_media'] > 0 ) {
			$media = get_post( $fields['featured_media'] );
			if ( ! $media || 'attachment' !== $media->post_type || ! current_user_can( 'read_post', $fields['featured_media'] )
				|| false ) {
				return Thuha_Contract::error( 'thuha_media_invalid', 'Featured media must be a readable attachment.', 422 );
			}
		}

		// 4. The slug must be free (posts share one slug space across languages) before anything is created.
		if ( wp_unique_post_slug( $fields['slug'], 0, 'publish', 'post', 0 ) !== $fields['slug'] || get_page_by_path( $fields['slug'], OBJECT, 'page' ) ) {
			return Thuha_Contract::error( 'thuha_slug_conflict', 'The slug is already taken by a post or page.', 409 );
		}

		// 5. Draft with ownership markers first; nothing is public yet. WordPress unslashes what it is given, so
		// every string is slashed first or backslashes in the article would be silently removed.
		$meta = array(
			Thuha_Contract::META_OWNER    => Thuha_Contract::OWNER,
			Thuha_Contract::META_KEY      => $fields['idempotency_key'],
			Thuha_Contract::META_PAYLOAD  => $payload,
			Thuha_Contract::META_TOPIC    => $fields['topic_id'],
			Thuha_Contract::META_LANGUAGE => $language,
			Thuha_Contract::META_STATE    => 'DRAFT_CREATED',
		);
		$post_id = wp_insert_post(
			array(
				'post_type'     => 'post',
				'post_status'   => 'draft',
				'post_title'    => wp_slash( $fields['title'] ),
				'post_content'  => wp_slash( $fields['content'] ),
				'post_name'     => $fields['slug'],
				'post_author'   => get_current_user_id(),
				'post_category' => array( $fields['category_id'] ),
				'meta_input'    => array_map( 'wp_slash', $meta ),
			),
			true
		);
		if ( is_wp_error( $post_id ) || ! $post_id ) {
			return Thuha_Contract::error( 'thuha_insert_failed', 'WordPress could not create the draft.', 500 );
		}
		$post_id = (int) $post_id;

		// Title and body must be stored exactly as reviewed (kses or a content filter can alter them).
		$stored = get_post( $post_id );
		if ( ! $stored || $stored->post_title !== $fields['title'] || $stored->post_content !== $fields['content'] ) {
			return self::fail_draft( $post_id, 'thuha_content_altered', 'WordPress stored the title or body differently from the reviewed text; the post stays a draft.', 422 );
		}

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
			update_post_meta( $post_id, $meta_key, wp_slash( $fields['seo'][ $field ] ) );
			if ( get_post_meta( $post_id, $meta_key, true ) !== $fields['seo'][ $field ] ) {
				return self::fail_draft( $post_id, 'thuha_seo_failed', 'An SEO field did not persist unchanged; the post stays a draft.', 500 );
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

		// 8. Decide BEFORE publishing: the slug must stay exactly as requested and the permalink of a copy that already
		// has the published status must sit in the right language namespace.
		if ( wp_unique_post_slug( $fields['slug'], $post_id, 'publish', 'post', 0 ) !== $fields['slug'] ) {
			return self::fail_draft( $post_id, 'thuha_slug_changed', 'The slug would change on publication; the post stays a draft.', 409 );
		}
		$probe              = clone get_post( $post_id );
		$probe->post_status = 'publish';
		$planned            = (string) get_permalink( $probe );
		if ( ( 0 === strpos( $planned, home_url( '/vi/' ) ) ) !== ( 'vi' === $language ) || false === strpos( $planned, '/' . $fields['slug'] . '/' ) ) {
			return self::fail_draft( $post_id, 'thuha_permalink_mismatch', 'The permalink would leave the language namespace; the post stays a draft.', 409 );
		}

		$published = wp_update_post( array( 'ID' => $post_id, 'post_status' => 'publish' ), true );
		if ( is_wp_error( $published ) ) {
			return self::fail_draft( $post_id, 'thuha_publish_failed', 'WordPress refused to publish the draft.', 500 );
		}
		// Safety net only: the decisive checks already happened.
		$post = get_post( $post_id );
		$link = (string) get_permalink( $post_id );
		if ( 'publish' !== $post->post_status || $post->post_name !== $fields['slug'] || ( 0 === strpos( $link, home_url( '/vi/' ) ) ) !== ( 'vi' === $language ) ) {
			return self::fail_draft( $post_id, 'thuha_permalink_mismatch', 'The post was published but its slug or URL is not as planned and it was returned to draft; publication side effects may already have run.', 409 );
		}
		update_post_meta( $post_id, Thuha_Contract::META_STATE, 'PUBLISHED' );
		return array( 'contract' => Thuha_Contract::CONTRACT, 'created' => true, 'idempotent_replay' => false, 'post' => Thuha_Readback::post( $post_id ) );
	}
}
