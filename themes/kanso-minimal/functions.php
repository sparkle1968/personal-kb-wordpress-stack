<?php

if (!defined('ABSPATH')) {
    exit;
}

add_action('after_setup_theme', function () {
    add_theme_support('wp-block-styles');
    add_theme_support('responsive-embeds');
    add_theme_support('post-thumbnails');
});

add_action('wp_enqueue_scripts', function () {
    $style_path = get_stylesheet_directory() . '/style.css';
    $style_version = file_exists($style_path) ? (string) filemtime($style_path) : wp_get_theme()->get('Version');
    wp_enqueue_style('kanso-minimal-style', get_stylesheet_uri(), [], $style_version);
});

function kanso_minimal_site_icon() {
    $icon_url = get_theme_file_uri('assets/kb-favicon.svg');
    $version = wp_get_theme()->get('Version');
    printf(
        '<link rel="icon" href="%s" type="image/svg+xml">' . "\n",
        esc_url(add_query_arg('v', $version, $icon_url))
    );
    printf(
        '<link rel="shortcut icon" href="%s" type="image/svg+xml">' . "\n",
        esc_url(add_query_arg('v', $version, $icon_url))
    );
}

add_action('wp_head', 'kanso_minimal_site_icon', 99);
add_action('login_head', 'kanso_minimal_site_icon', 99);
add_action('admin_head', 'kanso_minimal_site_icon', 99);
