<?php
/**
 * REST routes. Every route has an explicit permission callback; none is public.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Thuha_Routes {
	public static function register() {
		$ns = Thuha_Contract::NAMESPACE_;
		register_rest_route( $ns, '/preflight', array(
			'methods'             => 'GET',
			'callback'            => array( __CLASS__, 'preflight' ),
			'permission_callback' => array( 'Thuha_Auth', 'read_permission' ),
		) );
		register_rest_route( $ns, '/inventory', array(
			'methods'             => 'GET',
			'callback'            => array( __CLASS__, 'inventory' ),
			'permission_callback' => array( 'Thuha_Auth', 'read_permission' ),
			'args'                => array(
				'type'     => array( 'type' => 'string', 'default' => 'post' ),
				'status'   => array( 'type' => 'string', 'default' => 'publish' ),
				'page'     => array( 'type' => 'integer', 'default' => 1 ),
				'per_page' => array( 'type' => 'integer', 'default' => 100 ),
			),
		) );
		register_rest_route( $ns, '/categories', array(
			'methods'             => 'GET',
			'callback'            => array( __CLASS__, 'categories' ),
			'permission_callback' => array( 'Thuha_Auth', 'read_permission' ),
		) );
		register_rest_route( $ns, '/posts/by-key/(?P<key>[a-f0-9]{64})', array(
			'methods'             => 'GET',
			'callback'            => array( __CLASS__, 'reconcile' ),
			'permission_callback' => array( 'Thuha_Auth', 'read_permission' ),
		) );
		register_rest_route( $ns, '/posts', array(
			'methods'             => 'POST',
			'callback'            => array( __CLASS__, 'create' ),
			'permission_callback' => array( 'Thuha_Auth', 'write_permission' ),
		) );
	}

	private static function native_gate() {
		if ( ! Thuha_Language::native_available() ) {
			return Thuha_Contract::error( 'thuha_native_vi_missing', 'The native Vietnamese plugin API is unavailable.', 503 );
		}
		return true;
	}

	public static function preflight( $request ) {
		return rest_ensure_response( Thuha_Inventory::preflight() );
	}

	public static function inventory( $request ) {
		$gate = self::native_gate();
		if ( is_wp_error( $gate ) ) {
			return $gate;
		}
		$result = Thuha_Inventory::page( (string) $request->get_param( 'type' ), (string) $request->get_param( 'status' ), $request->get_param( 'page' ), $request->get_param( 'per_page' ) );
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}

	public static function categories( $request ) {
		$gate = self::native_gate();
		if ( is_wp_error( $gate ) ) {
			return $gate;
		}
		$result = Thuha_Inventory::categories();
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}

	public static function reconcile( $request ) {
		$gate = self::native_gate();
		if ( is_wp_error( $gate ) ) {
			return $gate;
		}
		$result = Thuha_Writer::reconcile( (string) $request->get_param( 'key' ) );
		return is_wp_error( $result ) ? $result : rest_ensure_response( $result );
	}

	public static function create( $request ) {
		$gate = self::native_gate();
		if ( is_wp_error( $gate ) ) {
			return $gate;
		}
		$fields = Thuha_Contract::validate_create( $request->get_json_params() );
		if ( is_wp_error( $fields ) ) {
			return $fields;
		}
		$result = Thuha_Writer::create( $fields );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$response = rest_ensure_response( $result );
		$response->set_status( ! empty( $result['created'] ) ? 201 : 200 );
		return $response;
	}
}
