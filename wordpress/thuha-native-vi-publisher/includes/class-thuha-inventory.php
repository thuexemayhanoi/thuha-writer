<?php
/**
 * Complete, read-only inventory of BOTH languages.
 *
 * The public REST collection can hide native Vietnamese posts, so the caller must not
 * trust it. Each response proves completeness by comparing the id list with core's own
 * published/draft counts; a mismatch is an error, never a silently short list.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Inventory {
	public static function statuses() {
		return array( 'publish', 'draft', 'pending', 'future', 'private' );
	}

	public static function preflight() {
		$user    = wp_get_current_user();
		$native  = Thuha_Language::native_available();
		$options = get_option( 'rbhvi_settings', array() );
		$pairs   = ( is_array( $options ) && array_key_exists( 'sitemap_pairs_only', $options ) ) ? (bool) $options['sitemap_pairs_only'] : null;
		return array(
			'contract'        => Thuha_Contract::CONTRACT,
			'adapter_version' => THUHA_ADAPTER_VERSION,
			'native_vi'       => array(
				'present'    => class_exists( 'RBHVI_Language' ),
				'version'    => defined( 'RBHVI_VERSION' ) ? RBHVI_VERSION : null,
				'set_vi'     => class_exists( 'RBHVI_Language' ) && is_callable( array( 'RBHVI_Language', 'set_vi' ) ),
				'is_vi'      => class_exists( 'RBHVI_Language' ) && is_callable( array( 'RBHVI_Language', 'is_vi' ) ),
				'term_is_vi' => class_exists( 'RBHVI_Language' ) && is_callable( array( 'RBHVI_Language', 'term_is_vi' ) ),
				'taxonomy'   => taxonomy_exists( Thuha_Language::TAXONOMY ) ? Thuha_Language::TAXONOMY : null,
				'usable'     => $native,
			),
			'yoast'           => array( 'present' => defined( 'WPSEO_VERSION' ) ),
			'user'            => array(
				'id'  => (int) $user->ID,
				'can' => array(
					'edit_posts'    => current_user_can( 'edit_posts' ),
					'publish_posts' => current_user_can( 'publish_posts' ),
				),
			),
			'auth'            => array( 'application_password' => true ),
			'settings'        => array( 'sitemap_pairs_only' => $pairs ),
			'limits'          => array( 'max_content_bytes' => Thuha_Contract::MAX_CONTENT ),
		);
	}

	public static function page( $type, $status, $page, $per_page ) {
		if ( ! in_array( $type, array( 'post', 'page' ), true ) || ! in_array( $status, self::statuses(), true ) ) {
			return Thuha_Contract::error( 'thuha_schema', 'Unsupported type or status.', 400 );
		}
		$page     = max( 1, (int) $page );
		$per_page = min( 100, max( 1, (int) $per_page ) );
		$ids      = Thuha_Query::unfiltered(
			function () use ( $type, $status ) {
				return get_posts(
					array(
						'post_type'        => $type,
						'post_status'      => $status,
						'fields'           => 'ids',
						'nopaging'         => true,
						'orderby'          => 'ID',
						'order'            => 'ASC',
						'suppress_filters' => true,
					)
				);
			}
		);
		$counts = wp_count_posts( $type );
		$expect = isset( $counts->$status ) ? (int) $counts->$status : 0;
		if ( count( $ids ) !== $expect ) {
			return Thuha_Contract::error( 'thuha_inventory_filtered', 'Query result differs from the core count; a filter is hiding posts.', 500 );
		}
		$total = count( $ids );
		$items = array();
		foreach ( array_slice( $ids, ( $page - 1 ) * $per_page, $per_page ) as $id ) {
			if ( ! current_user_can( 'read_post', (int) $id ) ) {
				return Thuha_Contract::error( 'thuha_forbidden', 'The user cannot read every post in the inventory.', 403 );
			}
			$row = Thuha_Readback::post( (int) $id );
			unset( $row['content_raw'], $row['idempotency_key'], $row['payload_sha256'], $row['state'], $row['incomplete'] );
			$items[] = $row;
		}
		return array(
			'contract'    => Thuha_Contract::CONTRACT,
			'type'        => $type,
			'status'      => $status,
			'page'        => $page,
			'per_page'    => $per_page,
			'total'       => $total,
			'total_pages' => max( 1, (int) ceil( $total / $per_page ) ),
			'items'       => $items,
		);
	}

	public static function categories() {
		$terms = get_terms( array( 'taxonomy' => 'category', 'hide_empty' => false ) );
		if ( is_wp_error( $terms ) ) {
			return $terms;
		}
		$items = array();
		foreach ( $terms as $term ) {
			$items[] = Thuha_Readback::category( $term );
		}
		return array( 'contract' => Thuha_Contract::CONTRACT, 'items' => $items );
	}
}
