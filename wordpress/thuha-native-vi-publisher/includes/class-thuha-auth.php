<?php
/**
 * Authentication, origin and capability gates shared by every route.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Auth {
	private static $application_password = false;

	public static function mark_application_password( $user = null, $item = null ) {
		self::$application_password = true;
	}

	public static function reset_for_tests() {
		self::$application_password = false;
	}

	/**
	 * @param WP_REST_Request $request Request.
	 * @param string          $capability Capability the caller must hold.
	 * @return true|WP_Error
	 */
	public static function check( $request, $capability ) {
		if ( ! is_user_logged_in() ) {
			return Thuha_Contract::error( 'thuha_unauthenticated', 'Authentication is required.', 401 );
		}
		if ( ! self::$application_password ) {
			return Thuha_Contract::error( 'thuha_app_password_required', 'Only Application Password authentication is accepted.', 403 );
		}
		$origin = trim( (string) $request->get_header( 'origin' ) );
		if ( '' !== $origin ) {
			$allowed = get_option( 'thuha_adapter_allowed_origins', array() );
			if ( ! is_array( $allowed ) || ! in_array( $origin, $allowed, true ) ) {
				return Thuha_Contract::error( 'thuha_origin_forbidden', 'Browser origins are not allowed.', 403 );
			}
		}
		if ( ! current_user_can( $capability ) ) {
			return Thuha_Contract::error( 'thuha_forbidden', 'The authenticated user lacks the required capability.', 403 );
		}
		return true;
	}

	public static function read_permission( $request ) {
		return self::check( $request, 'edit_posts' );
	}

	public static function write_permission( $request ) {
		return self::check( $request, 'publish_posts' );
	}

	public static function native_missing_notice() {
		if ( ! Thuha_Language::native_available() && current_user_can( 'activate_plugins' ) ) {
			echo '<div class="notice notice-error"><p>ThuHa Native VI Publisher needs the rentbikehanoi-native-vi plugin (RBHVI_Language). Publishing is disabled until it is active.</p></div>';
		}
	}
}
