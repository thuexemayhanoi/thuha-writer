<?php
/**
 * Runs read-only lookups with the hooks that can silently hide posts (for example a language filter that removes
 * Vietnamese posts) lifted for the duration of the call. suppress_filters does not cover these two.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Query {
	public static function unfiltered( $callback ) {
		global $wp_filter;
		$saved = array();
		foreach ( array( 'pre_get_posts', 'posts_pre_query' ) as $name ) {
			if ( isset( $wp_filter[ $name ] ) ) {
				$saved[ $name ] = $wp_filter[ $name ];
				unset( $wp_filter[ $name ] );
			}
		}
		try {
			return call_user_func( $callback );
		} finally {
			foreach ( $saved as $name => $hooks ) {
				$wp_filter[ $name ] = $hooks;
			}
		}
	}
}
