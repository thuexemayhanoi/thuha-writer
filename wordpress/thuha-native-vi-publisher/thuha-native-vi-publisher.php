<?php
/**
 * Plugin Name: ThuHa Native VI Publisher
 * Description: Authenticated companion API for the ThuHa Writer factory. Read-only bilingual inventory and create-only, idempotent publishing that attaches the native Vietnamese marker (RBHVI_Language::set_vi) before a post goes live.
 * Version: 1.0.0
 * Requires at least: 6.2
 * Requires PHP: 7.4
 * Author: ThuHa Writer
 * License: GPL-2.0-or-later
 * Text Domain: thuha-native-vi-publisher
 *
 * Depends at runtime on the existing rentbikehanoi-native-vi plugin (class RBHVI_Language,
 * taxonomy rbhvi_language). It registers no public route, writes no SQL, and never
 * executes request-supplied code. See contract.json and readme.txt.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'THUHA_ADAPTER_VERSION', '1.0.0' );
define( 'THUHA_ADAPTER_DIR', __DIR__ );

require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-contract.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-auth.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-language.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-readback.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-inventory.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-writer.php';
require_once THUHA_ADAPTER_DIR . '/includes/class-thuha-routes.php';

// Application Password authentication is the only accepted credential; the flag lets
// permission callbacks refuse cookie sessions (which would otherwise need a nonce).
add_action( 'application_password_did_authenticate', array( 'Thuha_Auth', 'mark_application_password' ), 10, 2 );
add_action( 'rest_api_init', array( 'Thuha_Routes', 'register' ) );
add_action( 'admin_notices', array( 'Thuha_Auth', 'native_missing_notice' ) );
