<?php
/**
 * Workflow helpers for the family/kb WordPress sites.
 */

if (!defined('ABSPATH')) {
    exit;
}

function home_workflow_site_kind() {
    $host = parse_url(home_url('/'), PHP_URL_HOST);
    if (!$host && isset($_SERVER['HTTP_HOST'])) {
        $host = sanitize_text_field(wp_unslash($_SERVER['HTTP_HOST']));
    }

    return strpos((string) $host, 'family.') !== false ? 'family' : 'kb';
}

function home_workflow_site_profile() {
    if (home_workflow_site_kind() === 'family') {
        return [
            'body_class' => 'home-login-family',
            'eyebrow' => 'Family Stories',
            'title' => '布丁一家人',
            'subtitle' => '照片、视频和日常故事，只给家人慢慢翻看。',
        ];
    }

    return [
        'body_class' => 'home-login-kb',
        'eyebrow' => 'Quiet Archive',
        'title' => '个人知识库',
        'subtitle' => '链接、资料和全文归档，登录后进入安静的资料馆。',
    ];
}

function home_kb_uncategorized_category_id($create = false) {
    $preferred_name = '未分类';
    $preferred_slug = 'kb-uncategorized';

    $term = get_term_by('name', $preferred_name, 'category');
    if ($term instanceof WP_Term) {
        return (int) $term->term_id;
    }

    $term = get_term_by('slug', $preferred_slug, 'category');
    if ($term instanceof WP_Term) {
        wp_update_term($term->term_id, 'category', ['name' => $preferred_name]);
        return (int) $term->term_id;
    }

    foreach (['待读', '未读'] as $legacy_name) {
        $legacy_term = get_term_by('name', $legacy_name, 'category');
        if (!$legacy_term instanceof WP_Term) {
            continue;
        }

        $args = ['name' => $preferred_name];
        $slug_term = get_term_by('slug', $preferred_slug, 'category');
        if (!$slug_term instanceof WP_Term || (int) $slug_term->term_id === (int) $legacy_term->term_id) {
            $args['slug'] = $preferred_slug;
        }

        wp_update_term($legacy_term->term_id, 'category', $args);
        return (int) $legacy_term->term_id;
    }

    if (!$create) {
        return 0;
    }

    $result = wp_insert_term($preferred_name, 'category', ['slug' => $preferred_slug]);
    if (is_wp_error($result)) {
        $existing = $result->get_error_data('term_exists');
        return $existing ? (int) $existing : 0;
    }

    return isset($result['term_id']) ? (int) $result['term_id'] : 0;
}

add_action('init', function () {
    if (home_workflow_site_kind() === 'kb') {
        home_kb_uncategorized_category_id(true);
    }
});

function home_workflow_client_ip() {
    $candidates = [];

    foreach (['HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP', 'REMOTE_ADDR'] as $key) {
        if (!empty($_SERVER[$key])) {
            $candidates[] = sanitize_text_field(wp_unslash($_SERVER[$key]));
        }
    }

    if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        $forwarded = sanitize_text_field(wp_unslash($_SERVER['HTTP_X_FORWARDED_FOR']));
        $parts = explode(',', $forwarded);
        $candidates[] = trim($parts[0]);
    }

    foreach ($candidates as $candidate) {
        if (filter_var($candidate, FILTER_VALIDATE_IP)) {
            return $candidate;
        }
    }

    return 'unknown';
}

function home_workflow_login_attempt_key() {
    return 'home_login_attempts_' . md5(home_workflow_client_ip());
}

function home_workflow_public_share_query_arg() {
    return 'kb_share';
}

function home_workflow_public_share_short_base() {
    return 's';
}

function home_workflow_public_share_generate_token() {
    for ($attempt = 0; $attempt < 5; $attempt++) {
        $token = wp_generate_password(40, false, false);
        $existing = get_posts([
            'post_type' => 'post',
            'post_status' => 'any',
            'fields' => 'ids',
            'posts_per_page' => 1,
            'meta_key' => 'home_public_share_token',
            'meta_value' => $token,
            'no_found_rows' => true,
        ]);

        if (!$existing) {
            return $token;
        }
    }

    return wp_generate_password(48, false, false);
}

function home_workflow_public_share_clean_token($token) {
    if (!is_scalar($token)) {
        return '';
    }

    $token = sanitize_text_field((string) $token);
    return preg_replace('/[^A-Za-z0-9]/', '', $token);
}

function home_workflow_public_share_short_token_from_request() {
    $request_uri = isset($_SERVER['REQUEST_URI'])
        ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_URI']))
        : '';
    $path = (string) parse_url($request_uri, PHP_URL_PATH);
    if ($path === '') {
        return '';
    }

    $home_path = (string) parse_url(home_url('/'), PHP_URL_PATH);
    $home_path = '/' . trim($home_path, '/');
    if ($home_path !== '/' && strpos($path, $home_path . '/') === 0) {
        $path = substr($path, strlen($home_path));
    }

    $base = preg_quote(home_workflow_public_share_short_base(), '#');
    if (!preg_match('#^/' . $base . '/([A-Za-z0-9]+)/?$#', $path, $matches)) {
        return '';
    }

    return home_workflow_public_share_clean_token($matches[1]);
}

function home_workflow_public_share_request_token() {
    $key = home_workflow_public_share_query_arg();
    if (!empty($_GET[$key])) {
        return home_workflow_public_share_clean_token(wp_unslash($_GET[$key]));
    }

    return home_workflow_public_share_short_token_from_request();
}

function home_workflow_public_share_enabled($post_id) {
    return get_post_meta($post_id, 'home_public_share_enabled', true) === '1';
}

function home_workflow_public_share_ensure_token($post_id) {
    $token = home_workflow_public_share_clean_token(get_post_meta($post_id, 'home_public_share_token', true));
    if ($token !== '') {
        return $token;
    }

    $token = home_workflow_public_share_generate_token();
    update_post_meta($post_id, 'home_public_share_token', $token);
    return $token;
}

function home_workflow_public_share_url($post_id) {
    $token = home_workflow_public_share_ensure_token($post_id);
    return home_url('/' . home_workflow_public_share_short_base() . '/' . rawurlencode($token) . '/');
}

function home_workflow_public_share_post_id_for_token($token) {
    $token = home_workflow_public_share_clean_token($token);
    if ($token === '') {
        return 0;
    }

    $posts = get_posts([
        'post_type' => 'post',
        'post_status' => 'publish',
        'fields' => 'ids',
        'posts_per_page' => 1,
        'meta_key' => 'home_public_share_token',
        'meta_value' => $token,
        'no_found_rows' => true,
    ]);

    $post_id = isset($posts[0]) ? absint($posts[0]) : 0;
    if (!$post_id || !home_workflow_public_share_enabled($post_id)) {
        return 0;
    }

    $stored = home_workflow_public_share_clean_token(get_post_meta($post_id, 'home_public_share_token', true));
    return $stored !== '' && hash_equals($stored, $token) ? $post_id : 0;
}

function home_workflow_public_share_token_is_valid($post_id, $token = null) {
    $post = get_post($post_id);
    if (!$post || $post->post_type !== 'post' || $post->post_status !== 'publish') {
        return false;
    }

    if (!home_workflow_public_share_enabled($post_id)) {
        return false;
    }

    $token = $token === null ? home_workflow_public_share_request_token() : home_workflow_public_share_clean_token($token);
    if ($token === '') {
        return false;
    }

    $stored = home_workflow_public_share_clean_token(get_post_meta($post_id, 'home_public_share_token', true));
    return $stored !== '' && hash_equals($stored, $token);
}

function home_workflow_current_request_is_public_share() {
    if (!is_singular('post')) {
        return false;
    }

    return home_workflow_public_share_token_is_valid(get_queried_object_id());
}

function home_workflow_current_request_is_public_kb_post() {
    if (home_workflow_site_kind() !== 'kb' || !is_singular('post')) {
        return false;
    }

    $post = get_post(get_queried_object_id());
    return $post && $post->post_type === 'post' && $post->post_status === 'publish';
}

function home_workflow_current_user_can_share_posts() {
    if (!is_user_logged_in()) {
        return false;
    }

    return current_user_can('read');
}

function home_workflow_current_user_can_share_post($post_id) {
    if (current_user_can('edit_post', $post_id)) {
        return true;
    }

    return home_workflow_current_user_can_share_posts() && get_post_status($post_id) === 'publish';
}

add_filter('request', function ($query_vars) {
    $token = home_workflow_public_share_short_token_from_request();
    if ($token === '') {
        return $query_vars;
    }

    $post_id = home_workflow_public_share_post_id_for_token($token);
    if (!$post_id) {
        return $query_vars;
    }

    return [
        'p' => $post_id,
        'post_type' => 'post',
    ];
});

add_filter('redirect_canonical', function ($redirect_url, $requested_url) {
    if (home_workflow_public_share_short_token_from_request() !== '') {
        return false;
    }

    return $redirect_url;
}, 10, 2);

add_filter('user_has_cap', function ($allcaps, $caps, $args, $user) {
    if (!$user instanceof WP_User || $user->user_login !== 'site-admin') {
        return $allcaps;
    }

    foreach ([
        'read',
        'edit_posts',
        'edit_others_posts',
        'edit_published_posts',
        'edit_private_posts',
        'publish_posts',
        'read_private_posts',
        'upload_files',
        'manage_categories',
        'assign_categories',
        'delete_posts',
        'delete_others_posts',
        'delete_published_posts',
        'delete_private_posts',
        'create_users',
        'delete_users',
        'edit_users',
        'list_users',
        'promote_users',
    ] as $capability) {
        $allcaps[$capability] = true;
    }

    return $allcaps;
}, 10, 4);

function home_workflow_kb_account_role_options() {
    return [
        'kb-viewer' => [
            'label' => '阅读账号',
            'description' => '只能登录阅读已发布资料，不能新增、修改或删除内容。',
        ],
        'kb-author' => [
            'label' => '整理账号',
            'description' => '可以新增、发布和维护自己的资料，不能管理分类或其他人的内容。',
        ],
        'editor' => [
            'label' => '发布账号',
            'description' => '可以新增、发布、编辑、删除资料，并管理分类。',
        ],
    ];
}

function home_workflow_kb_custom_role_capabilities($role) {
    if ($role === 'kb-viewer') {
        return [
            'read' => true,
            'kb_viewer' => true,
        ];
    }

    if ($role === 'kb-author') {
        return [
            'read' => true,
            'edit_posts' => true,
            'edit_published_posts' => true,
            'publish_posts' => true,
            'delete_posts' => true,
            'delete_published_posts' => true,
            'upload_files' => true,
            'assign_categories' => true,
        ];
    }

    return [];
}

add_action('init', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return;
    }

    foreach (home_workflow_kb_account_role_options() as $role => $option) {
        if ($role === 'editor') {
            continue;
        }

        $capabilities = home_workflow_kb_custom_role_capabilities($role);
        $wp_role = get_role($role);
        if (!$wp_role) {
            add_role($role, $option['label'], $capabilities);
            continue;
        }

        foreach ($capabilities as $capability => $grant) {
            $wp_role->add_cap($capability, $grant);
        }
    }
});

function home_workflow_kb_can_manage_accounts() {
    if (home_workflow_site_kind() !== 'kb' || !is_user_logged_in()) {
        return false;
    }

    $user = wp_get_current_user();
    return $user instanceof WP_User && $user->user_login === 'site-admin';
}

function home_workflow_kb_protected_account_logins() {
    $logins = ['site-admin'];

    foreach (['WP_ADMIN_USER', 'WP_PUBLISHER_USER', 'WP_KB_API_USER'] as $key) {
        $value = trim((string) getenv($key));
        if ($value !== '') {
            $logins[] = $value;
        }
    }

    return array_values(array_unique($logins));
}

function home_workflow_kb_account_is_protected(WP_User $user) {
    if (in_array('administrator', (array) $user->roles, true)) {
        return true;
    }

    return in_array($user->user_login, home_workflow_kb_protected_account_logins(), true);
}

function home_workflow_kb_account_primary_role(WP_User $user) {
    foreach (array_keys(home_workflow_kb_account_role_options()) as $role) {
        if (in_array($role, (array) $user->roles, true)) {
            return $role;
        }
    }

    if (in_array('administrator', (array) $user->roles, true)) {
        return 'administrator';
    }

    return isset($user->roles[0]) ? (string) $user->roles[0] : '';
}

function home_workflow_kb_account_role_label($role) {
    $options = home_workflow_kb_account_role_options();
    if (isset($options[$role])) {
        return $options[$role]['label'];
    }

    if ($role === 'administrator') {
        return '管理账号';
    }

    if ($role === '') {
        return '未分配';
    }

    return translate_user_role(ucwords(str_replace(['_', '-'], ' ', $role)));
}

function home_workflow_kb_sync_default_settings() {
    return [
        'mode' => 'schedule',
        'interval_minutes' => 60,
        'realtime_seconds' => 30,
        'updated_at' => '',
    ];
}

function home_workflow_kb_sanitize_sync_settings($raw_settings) {
    $defaults = home_workflow_kb_sync_default_settings();
    $raw_settings = is_array($raw_settings) ? $raw_settings : [];

    $mode = isset($raw_settings['mode']) ? sanitize_key((string) $raw_settings['mode']) : $defaults['mode'];
    if (!in_array($mode, ['schedule', 'realtime'], true)) {
        $mode = $defaults['mode'];
    }

    $interval_minutes = isset($raw_settings['interval_minutes']) ? absint($raw_settings['interval_minutes']) : $defaults['interval_minutes'];
    $interval_minutes = min(1440, max(5, $interval_minutes));

    $realtime_seconds = isset($raw_settings['realtime_seconds']) ? absint($raw_settings['realtime_seconds']) : $defaults['realtime_seconds'];
    $realtime_seconds = min(300, max(15, $realtime_seconds));

    $updated_at = isset($raw_settings['updated_at']) ? sanitize_text_field((string) $raw_settings['updated_at']) : '';

    return [
        'mode' => $mode,
        'interval_minutes' => $interval_minutes,
        'realtime_seconds' => $realtime_seconds,
        'updated_at' => $updated_at,
    ];
}

function home_workflow_kb_sync_settings() {
    $stored = get_option('home_kb_obsidian_sync_settings', []);
    return home_workflow_kb_sanitize_sync_settings(array_merge(home_workflow_kb_sync_default_settings(), is_array($stored) ? $stored : []));
}

function home_workflow_kb_sync_poll_seconds($settings = null) {
    $settings = $settings === null ? home_workflow_kb_sync_settings() : home_workflow_kb_sanitize_sync_settings($settings);
    if ($settings['mode'] === 'realtime') {
        return (int) $settings['realtime_seconds'];
    }

    return (int) $settings['interval_minutes'] * 60;
}

function home_workflow_kb_action_notice_window($message, $title = '操作完成') {
    static $instance = 0;
    $instance++;
    $title_id = 'kb-action-notice-title-' . $instance;
    $body_id = 'kb-action-notice-body-' . $instance;

    ob_start();
    ?>
    <div class="kb-action-notice-window" role="alertdialog" aria-modal="true" aria-labelledby="<?php echo esc_attr($title_id); ?>" aria-describedby="<?php echo esc_attr($body_id); ?>" data-kb-action-notice>
        <button class="kb-action-notice-backdrop" type="button" aria-label="关闭提示" data-kb-action-notice-close></button>
        <div class="kb-action-notice-card">
            <span>完成</span>
            <h2 id="<?php echo esc_attr($title_id); ?>"><?php echo esc_html($title); ?></h2>
            <p class="kb-action-notice-message" id="<?php echo esc_attr($body_id); ?>"><?php echo esc_html($message); ?></p>
            <button class="kb-action-notice-confirm" type="button" data-kb-action-notice-close autofocus>知道了</button>
        </div>
    </div>
    <script>
        (function () {
            document.addEventListener('click', function (event) {
                var close = event.target.closest('[data-kb-action-notice-close]');
                if (!close) {
                    return;
                }
                var notice = close.closest('[data-kb-action-notice]');
                if (notice) {
                    notice.hidden = true;
                }
            });
            document.addEventListener('keydown', function (event) {
                if (event.key !== 'Escape') {
                    return;
                }
                document.querySelectorAll('[data-kb-action-notice]').forEach(function (notice) {
                    notice.hidden = true;
                });
            });
        })();
    </script>
    <?php

    return home_workflow_kb_compact_html(ob_get_clean());
}

add_action('init', function () {
    register_post_meta('post', 'source_url', [
        'type' => 'string',
        'single' => true,
        'show_in_rest' => true,
        'sanitize_callback' => 'esc_url_raw',
        'auth_callback' => function () {
            return current_user_can('edit_posts');
        },
    ]);

    register_post_meta('post', 'source_site', [
        'type' => 'string',
        'single' => true,
        'show_in_rest' => true,
        'sanitize_callback' => 'sanitize_text_field',
        'auth_callback' => function () {
            return current_user_can('edit_posts');
        },
    ]);

    register_post_meta('post', 'source_author', [
        'type' => 'string',
        'single' => true,
        'show_in_rest' => true,
        'sanitize_callback' => 'sanitize_text_field',
        'auth_callback' => function () {
            return current_user_can('edit_posts');
        },
    ]);

    register_post_meta('post', 'home_kb_form_attachment_ids', [
        'type' => 'array',
        'single' => true,
        'show_in_rest' => false,
        'sanitize_callback' => 'home_workflow_kb_sanitize_id_list',
        'auth_callback' => function () {
            return current_user_can('edit_posts');
        },
    ]);

    register_post_meta('post', 'home_public_share_enabled', [
        'type' => 'boolean',
        'single' => true,
        'show_in_rest' => false,
        'sanitize_callback' => 'rest_sanitize_boolean',
        'auth_callback' => function () {
            return home_workflow_current_user_can_share_posts();
        },
    ]);

    register_post_meta('post', 'home_public_share_token', [
        'type' => 'string',
        'single' => true,
        'show_in_rest' => false,
        'sanitize_callback' => 'home_workflow_public_share_clean_token',
        'auth_callback' => function () {
            return home_workflow_current_user_can_share_posts();
        },
    ]);
});

add_action('rest_api_init', function () {
    register_rest_route('home-kb/v1', '/obsidian-sync-settings', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => function () {
            return home_workflow_site_kind() === 'kb' && current_user_can('edit_posts');
        },
        'callback' => function () {
            $settings = home_workflow_kb_sync_settings();
            return rest_ensure_response([
                'mode' => $settings['mode'],
                'interval_minutes' => (int) $settings['interval_minutes'],
                'realtime_seconds' => (int) $settings['realtime_seconds'],
                'poll_seconds' => home_workflow_kb_sync_poll_seconds($settings),
                'updated_at' => $settings['updated_at'],
            ]);
        },
    ]);
});

add_action('add_meta_boxes', function () {
    add_meta_box(
        'home-public-share',
        '公开分享链接',
        'home_workflow_public_share_meta_box',
        'post',
        'side',
        'default'
    );
});

function home_workflow_public_share_meta_box($post) {
    $enabled = home_workflow_public_share_enabled($post->ID);
    $token = home_workflow_public_share_clean_token(get_post_meta($post->ID, 'home_public_share_token', true));
    $is_published = get_post_status($post) === 'publish';
    $share_url = $enabled && $token !== '' && $is_published ? home_workflow_public_share_url($post->ID) : '';

    wp_nonce_field('home_public_share_save', 'home_public_share_nonce');
    ?>
    <p>
        <label>
            <input type="checkbox" name="home_public_share_enabled" value="1" <?php checked($enabled); ?>>
            允许持有链接的人免登录阅读这篇文章
        </label>
    </p>
    <p class="description">只对已发布文章生效。开启后，文章正文和登录可见全文归档都会对持有链接的人可见。</p>
    <?php if (!$is_published) : ?>
        <p class="description"><strong>提示：</strong>这篇文章发布后，分享链接才会生效。</p>
    <?php endif; ?>
    <?php if ($share_url) : ?>
        <p>
            <label for="home-public-share-url"><strong>分享链接</strong></label>
            <input id="home-public-share-url" type="text" readonly value="<?php echo esc_attr($share_url); ?>" style="width:100%;">
        </p>
        <p>
            <button type="button" class="button" data-home-copy-share="#home-public-share-url">复制链接</button>
        </p>
    <?php else : ?>
        <p class="description">勾选后保存文章，会生成可复制的分享链接。</p>
    <?php endif; ?>
    <p>
        <label>
            <input type="checkbox" name="home_public_share_regenerate" value="1">
            重新生成链接，让旧链接失效
        </label>
    </p>
    <?php
}

add_action('save_post_post', function ($post_id) {
    if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
        return;
    }
    if (wp_is_post_revision($post_id)) {
        return;
    }
    if (!isset($_POST['home_public_share_nonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['home_public_share_nonce'])), 'home_public_share_save')) {
        return;
    }
    if (!home_workflow_current_user_can_share_post($post_id)) {
        return;
    }

    $enabled = isset($_POST['home_public_share_enabled']) ? '1' : '0';
    update_post_meta($post_id, 'home_public_share_enabled', $enabled);

    $regenerate = isset($_POST['home_public_share_regenerate']);
    $token = home_workflow_public_share_clean_token(get_post_meta($post_id, 'home_public_share_token', true));
    if ($regenerate || ($enabled === '1' && $token === '')) {
        update_post_meta($post_id, 'home_public_share_token', home_workflow_public_share_generate_token());
    }
});

add_action('admin_footer-post.php', 'home_workflow_public_share_admin_script');
add_action('admin_footer-post-new.php', 'home_workflow_public_share_admin_script');
add_action('wp_footer', 'home_workflow_public_share_frontend_script');

function home_workflow_public_share_admin_script() {
    $screen = get_current_screen();
    if (!$screen || $screen->post_type !== 'post') {
        return;
    }

    home_workflow_public_share_copy_script();
}

function home_workflow_public_share_frontend_script() {
    if (!is_singular('post') || !home_workflow_current_user_can_share_post(get_queried_object_id())) {
        return;
    }

    home_workflow_public_share_copy_script();
}

function home_workflow_public_share_copy_script() {
    ?>
    <script>
    document.addEventListener('click', function (event) {
        var button = event.target.closest('[data-home-copy-share]');
        if (!button) {
            return;
        }
        var input = document.querySelector(button.getAttribute('data-home-copy-share'));
        if (!input) {
            return;
        }
        input.select();
        input.setSelectionRange(0, input.value.length);
        navigator.clipboard.writeText(input.value).then(function () {
            button.textContent = '已复制';
            setTimeout(function () {
                button.textContent = '复制链接';
            }, 1500);
        }).catch(function () {
            document.execCommand('copy');
        });
    });
    </script>
    <?php
}

add_action('template_redirect', function () {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || empty($_POST['home_public_share_action'])) {
        return;
    }

    if (!is_singular('post')) {
        return;
    }

    $post_id = get_queried_object_id();
    if (!home_workflow_current_user_can_share_post($post_id)) {
        wp_die('你没有权限分享这篇文章。', '无权分享', ['response' => 403]);
    }

    if (empty($_POST['home_public_share_nonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['home_public_share_nonce'])), 'home_public_share_frontend_' . $post_id)) {
        wp_die('分享请求已过期，请刷新页面后重试。', '请求已过期', ['response' => 403]);
    }

    $action = sanitize_key(wp_unslash($_POST['home_public_share_action']));
    if ($action === 'disable') {
        update_post_meta($post_id, 'home_public_share_enabled', '0');
    } elseif ($action === 'regenerate') {
        update_post_meta($post_id, 'home_public_share_enabled', '1');
        update_post_meta($post_id, 'home_public_share_token', home_workflow_public_share_generate_token());
    } else {
        update_post_meta($post_id, 'home_public_share_enabled', '1');
        home_workflow_public_share_ensure_token($post_id);
        $action = 'enable';
    }

    wp_safe_redirect(add_query_arg('share_updated', $action, get_permalink($post_id)));
    exit;
}, 0);

function home_workflow_public_share_controls($post_id) {
    if (!home_workflow_current_user_can_share_post($post_id)) {
        return '';
    }

    $enabled = home_workflow_public_share_enabled($post_id);
    $share_url = $enabled ? home_workflow_public_share_url($post_id) : '';
    $updated = isset($_GET['share_updated']) ? sanitize_key(wp_unslash($_GET['share_updated'])) : '';

    ob_start();
    ?>
    <aside class="source-note public-share-tools">
        <strong>公开分享：</strong>
        <?php if ($updated === 'enable') : ?>
            <span>分享链接已生成。</span>
        <?php elseif ($updated === 'regenerate') : ?>
            <span>新分享链接已生成，旧链接已经失效。</span>
        <?php elseif ($updated === 'disable') : ?>
            <span>分享链接已关闭。</span>
        <?php else : ?>
            <span>登录的 viewer 账号可以把这一篇文章分享给未登录的人。</span>
        <?php endif; ?>

        <?php if ($enabled && $share_url) : ?>
            <p>
                <input id="home-public-share-url-frontend" type="text" readonly value="<?php echo esc_attr($share_url); ?>" style="width:100%;max-width:42rem;">
                <button type="button" data-home-copy-share="#home-public-share-url-frontend">复制链接</button>
            </p>
        <?php endif; ?>

        <form method="post" action="<?php echo esc_url(get_permalink($post_id)); ?>" style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;">
            <?php echo wp_nonce_field('home_public_share_frontend_' . $post_id, 'home_public_share_nonce', true, false); ?>
            <?php if ($enabled) : ?>
                <button type="submit" name="home_public_share_action" value="regenerate">重新生成链接</button>
                <button type="submit" name="home_public_share_action" value="disable">关闭分享</button>
            <?php else : ?>
                <button type="submit" name="home_public_share_action" value="enable">生成分享链接</button>
            <?php endif; ?>
        </form>
    </aside>
    <?php
    return trim((string) ob_get_clean());
}

add_filter('manage_post_posts_columns', function ($columns) {
    $updated = [];
    foreach ($columns as $key => $label) {
        $updated[$key] = $label;
        if ($key === 'title') {
            $updated['home_public_share'] = '分享';
        }
    }

    return $updated;
});

add_action('manage_post_posts_custom_column', function ($column, $post_id) {
    if ($column !== 'home_public_share') {
        return;
    }

    if (!home_workflow_public_share_enabled($post_id) || get_post_status($post_id) !== 'publish') {
        echo '<span aria-label="未开启公开分享">-</span>';
        return;
    }

    echo '<a href="' . esc_url(home_workflow_public_share_url($post_id)) . '" target="_blank" rel="noopener noreferrer">打开</a>';
}, 10, 2);

add_filter('authenticate', function ($user, $username, $password) {
    if (empty($username) || empty($password)) {
        return $user;
    }

    $attempts = (int) get_transient(home_workflow_login_attempt_key());
    if ($attempts >= 8) {
        return new WP_Error(
            'home_too_many_login_attempts',
            '登录尝试过多，请 20 分钟后再试。'
        );
    }

    return $user;
}, 30, 3);

add_action('wp_login_failed', function () {
    $key = home_workflow_login_attempt_key();
    $attempts = (int) get_transient($key);
    set_transient($key, $attempts + 1, 20 * MINUTE_IN_SECONDS);
}, 10, 0);

add_action('wp_login', function () {
    delete_transient(home_workflow_login_attempt_key());
}, 10, 0);

add_action('template_redirect', function () {
    if (is_user_logged_in() || is_admin() || wp_doing_ajax() || wp_doing_cron()) {
        return;
    }

    if (home_workflow_current_request_is_public_kb_post()) {
        return;
    }

    if (home_workflow_current_request_is_public_share()) {
        return;
    }

    $request_uri = isset($_SERVER['REQUEST_URI'])
        ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_URI']))
        : '/';

    wp_safe_redirect(wp_login_url(home_url($request_uri)));
    exit;
}, 1);

add_filter('rest_authentication_errors', function ($result) {
    if (is_wp_error($result) || is_user_logged_in()) {
        return $result;
    }

    return new WP_Error(
        'home_login_required',
        '需要登录后才能访问这个网站内容。',
        ['status' => 401]
    );
}, 100);

add_shortcode('private_archive', function ($atts, $content = '') {
    if (is_user_logged_in() || home_workflow_current_request_is_public_share() || home_workflow_current_request_is_public_kb_post()) {
        $title = is_user_logged_in() ? '登录可见全文归档' : '全文归档';
        return '<section class="private-archive"><h2>' . esc_html($title) . '</h2>' . do_shortcode($content) . '</section>';
    }

    return '<section class="private-archive private-archive-locked"><h2>全文归档</h2><p>这部分内容仅家人登录后可见，公开页面保留摘要、短摘录和来源链接。</p></section>';
});

function home_workflow_kb_source_search_join($join, $query) {
    if (!$query instanceof WP_Query || !$query->get('kb_source_search')) {
        return $join;
    }
    if (strpos($join, 'kb_source_meta') !== false) {
        return $join;
    }

    global $wpdb;
    return $join . " LEFT JOIN {$wpdb->postmeta} AS kb_source_meta ON ({$wpdb->posts}.ID = kb_source_meta.post_id AND kb_source_meta.meta_key IN ('source_url', 'source_site', 'source_author'))";
}

function home_workflow_kb_source_search_sql($search, $query) {
    if (!$query instanceof WP_Query || !$query->get('kb_source_search')) {
        return $search;
    }

    $term = sanitize_text_field((string) $query->get('kb_source_search'));
    if ($term === '') {
        return $search;
    }

    global $wpdb;
    $source_search = $wpdb->prepare('kb_source_meta.meta_value LIKE %s', '%' . $wpdb->esc_like($term) . '%');
    $search = trim((string) $search);
    if ($search === '') {
        return ' AND (' . $source_search . ')';
    }

    $search = preg_replace('/^\s*AND\s*/i', '', $search);
    return ' AND ((' . $search . ') OR (' . $source_search . '))';
}

function home_workflow_kb_source_search_distinct($distinct, $query) {
    if ($query instanceof WP_Query && $query->get('kb_source_search')) {
        return 'DISTINCT';
    }

    return $distinct;
}

add_filter('posts_join', 'home_workflow_kb_source_search_join', 10, 2);
add_filter('posts_search', 'home_workflow_kb_source_search_sql', 10, 2);
add_filter('posts_distinct', 'home_workflow_kb_source_search_distinct', 10, 2);

function home_workflow_kb_pagination_pages($current, $total) {
    $current = max(1, (int) $current);
    $total = max(1, (int) $total);
    if ($total <= 7) {
        return range(1, $total);
    }

    $pages = [1, $total, $current - 1, $current, $current + 1];
    if ($current <= 3) {
        $pages = array_merge($pages, [2, 3, 4]);
    }
    if ($current >= $total - 2) {
        $pages = array_merge($pages, [$total - 3, $total - 2, $total - 1]);
    }

    $pages = array_values(array_unique(array_filter(
        $pages,
        function ($page) use ($total) {
            return $page >= 1 && $page <= $total;
        }
    )));
    sort($pages, SORT_NUMERIC);

    $items = [];
    $previous = 0;
    foreach ($pages as $page) {
        if ($previous && $page > $previous + 1) {
            $items[] = 'ellipsis';
        }
        $items[] = $page;
        $previous = $page;
    }

    return $items;
}

function home_workflow_kb_sanitize_id_list($ids) {
    if (!is_array($ids)) {
        return [];
    }

    return array_values(array_unique(array_filter(array_map('absint', $ids))));
}

function home_workflow_kb_categories() {
    return array_values(array_filter(
        get_categories([
            'hide_empty' => false,
            'orderby' => 'name',
            'order' => 'ASC',
        ]),
        function ($category) {
            return $category->slug !== 'uncategorized';
        }
    ));
}

function home_workflow_kb_category_counts($categories, $visible_statuses) {
    $category_counts = [];
    foreach ($categories as $category) {
        $category_count_query = new WP_Query([
            'post_type' => 'post',
            'post_status' => $visible_statuses,
            'posts_per_page' => 1,
            'fields' => 'ids',
            'cat' => $category->term_id,
        ]);
        $category_counts[$category->term_id] = (int) $category_count_query->found_posts;
        wp_reset_postdata();
    }

    return $category_counts;
}

function home_workflow_kb_valid_category_id($category_id) {
    $category_id = absint($category_id);
    if (!$category_id) {
        return 0;
    }

    $category = get_term($category_id, 'category');
    if (!$category instanceof WP_Term || is_wp_error($category) || $category->slug === 'uncategorized') {
        return 0;
    }

    return (int) $category->term_id;
}

function home_workflow_kb_default_category_id() {
    foreach (['未分类', '待读', '资料'] as $category_name) {
        $category = get_term_by('name', $category_name, 'category');
        if ($category instanceof WP_Term && $category->slug !== 'uncategorized') {
            return (int) $category->term_id;
        }
    }

    $categories = home_workflow_kb_categories();
    return $categories ? (int) $categories[0]->term_id : 0;
}

function home_workflow_kb_last_category_cookie_id() {
    if (empty($_COOKIE['home_kb_last_category'])) {
        return 0;
    }

    return home_workflow_kb_valid_category_id(wp_unslash($_COOKIE['home_kb_last_category']));
}

function home_workflow_kb_request_category_id() {
    if (isset($_GET['kb_category'])) {
        return home_workflow_kb_valid_category_id(wp_unslash($_GET['kb_category']));
    }

    if (!empty($_GET['kb_view'])) {
        return home_workflow_kb_last_category_cookie_id() ?: home_workflow_kb_default_category_id();
    }

    return 0;
}

add_action('template_redirect', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return;
    }

    if (isset($_GET['kb_category'])) {
        $category_id = home_workflow_kb_valid_category_id(wp_unslash($_GET['kb_category']));
        if ($category_id) {
            setcookie('home_kb_last_category', (string) $category_id, [
                'expires' => time() + YEAR_IN_SECONDS,
                'path' => COOKIEPATH ?: '/',
                'domain' => COOKIE_DOMAIN,
                'secure' => is_ssl(),
                'httponly' => true,
                'samesite' => 'Lax',
            ]);
        }
    }

    if (isset($_GET['kb_category']) || empty($_GET['kb_view'])) {
        return;
    }

    $view = sanitize_key(wp_unslash($_GET['kb_view']));
    if (!in_array($view, ['new', 'trash', 'sync', 'accounts'], true)) {
        return;
    }

    $category_id = home_workflow_kb_request_category_id();
    if (!$category_id) {
        return;
    }

    $args = ['kb_view' => $view, 'kb_category' => $category_id];
    if ($view === 'trash' && isset($_GET['kb_trash_page'])) {
        $args['kb_trash_page'] = max(1, absint($_GET['kb_trash_page']));
    }
    foreach (['kb_account_notice', 'kb_sync_notice'] as $notice_key) {
        if (isset($_GET[$notice_key])) {
            $args[$notice_key] = sanitize_key(wp_unslash($_GET[$notice_key]));
        }
    }

    wp_safe_redirect(add_query_arg($args, home_url('/')), 302);
    exit;
}, 0);

function home_workflow_kb_home_url_with_category($category_id = 0, $fragment = '') {
    $url = $category_id ? add_query_arg(['kb_category' => $category_id], home_url('/')) : home_url('/');
    if ($fragment !== '') {
        $url .= '#' . ltrim($fragment, '#');
    }

    return $url;
}

function home_workflow_kb_view_url($view, $category_id = 0, $extra_args = []) {
    $args = array_merge(['kb_view' => $view], $extra_args);
    if ($category_id) {
        $args['kb_category'] = $category_id;
    }

    return add_query_arg($args, home_url('/'));
}

function home_workflow_kb_style_modes() {
    return [
        'minimal' => '精致极简',
        'magazine' => '杂志编辑',
    ];
}

function home_workflow_kb_style_mode() {
    $modes = array_keys(home_workflow_kb_style_modes());
    $mode = '';

    if (isset($_GET['kb_style'])) {
        $mode = sanitize_key(wp_unslash($_GET['kb_style']));
    } elseif (isset($_COOKIE['home_kb_style'])) {
        $mode = sanitize_key(wp_unslash($_COOKIE['home_kb_style']));
    }

    return in_array($mode, $modes, true) ? $mode : 'minimal';
}

add_action('init', function () {
    if (home_workflow_site_kind() !== 'kb' || !isset($_GET['kb_style'])) {
        return;
    }

    $mode = sanitize_key(wp_unslash($_GET['kb_style']));
    if (!array_key_exists($mode, home_workflow_kb_style_modes())) {
        return;
    }

    setcookie(
        'home_kb_style',
        $mode,
        time() + YEAR_IN_SECONDS,
        COOKIEPATH ?: '/',
        COOKIE_DOMAIN,
        is_ssl(),
        false
    );
});

add_filter('body_class', function ($classes) {
    if (home_workflow_site_kind() === 'kb') {
        $classes[] = 'kb-style-' . home_workflow_kb_style_mode();
    }

    return $classes;
});

function home_workflow_kb_style_switch() {
    $current_mode = home_workflow_kb_style_mode();
    $modes = home_workflow_kb_style_modes();

    ob_start();
    ?>
    <div class="kb-style-switch" aria-label="版式切换">
        <span>版式</span>
        <div>
            <?php foreach ($modes as $mode => $label) : ?>
                <a
                    href="<?php echo esc_url(add_query_arg('kb_style', $mode)); ?>"
                    class="<?php echo $current_mode === $mode ? 'is-active' : ''; ?>"
                    data-kb-style-mode="<?php echo esc_attr($mode); ?>"
                    aria-pressed="<?php echo $current_mode === $mode ? 'true' : 'false'; ?>"
                ><?php echo esc_html($label); ?></a>
            <?php endforeach; ?>
        </div>
    </div>
    <?php

    return trim((string) ob_get_clean());
}

add_action('wp_footer', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return;
    }
    ?>
    <script>
    (function () {
        var modes = ['minimal', 'magazine'];

        function setMode(mode) {
            if (modes.indexOf(mode) === -1) {
                return;
            }
            document.body.classList.remove('kb-style-minimal', 'kb-style-magazine');
            document.body.classList.add('kb-style-' + mode);
            document.cookie = 'home_kb_style=' + mode + ';path=/;max-age=31536000;samesite=lax';

            document.querySelectorAll('[data-kb-style-mode]').forEach(function (item) {
                var active = item.getAttribute('data-kb-style-mode') === mode;
                item.classList.toggle('is-active', active);
                item.setAttribute('aria-pressed', active ? 'true' : 'false');
            });

            if (window.history && window.URL) {
                var url = new URL(window.location.href);
                url.searchParams.set('kb_style', mode);
                window.history.replaceState(null, '', url.toString());
            }
        }

        document.addEventListener('click', function (event) {
            var trigger = event.target.closest('[data-kb-style-mode]');
            if (!trigger) {
                return;
            }
            event.preventDefault();
            setMode(trigger.getAttribute('data-kb-style-mode'));
        });
    })();
    </script>
    <?php
});

function home_workflow_kb_sidebar_critical_css() {
    static $printed = false;
    if ($printed) {
        return '';
    }
    $printed = true;

    return '<style id="kb-sidebar-critical-css">'
        . '@media (min-width:901px){'
        . '.kb-sidebar{display:flex!important;flex-direction:column!important;align-items:stretch!important;height:100vh!important;min-height:100vh!important;overflow-y:auto!important;}'
        . '.kb-sidebar br{display:none!important;}'
        . '.kb-sidebar .kb-side-title,.kb-sidebar .kb-side-nav,.kb-sidebar .kb-side-block{flex:0 0 auto!important;}'
        . '.kb-sidebar .kb-side-nav{display:flex!important;flex-direction:column!important;justify-content:flex-start!important;align-content:flex-start!important;gap:4px!important;margin:26px 0 20px!important;height:auto!important;min-height:0!important;}'
        . '.kb-sidebar .kb-side-nav a{display:flex!important;align-items:center!important;flex:0 0 30px!important;height:30px!important;min-height:30px!important;max-height:30px!important;margin:0!important;padding:0 9px!important;font-family:var(--kanso-sans)!important;font-size:13px!important;font-weight:600!important;line-height:1.2!important;letter-spacing:0!important;transform:none!important;}'
        . '.kb-sidebar .kb-side-nav a.kb-nav-short-label{font-size:14px!important;font-weight:650!important;}'
        . '.kb-sidebar .kb-side-nav a.kb-nav-medium-label{font-size:13.5px!important;font-weight:625!important;}'
        . '.kb-sidebar .kb-side-block{display:flex!important;flex-direction:column!important;justify-content:flex-start!important;align-content:flex-start!important;gap:4px!important;padding-top:16px!important;height:auto!important;min-height:0!important;}'
        . '.kb-sidebar .kb-side-block>a{display:flex!important;align-items:center!important;flex:0 0 29px!important;height:29px!important;min-height:29px!important;max-height:29px!important;margin:0!important;padding:0 9px!important;font-size:13px!important;font-weight:590!important;line-height:1.2!important;}'
        . '.kb-sidebar .kb-side-block>span{margin:0 0 4px!important;font-size:12px!important;font-weight:700!important;}'
        . '.kb-sidebar .kb-logout-wrap{position:static!important;margin-top:auto!important;padding-top:20px!important;}'
        . '}'
        . '</style>';
}

function home_workflow_kb_nav_label_class($label) {
    $length = preg_match_all('/./u', (string) $label);
    if ($length <= 2) {
        return 'kb-nav-short-label';
    }
    if ($length === 3) {
        return 'kb-nav-medium-label';
    }

    return 'kb-nav-long-label';
}

function home_workflow_kb_nav_link($url, $label, $is_active = false, $extra_attrs = '') {
    $classes = ['kb-nav-item', home_workflow_kb_nav_label_class($label)];
    if ($is_active) {
        $classes[] = 'is-active';
    }
    $attrs = $is_active ? ' aria-current="page"' : '';
    if ($extra_attrs !== '') {
        $attrs .= ' ' . trim($extra_attrs);
    }

    return sprintf(
        '<a href="%s" class="%s"%s>%s</a>',
        esc_url($url),
        esc_attr(implode(' ', $classes)),
        $attrs,
        esc_html($label)
    );
}

function home_workflow_kb_sidebar($active_view, $categories, $category_counts, $can_edit, $options = []) {
    $active_category_id = isset($options['active_category_id'])
        ? absint($options['active_category_id'])
        : home_workflow_kb_request_category_id();
    $home_active = array_key_exists('home_active', $options)
        ? (bool) $options['home_active']
        : $active_view === 'home';
    $search_active = array_key_exists('search_active', $options)
        ? (bool) $options['search_active']
        : $active_view === 'search';
    $new_active = array_key_exists('new_active', $options)
        ? (bool) $options['new_active']
        : $active_view === 'new';
    $trash_active = array_key_exists('trash_active', $options)
        ? (bool) $options['trash_active']
        : $active_view === 'trash';
    $accounts_active = array_key_exists('accounts_active', $options)
        ? (bool) $options['accounts_active']
        : $active_view === 'accounts';
    $home_url = isset($options['home_url']) ? (string) $options['home_url'] : home_url('/');
    $home_search_url = isset($options['home_search_url']) ? (string) $options['home_search_url'] : home_url('/#kb-search-input');
    $new_url = isset($options['new_url']) ? (string) $options['new_url'] : home_workflow_kb_view_url('new', $active_category_id);
    $trash_url = isset($options['trash_url']) ? (string) $options['trash_url'] : home_workflow_kb_view_url('trash', $active_category_id);
    $sync_url = isset($options['sync_url']) ? (string) $options['sync_url'] : home_workflow_kb_view_url('sync', $active_category_id);
    $accounts_url = isset($options['accounts_url']) ? (string) $options['accounts_url'] : home_workflow_kb_view_url('accounts', $active_category_id);
    $category_manager_url = isset($options['category_manager_url'])
        ? (string) $options['category_manager_url']
        : home_workflow_kb_home_url_with_category($active_category_id, 'kb-category-manager');
    $category_url_callback = isset($options['category_url_callback']) && is_callable($options['category_url_callback'])
        ? $options['category_url_callback']
        : null;

    ob_start();
    ?>
    <?php echo home_workflow_kb_sidebar_critical_css(); ?>
    <aside class="kb-sidebar">
        <div class="kb-side-title">
            <span>Quiet Archive</span>
            <strong>个人知识库</strong>
        </div>
        <?php echo home_workflow_kb_style_switch(); ?>
        <nav class="kb-side-nav" aria-label="资料馆导航">
            <?php echo home_workflow_kb_nav_link($home_url, '目录', $home_active); ?>
            <?php echo home_workflow_kb_nav_link($home_search_url, '检索', $search_active); ?>
            <?php if ($can_edit) : ?>
                <?php echo home_workflow_kb_nav_link(admin_url('edit.php'), '草稿'); ?>
                <?php echo home_workflow_kb_nav_link($new_url, '新资料', $new_active, 'target="_blank" rel="noopener noreferrer"'); ?>
            <?php endif; ?>
            <?php if (current_user_can('delete_posts')) : ?>
                <?php echo home_workflow_kb_nav_link($trash_url, '回收站', $trash_active); ?>
            <?php endif; ?>
            <?php if (current_user_can('manage_categories')) : ?>
                <?php echo home_workflow_kb_nav_link($category_manager_url, '分类管理'); ?>
            <?php endif; ?>
            <?php if (home_workflow_kb_can_manage_accounts()) : ?>
                <?php echo home_workflow_kb_nav_link($sync_url, '同步设置', $active_view === 'sync'); ?>
                <?php echo home_workflow_kb_nav_link($accounts_url, '账号管理', $accounts_active); ?>
            <?php endif; ?>
        </nav>
        <div class="kb-side-block">
            <span>分类</span>
            <?php foreach ($categories as $category) : ?>
                <?php $category_url = $category_url_callback ? (string) call_user_func($category_url_callback, $category) : home_workflow_kb_home_url_with_category($category->term_id); ?>
                <a href="<?php echo esc_url($category_url); ?>" class="<?php echo $active_category_id === (int) $category->term_id ? 'is-active' : ''; ?>" <?php echo $active_category_id === (int) $category->term_id ? 'aria-current="page"' : ''; ?>>
                    <span><?php echo esc_html($category->name); ?></span>
                    <small><?php echo esc_html((string) ($category_counts[$category->term_id] ?? 0)); ?></small>
                </a>
            <?php endforeach; ?>
        </div>
        <div class="kb-logout-wrap"><a class="kb-logout" href="<?php echo esc_url(wp_logout_url(wp_login_url())); ?>">退出登录</a></div>
    </aside>
    <?php
    return trim(ob_get_clean());
}

function home_workflow_kb_shell($active_view, $main_html, $categories = null, $category_counts = null) {
    $can_edit = current_user_can('edit_posts');
    $categories = $categories === null ? home_workflow_kb_categories() : $categories;
    $visible_statuses = home_workflow_kb_visible_statuses();
    $category_counts = $category_counts === null ? home_workflow_kb_category_counts($categories, $visible_statuses) : $category_counts;
    return '<div class="kb-shell">'
        . home_workflow_kb_sidebar($active_view, $categories, $category_counts, $can_edit)
        . '<section class="kb-main">'
        . $main_html
        . '</section></div>';
}

function home_workflow_kb_compact_html($html) {
    $html = preg_replace('/>\s+</', '><', (string) $html);
    $html = preg_replace('/\s{2,}/', ' ', (string) $html);
    return trim((string) $html);
}

function home_workflow_kb_visible_statuses() {
    $statuses = ['publish'];

    if (current_user_can('edit_others_posts')) {
        $statuses[] = 'draft';
    }
    if (current_user_can('read_private_posts')) {
        $statuses[] = 'private';
    }

    return $statuses;
}

function home_workflow_kb_split_terms($value) {
    if (!is_scalar($value)) {
        return [];
    }

    $terms = [];
    foreach (preg_split('/[,，;；\n]+/u', (string) $value) as $term) {
        $term = trim($term);
        if ($term !== '' && !in_array($term, $terms, true)) {
            $terms[] = $term;
        }
    }

    return $terms;
}

function home_workflow_kb_can_manage_keywords() {
    if (home_workflow_site_kind() !== 'kb' || !is_user_logged_in()) {
        return false;
    }

    $user = wp_get_current_user();
    if (!$user instanceof WP_User) {
        return false;
    }

    return in_array($user->user_login, ['site-admin', 'publishi'], true);
}

function home_workflow_kb_autop_content($raw_content) {
    $raw_content = trim((string) $raw_content);
    if ($raw_content === '') {
        return '';
    }

    return wp_kses_post(wpautop($raw_content));
}

function home_workflow_kb_media_html($attachment_ids) {
    $pieces = [];
    foreach (home_workflow_kb_sanitize_id_list($attachment_ids) as $attachment_id) {
        $mime = (string) get_post_mime_type($attachment_id);
        if (str_starts_with($mime, 'image/')) {
            $image = wp_get_attachment_image($attachment_id, 'large', false, [
                'loading' => 'lazy',
                'decoding' => 'async',
            ]);
            if ($image) {
                $pieces[] = '<figure class="kb-form-media kb-form-image">' . $image . '</figure>';
            }
        } elseif (str_starts_with($mime, 'video/')) {
            $url = wp_get_attachment_url($attachment_id);
            if ($url) {
                $pieces[] = sprintf(
                    '<figure class="kb-form-media kb-form-video"><video controls playsinline preload="metadata"><source src="%s" type="%s"></video></figure>',
                    esc_url($url),
                    esc_attr($mime)
                );
            }
        }
    }

    return implode("\n\n", $pieces);
}

function home_workflow_kb_handle_uploaded_media($post_id) {
    if (empty($_FILES['home_kb_media']) || !current_user_can('upload_files')) {
        return [];
    }

    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/media.php';
    require_once ABSPATH . 'wp-admin/includes/image.php';

    $files = $_FILES['home_kb_media'];
    $names = is_array($files['name']) ? $files['name'] : [$files['name']];
    $attachment_ids = [];
    $fail = function ($message) use (&$attachment_ids) {
        foreach ($attachment_ids as $attachment_id) {
            wp_delete_attachment($attachment_id, true);
        }

        return new WP_Error('home_kb_media_upload_failed', $message);
    };

    foreach ($names as $index => $name) {
        $error = is_array($files['error']) ? (int) $files['error'][$index] : (int) $files['error'];
        if ($error === UPLOAD_ERR_NO_FILE) {
            continue;
        }
        if ($error !== UPLOAD_ERR_OK) {
            return $fail('文件上传失败，请缩小文件后重试。');
        }

        $single_file = [
            'name' => is_array($files['name']) ? $files['name'][$index] : $files['name'],
            'type' => is_array($files['type']) ? $files['type'][$index] : $files['type'],
            'tmp_name' => is_array($files['tmp_name']) ? $files['tmp_name'][$index] : $files['tmp_name'],
            'error' => $error,
            'size' => is_array($files['size']) ? $files['size'][$index] : $files['size'],
        ];

        $_FILES['home_kb_media_single'] = $single_file;
        $attachment_id = media_handle_upload('home_kb_media_single', $post_id);
        unset($_FILES['home_kb_media_single']);

        if (is_wp_error($attachment_id)) {
            return $fail($attachment_id->get_error_message());
        }

        $mime = (string) get_post_mime_type($attachment_id);
        if (!str_starts_with($mime, 'image/') && !str_starts_with($mime, 'video/')) {
            wp_delete_attachment($attachment_id, true);
            return $fail('只支持上传图片和视频。');
        }

        $attachment_ids[] = (int) $attachment_id;
    }

    return $attachment_ids;
}

function home_workflow_kb_attachment_ids_for_post($post_id) {
    $ids = [];
    $children = get_children([
        'post_parent' => $post_id,
        'post_type' => 'attachment',
        'post_status' => 'any',
        'fields' => 'ids',
    ]);
    $ids = array_merge($ids, array_map('intval', $children));

    $saved_ids = get_post_meta($post_id, 'home_kb_form_attachment_ids', true);
    if (is_array($saved_ids)) {
        $ids = array_merge($ids, array_map('intval', $saved_ids));
    }

    $thumbnail_id = (int) get_post_thumbnail_id($post_id);
    if ($thumbnail_id) {
        $ids[] = $thumbnail_id;
    }

    $post = get_post($post_id);
    $content = $post ? (string) $post->post_content : '';
    if (preg_match_all('#https?://[^"\'<>\s]+/wp-content/uploads/[^"\'<>\s]+#i', $content, $matches)) {
        foreach ($matches[0] as $url) {
            $attachment_id = attachment_url_to_postid(html_entity_decode($url));
            if ($attachment_id) {
                $ids[] = (int) $attachment_id;
            }
        }
    }
    if (preg_match_all('#/wp-content/uploads/[^"\'<>\s]+#i', $content, $matches)) {
        foreach ($matches[0] as $path) {
            $attachment_id = attachment_url_to_postid(home_url(html_entity_decode($path)));
            if ($attachment_id) {
                $ids[] = (int) $attachment_id;
            }
        }
    }

    return home_workflow_kb_sanitize_id_list($ids);
}

function home_workflow_kb_static_video_paths_for_post($post_id) {
    $post = get_post($post_id);
    if (!$post) {
        return [];
    }

    $content = (string) $post->post_content;
    if (!preg_match_all('#/wp-content/themes/kanso-minimal/kb-videos/([^"\'<>\s?]+)#i', $content, $matches)) {
        return [];
    }

    $video_dir = get_stylesheet_directory() . '/kb-videos';
    $video_dir_real = realpath($video_dir);
    if (!$video_dir_real) {
        return [];
    }

    $paths = [];
    foreach ($matches[1] as $filename) {
        $filename = basename(rawurldecode(html_entity_decode($filename)));
        if ($filename === '') {
            continue;
        }

        $path = $video_dir . '/' . $filename;
        $real = realpath($path);
        if ($real && str_starts_with($real, $video_dir_real . DIRECTORY_SEPARATOR)) {
            $paths[] = $real;
        }
    }

    return array_values(array_unique($paths));
}

function home_workflow_kb_delete_post_and_media($post_id) {
    foreach (home_workflow_kb_attachment_ids_for_post($post_id) as $attachment_id) {
        wp_delete_attachment($attachment_id, true);
    }

    foreach (home_workflow_kb_static_video_paths_for_post($post_id) as $path) {
        if (is_file($path)) {
            wp_delete_file($path);
        }
    }

    return wp_delete_post($post_id, true);
}

add_action('template_redirect', function () {
    if (home_workflow_site_kind() !== 'kb' || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        return;
    }

    if (!empty($_POST['home_kb_new_post_action'])) {
        if (!current_user_can('edit_posts') || !current_user_can('publish_posts') || !current_user_can('assign_categories')) {
            wp_die('你没有权限新增资料。', '权限不足', ['response' => 403]);
        }

        check_admin_referer('home_kb_new_post', 'home_kb_new_post_nonce');

        $title = isset($_POST['home_kb_new_title'])
            ? sanitize_text_field(wp_unslash($_POST['home_kb_new_title']))
            : '';
        if ($title === '') {
            wp_die('标题不能为空。', '新增资料失败', ['response' => 400]);
        }

        $category_id = isset($_POST['home_kb_new_category']) ? absint($_POST['home_kb_new_category']) : 0;
        $category = $category_id ? get_term($category_id, 'category') : null;
        if (!$category instanceof WP_Term || is_wp_error($category)) {
            wp_die('请选择有效分类。', '新增资料失败', ['response' => 400]);
        }

        $raw_content = isset($_POST['home_kb_new_content']) ? wp_unslash($_POST['home_kb_new_content']) : '';
        $content = home_workflow_kb_autop_content($raw_content);
        $source_url = isset($_POST['home_kb_new_source_url']) ? esc_url_raw(wp_unslash($_POST['home_kb_new_source_url'])) : '';
        $source_site = isset($_POST['home_kb_new_source_site']) ? sanitize_text_field(wp_unslash($_POST['home_kb_new_source_site'])) : '';
        $source_author = isset($_POST['home_kb_new_source_author']) ? sanitize_text_field(wp_unslash($_POST['home_kb_new_source_author'])) : '';
        if ($source_url && $source_site === '') {
            $host = wp_parse_url($source_url, PHP_URL_HOST);
            $source_site = $host ? preg_replace('/^www\./i', '', (string) $host) : '';
        }

        $post_id = wp_insert_post([
            'post_type' => 'post',
            'post_status' => 'publish',
            'post_title' => $title,
            'post_content' => $content,
            'post_category' => [$category_id],
        ], true);
        if (is_wp_error($post_id)) {
            wp_die(esc_html($post_id->get_error_message()), '新增资料失败', ['response' => 400]);
        }

        if ($source_url !== '') {
            update_post_meta($post_id, 'source_url', $source_url);
        }
        if ($source_site !== '') {
            update_post_meta($post_id, 'source_site', $source_site);
        }
        if ($source_author !== '') {
            update_post_meta($post_id, 'source_author', $source_author);
        }

        $tags = isset($_POST['home_kb_new_tags'])
            ? home_workflow_kb_split_terms(wp_unslash($_POST['home_kb_new_tags']))
            : [];
        if ($tags) {
            wp_set_post_tags($post_id, $tags, false);
        }

        $attachment_ids = home_workflow_kb_handle_uploaded_media($post_id);
        if (is_wp_error($attachment_ids)) {
            wp_delete_post($post_id, true);
            wp_die(esc_html($attachment_ids->get_error_message()), '上传失败', ['response' => 400]);
        }

        if ($attachment_ids) {
            update_post_meta($post_id, 'home_kb_form_attachment_ids', $attachment_ids);
            $media_html = home_workflow_kb_media_html($attachment_ids);
            if ($media_html !== '') {
                wp_update_post([
                    'ID' => $post_id,
                    'post_content' => trim($content . "\n\n" . $media_html),
                ]);
            }
        }

        wp_safe_redirect(get_permalink($post_id));
        exit;
    }

    if (!empty($_POST['home_kb_trash_action'])) {
        $post_id = isset($_POST['home_kb_post_id']) ? absint($_POST['home_kb_post_id']) : 0;
        $action = sanitize_key(wp_unslash($_POST['home_kb_trash_action']));
        if (!$post_id || get_post_type($post_id) !== 'post') {
            wp_die('文章不存在。', '文章不存在', ['response' => 404]);
        }
        if (get_post_status($post_id) !== 'trash') {
            wp_die('这篇文章不在回收站。', '回收站操作失败', ['response' => 400]);
        }

        if ($action === 'restore') {
            if (!current_user_can('edit_post', $post_id)) {
                wp_die('你没有权限恢复这篇文章。', '权限不足', ['response' => 403]);
            }

            check_admin_referer('home_kb_trash_restore_' . $post_id, 'home_kb_trash_nonce');
            wp_untrash_post($post_id);
        } elseif ($action === 'delete') {
            if (!current_user_can('delete_post', $post_id)) {
                wp_die('你没有权限永久删除这篇文章。', '权限不足', ['response' => 403]);
            }

            check_admin_referer('home_kb_trash_delete_' . $post_id, 'home_kb_trash_nonce');
            home_workflow_kb_delete_post_and_media($post_id);
        }

        wp_safe_redirect(wp_get_referer() ?: home_url('/?kb_view=trash'));
        exit;
    }

    if (!empty($_POST['home_kb_post_action'])) {
        $post_id = isset($_POST['home_kb_post_id']) ? absint($_POST['home_kb_post_id']) : 0;
        $action = sanitize_key(wp_unslash($_POST['home_kb_post_action']));

        if (!$post_id || get_post_type($post_id) !== 'post') {
            wp_die('文章不存在。', '文章不存在', ['response' => 404]);
        }

        if ($action === 'trash') {
            if (!current_user_can('delete_post', $post_id)) {
                wp_die('你没有权限删除这篇文章。', '权限不足', ['response' => 403]);
            }

            check_admin_referer('home_kb_post_trash_' . $post_id, 'home_kb_post_nonce');
            wp_trash_post($post_id);
        } elseif ($action === 'category') {
            if (!current_user_can('edit_post', $post_id) || !current_user_can('assign_categories')) {
                wp_die('你没有权限修改这篇文章的分类。', '权限不足', ['response' => 403]);
            }

            check_admin_referer('home_kb_post_category_' . $post_id, 'home_kb_post_nonce');
            $category_id = isset($_POST['home_kb_post_category']) ? absint($_POST['home_kb_post_category']) : 0;
            $category = $category_id ? get_term($category_id, 'category') : null;
            if (!$category instanceof WP_Term || is_wp_error($category)) {
                wp_die('分类不存在。', '分类不存在', ['response' => 404]);
            }

            wp_set_post_categories($post_id, [$category_id], false);
        }

        wp_safe_redirect(wp_get_referer() ?: home_url('/'));
        exit;
    }

    if (!empty($_POST['home_kb_category_action'])) {
        if (!current_user_can('manage_categories')) {
            wp_die('你没有权限管理分类。', '权限不足', ['response' => 403]);
        }

        $action = sanitize_key(wp_unslash($_POST['home_kb_category_action']));
        if ($action === 'add') {
            check_admin_referer('home_kb_category_add', 'home_kb_category_nonce');
            $category_name = isset($_POST['home_kb_category_name'])
                ? sanitize_text_field(wp_unslash($_POST['home_kb_category_name']))
                : '';

            if ($category_name !== '') {
                $result = wp_insert_term($category_name, 'category');
                if (is_wp_error($result) && $result->get_error_code() !== 'term_exists') {
                    wp_die(esc_html($result->get_error_message()), '分类新增失败', ['response' => 400]);
                }
            }
        } elseif ($action === 'delete') {
            $category_id = isset($_POST['home_kb_category_id']) ? absint($_POST['home_kb_category_id']) : 0;
            check_admin_referer('home_kb_category_delete_' . $category_id, 'home_kb_category_nonce');

            $default_category = (int) get_option('default_category');
            $fallback_category = home_kb_uncategorized_category_id(true);
            $category = $category_id ? get_term($category_id, 'category') : null;
            if (!$category instanceof WP_Term || is_wp_error($category) || $category_id === $default_category || $category_id === $fallback_category || $category->slug === 'uncategorized') {
                wp_die('这个分类不能删除。', '分类删除失败', ['response' => 400]);
            }

            if (!$fallback_category) {
                wp_die('未分类兜底分类不可用。', '分类删除失败', ['response' => 500]);
            }

            $post_ids = get_posts([
                'post_type' => 'post',
                'post_status' => 'any',
                'fields' => 'ids',
                'posts_per_page' => -1,
                'tax_query' => [
                    [
                        'taxonomy' => 'category',
                        'field' => 'term_id',
                        'terms' => [$category_id],
                    ],
                ],
            ]);

            foreach ($post_ids as $affected_post_id) {
                wp_set_post_categories((int) $affected_post_id, [$fallback_category], false);
            }

            $result = wp_delete_term($category_id, 'category');
            if (is_wp_error($result)) {
                wp_die(esc_html($result->get_error_message()), '分类删除失败', ['response' => 400]);
            }
        }

        wp_safe_redirect(wp_get_referer() ?: home_url('/'));
        exit;
    }

    if (!empty($_POST['home_kb_tag_action'])) {
        if (!home_workflow_kb_can_manage_keywords()) {
            wp_die('你没有权限管理关键字。', '权限不足', ['response' => 403]);
        }

        $action = sanitize_key(wp_unslash($_POST['home_kb_tag_action']));
        if ($action === 'add') {
            check_admin_referer('home_kb_tag_add', 'home_kb_tag_nonce');
            $tag_names = isset($_POST['home_kb_tag_name'])
                ? home_workflow_kb_split_terms(wp_unslash($_POST['home_kb_tag_name']))
                : [];
            $added_tag_id = 0;

            foreach ($tag_names as $tag_name) {
                $result = wp_insert_term($tag_name, 'post_tag');
                if (is_wp_error($result)) {
                    if ($result->get_error_code() === 'term_exists') {
                        $existing_tag_id = (int) $result->get_error_data('term_exists');
                        $added_tag_id = $added_tag_id ?: $existing_tag_id;
                        continue;
                    }

                    wp_die(esc_html($result->get_error_message()), '关键字新增失败', ['response' => 400]);
                }

                if (!$added_tag_id && isset($result['term_id'])) {
                    $added_tag_id = (int) $result['term_id'];
                }
            }

            $redirect = remove_query_arg('kb_page', wp_get_referer() ?: home_url('/'));
            if ($added_tag_id) {
                $redirect = add_query_arg('kb_tag', (string) $added_tag_id, $redirect);
            }
            wp_safe_redirect($redirect);
            exit;
        }

        if ($action === 'delete') {
            $tag_id = isset($_POST['home_kb_tag_id']) ? absint($_POST['home_kb_tag_id']) : 0;
            check_admin_referer('home_kb_tag_delete_' . $tag_id, 'home_kb_tag_nonce');

            $tag = $tag_id ? get_term($tag_id, 'post_tag') : null;
            if (!$tag instanceof WP_Term || is_wp_error($tag)) {
                wp_die('关键字不存在。', '关键字删除失败', ['response' => 404]);
            }

            $result = wp_delete_term($tag_id, 'post_tag');
            if (is_wp_error($result)) {
                wp_die(esc_html($result->get_error_message()), '关键字删除失败', ['response' => 400]);
            }

            wp_safe_redirect(remove_query_arg(['kb_tag', 'kb_page'], wp_get_referer() ?: home_url('/')));
            exit;
        }
    }

    if (!empty($_POST['home_kb_sync_action'])) {
        if (!home_workflow_kb_can_manage_accounts()) {
            wp_die('你没有权限管理同步设置。', '权限不足', ['response' => 403]);
        }

        check_admin_referer('home_kb_sync_settings', 'home_kb_sync_nonce');

        $settings = home_workflow_kb_sanitize_sync_settings([
            'mode' => isset($_POST['home_kb_sync_mode']) ? wp_unslash($_POST['home_kb_sync_mode']) : '',
            'interval_minutes' => isset($_POST['home_kb_sync_interval_minutes']) ? wp_unslash($_POST['home_kb_sync_interval_minutes']) : 0,
            'realtime_seconds' => isset($_POST['home_kb_sync_realtime_seconds']) ? wp_unslash($_POST['home_kb_sync_realtime_seconds']) : 0,
            'updated_at' => current_time('mysql'),
        ]);

        update_option('home_kb_obsidian_sync_settings', $settings, false);
        wp_safe_redirect(add_query_arg('kb_sync_notice', 'saved', home_workflow_kb_view_url('sync')));
        exit;
    }

    if (!empty($_POST['home_kb_account_action'])) {
        if (!home_workflow_kb_can_manage_accounts()) {
            wp_die('你没有权限管理账号。', '权限不足', ['response' => 403]);
        }

        $action = sanitize_key(wp_unslash($_POST['home_kb_account_action']));
        $role_options = home_workflow_kb_account_role_options();
        $accounts_url = home_workflow_kb_view_url('accounts');

        if ($action === 'create') {
            check_admin_referer('home_kb_account_create', 'home_kb_account_nonce');

            $login = isset($_POST['home_kb_account_login'])
                ? sanitize_user(wp_unslash($_POST['home_kb_account_login']), true)
                : '';
            $email = isset($_POST['home_kb_account_email'])
                ? sanitize_email(wp_unslash($_POST['home_kb_account_email']))
                : '';
            $display_name = isset($_POST['home_kb_account_display_name'])
                ? sanitize_text_field(wp_unslash($_POST['home_kb_account_display_name']))
                : '';
            $password = isset($_POST['home_kb_account_password'])
                ? (string) wp_unslash($_POST['home_kb_account_password'])
                : '';
            $role = isset($_POST['home_kb_account_role'])
                ? sanitize_key(wp_unslash($_POST['home_kb_account_role']))
                : '';

            if ($login === '' || !validate_username($login)) {
                wp_die('账号名只能使用字母、数字、下划线、连字符或邮箱格式。', '账号新增失败', ['response' => 400]);
            }
            if (username_exists($login)) {
                wp_die('这个账号名已经存在。', '账号新增失败', ['response' => 400]);
            }
            if (!is_email($email)) {
                wp_die('请填写有效邮箱。', '账号新增失败', ['response' => 400]);
            }
            if (email_exists($email)) {
                wp_die('这个邮箱已经被其他账号使用。', '账号新增失败', ['response' => 400]);
            }
            if (strlen($password) < 10) {
                wp_die('密码至少需要 10 个字符。', '账号新增失败', ['response' => 400]);
            }
            if (!isset($role_options[$role])) {
                wp_die('请选择有效账号类型。', '账号新增失败', ['response' => 400]);
            }

            $user_id = wp_insert_user([
                'user_login' => $login,
                'user_email' => $email,
                'display_name' => $display_name !== '' ? $display_name : $login,
                'user_pass' => $password,
                'role' => $role,
            ]);
            if (is_wp_error($user_id)) {
                wp_die(esc_html($user_id->get_error_message()), '账号新增失败', ['response' => 400]);
            }

            wp_safe_redirect(add_query_arg('kb_account_notice', 'created', $accounts_url));
            exit;
        }

        if ($action === 'role') {
            $user_id = isset($_POST['home_kb_account_user_id']) ? absint($_POST['home_kb_account_user_id']) : 0;
            check_admin_referer('home_kb_account_role_' . $user_id, 'home_kb_account_nonce');

            $target_user = $user_id ? get_user_by('id', $user_id) : false;
            $role = isset($_POST['home_kb_account_role'])
                ? sanitize_key(wp_unslash($_POST['home_kb_account_role']))
                : '';
            if (!$target_user instanceof WP_User) {
                wp_die('账号不存在。', '账号更新失败', ['response' => 404]);
            }
            if (home_workflow_kb_account_is_protected($target_user)) {
                wp_die('受保护账号不能在这里修改权限。', '账号更新失败', ['response' => 403]);
            }
            if (!isset($role_options[$role])) {
                wp_die('请选择有效账号类型。', '账号更新失败', ['response' => 400]);
            }

            $target_user->set_role($role);
            wp_safe_redirect(add_query_arg('kb_account_notice', 'updated', $accounts_url));
            exit;
        }

        if ($action === 'password') {
            $user_id = isset($_POST['home_kb_account_user_id']) ? absint($_POST['home_kb_account_user_id']) : 0;
            check_admin_referer('home_kb_account_password_' . $user_id, 'home_kb_account_nonce');

            $target_user = $user_id ? get_user_by('id', $user_id) : false;
            $password = isset($_POST['home_kb_account_password'])
                ? (string) wp_unslash($_POST['home_kb_account_password'])
                : '';
            if (!$target_user instanceof WP_User) {
                wp_die('账号不存在。', '密码更新失败', ['response' => 404]);
            }
            if (strlen($password) < 10) {
                wp_die('新密码至少需要 10 个字符。', '密码更新失败', ['response' => 400]);
            }

            $result = wp_update_user([
                'ID' => (int) $target_user->ID,
                'user_pass' => $password,
            ]);
            if (is_wp_error($result)) {
                wp_die(esc_html($result->get_error_message()), '密码更新失败', ['response' => 400]);
            }

            wp_safe_redirect(add_query_arg('kb_account_notice', 'password', $accounts_url));
            exit;
        }

        if ($action === 'delete') {
            $user_id = isset($_POST['home_kb_account_user_id']) ? absint($_POST['home_kb_account_user_id']) : 0;
            check_admin_referer('home_kb_account_delete_' . $user_id, 'home_kb_account_nonce');

            $target_user = $user_id ? get_user_by('id', $user_id) : false;
            if (!$target_user instanceof WP_User) {
                wp_die('账号不存在。', '账号删除失败', ['response' => 404]);
            }
            if ((int) $target_user->ID === get_current_user_id()) {
                wp_die('不能删除当前登录账号。', '账号删除失败', ['response' => 403]);
            }
            if (home_workflow_kb_account_is_protected($target_user)) {
                wp_die('受保护账号不能删除。', '账号删除失败', ['response' => 403]);
            }

            require_once ABSPATH . 'wp-admin/includes/user.php';
            wp_delete_user((int) $target_user->ID, get_current_user_id());
            wp_safe_redirect(add_query_arg('kb_account_notice', 'deleted', $accounts_url));
            exit;
        }
    }

    if (empty($_POST['home_kb_sticky_action'])) {
        return;
    }

    $post_id = isset($_POST['home_kb_post_id']) ? absint($_POST['home_kb_post_id']) : 0;
    if (!$post_id || !current_user_can('edit_post', $post_id)) {
        wp_die('你没有权限置顶这篇文章。', '权限不足', ['response' => 403]);
    }

    check_admin_referer('home_kb_sticky_' . $post_id, 'home_kb_sticky_nonce');

    $action = sanitize_key(wp_unslash($_POST['home_kb_sticky_action']));
    if ($action === 'stick') {
        stick_post($post_id);
    } elseif ($action === 'unstick') {
        unstick_post($post_id);
    }

    wp_safe_redirect(wp_get_referer() ?: home_url('/'));
    exit;
});

function home_workflow_render_kb_new_view() {
    if (!current_user_can('edit_posts')) {
        return home_workflow_kb_shell('new', '<article class="kb-card kb-empty"><h2>权限不足</h2><p>你没有权限新增资料。</p></article>');
    }

    $categories = home_workflow_kb_categories();
    $category_counts = home_workflow_kb_category_counts($categories, home_workflow_kb_visible_statuses());
    $active_category_id = home_workflow_kb_request_category_id();
    $return_url = home_workflow_kb_home_url_with_category($active_category_id);
    $form_action = home_workflow_kb_view_url('new', $active_category_id);

    ob_start();
    ?>
    <header class="kb-page-head">
        <div>
            <div class="kb-eyebrow">New Archive Item</div>
            <h1>新资料</h1>
            <p>把本地整理好的文字、图片和小中型视频直接发布到个人知识库。</p>
        </div>
        <a href="<?php echo esc_url($return_url); ?>">返回目录</a>
    </header>

    <section class="kb-editor-panel">
        <form class="kb-new-post-form" method="post" action="<?php echo esc_url($form_action); ?>" enctype="multipart/form-data">
            <input type="hidden" name="home_kb_new_post_action" value="create">
            <?php wp_nonce_field('home_kb_new_post', 'home_kb_new_post_nonce'); ?>

            <label class="kb-field kb-field-full">
                <span>标题</span>
                <input type="text" name="home_kb_new_title" maxlength="180" required>
            </label>

            <label class="kb-field kb-field-full">
                <span>正文</span>
                <textarea name="home_kb_new_content" rows="14" placeholder="可以直接输入文字，也可以粘贴少量安全 HTML。普通换行会自动整理成段落。"></textarea>
            </label>

            <div class="kb-field-grid">
                <label class="kb-field">
                    <span>分类</span>
                    <select name="home_kb_new_category" required>
                        <?php foreach ($categories as $category) : ?>
                            <option value="<?php echo esc_attr((string) $category->term_id); ?>" <?php selected($active_category_id, (int) $category->term_id); ?>><?php echo esc_html($category->name); ?></option>
                        <?php endforeach; ?>
                    </select>
                </label>

                <label class="kb-field">
                    <span>标签</span>
                    <input type="text" name="home_kb_new_tags" placeholder="用逗号分隔，例如：AI, 视频">
                </label>
            </div>

            <div class="kb-field-grid">
                <label class="kb-field">
                    <span>来源链接</span>
                    <input type="url" name="home_kb_new_source_url" placeholder="https://example.com/article">
                </label>

                <label class="kb-field">
                    <span>来源站点</span>
                    <input type="text" name="home_kb_new_source_site" placeholder="留空时会从来源链接自动推断">
                </label>
            </div>

            <div class="kb-field-grid">
                <label class="kb-field">
                    <span>作者</span>
                    <input type="text" name="home_kb_new_source_author">
                </label>

                <label class="kb-field">
                    <span>本地图片 / 视频</span>
                    <input type="file" name="home_kb_media[]" accept="image/*,video/*" multiple>
                </label>
            </div>

            <div class="kb-form-note">
                <strong>默认直接发布。</strong>
                <span>大视频建议继续用现有 SSH 视频快捷指令，或等下一步内网直传方案。</span>
            </div>

            <div class="kb-form-actions">
                <button type="submit">发布到知识库</button>
                <a href="<?php echo esc_url($return_url); ?>">取消</a>
            </div>
        </form>
    </section>
    <?php

    return home_workflow_kb_shell('new', home_workflow_kb_compact_html(ob_get_clean()), $categories, $category_counts);
}

function home_workflow_render_kb_sync_view() {
    if (!home_workflow_kb_can_manage_accounts()) {
        return home_workflow_kb_shell('sync', '<article class="kb-card kb-empty"><h2>权限不足</h2><p>你没有权限管理同步设置。</p></article>');
    }

    $categories = home_workflow_kb_categories();
    $category_counts = home_workflow_kb_category_counts($categories, home_workflow_kb_visible_statuses());
    $active_category_id = home_workflow_kb_request_category_id();
    $return_url = home_workflow_kb_home_url_with_category($active_category_id);
    $sync_url = home_workflow_kb_view_url('sync', $active_category_id);
    $settings = home_workflow_kb_sync_settings();
    $notice = isset($_GET['kb_sync_notice']) ? sanitize_key(wp_unslash($_GET['kb_sync_notice'])) : '';
    $mode_label = $settings['mode'] === 'realtime' ? '实时同步' : '定时同步';
    $poll_seconds = home_workflow_kb_sync_poll_seconds($settings);

    ob_start();
    ?>
    <header class="kb-page-head">
        <div>
            <div class="kb-eyebrow">Obsidian Sync</div>
            <h1>同步设置</h1>
            <p>WordPress 仍是权威源；Mac 本机同步脚本读取这里的模式后，把资料镜像到 Obsidian。</p>
        </div>
        <a href="<?php echo esc_url($return_url); ?>">返回目录</a>
    </header>

    <?php if ($notice === 'saved') : ?>
        <div class="kb-account-notice">Obsidian 同步设置已保存。</div>
        <?php echo home_workflow_kb_action_notice_window('Obsidian 同步设置已保存，本机同步脚本下一轮会读取这个模式。', '同步设置已保存'); ?>
    <?php endif; ?>

    <section class="kb-sync-panel">
        <form class="kb-sync-form" method="post" action="<?php echo esc_url($sync_url); ?>">
            <input type="hidden" name="home_kb_sync_action" value="update">
            <?php wp_nonce_field('home_kb_sync_settings', 'home_kb_sync_nonce'); ?>

            <div class="kb-sync-mode-grid" role="radiogroup" aria-label="Obsidian 同步模式">
                <label class="kb-sync-mode-card <?php echo $settings['mode'] === 'schedule' ? 'is-active' : ''; ?>">
                    <input type="radio" name="home_kb_sync_mode" value="schedule" <?php checked($settings['mode'], 'schedule'); ?>>
                    <span>定时同步</span>
                    <strong>按固定间隔拉取</strong>
                    <small>适合日常后台镜像，资源占用更低。</small>
                </label>
                <label class="kb-sync-mode-card <?php echo $settings['mode'] === 'realtime' ? 'is-active' : ''; ?>">
                    <input type="radio" name="home_kb_sync_mode" value="realtime" <?php checked($settings['mode'], 'realtime'); ?>>
                    <span>实时同步</span>
                    <strong>短间隔自动拉取</strong>
                    <small>近实时更新 Obsidian，不改 WordPress 发布流程。</small>
                </label>
            </div>

            <div class="kb-field-grid">
                <label class="kb-field">
                    <span>定时间隔（分钟）</span>
                    <input type="number" name="home_kb_sync_interval_minutes" min="5" max="1440" step="5" value="<?php echo esc_attr((string) $settings['interval_minutes']); ?>" required>
                </label>
                <label class="kb-field">
                    <span>实时轮询（秒）</span>
                    <input type="number" name="home_kb_sync_realtime_seconds" min="15" max="300" step="5" value="<?php echo esc_attr((string) $settings['realtime_seconds']); ?>" required>
                </label>
            </div>

            <div class="kb-sync-summary">
                <span>当前模式：<?php echo esc_html($mode_label); ?></span>
                <span>脚本等待：<?php echo esc_html((string) $poll_seconds); ?> 秒</span>
                <?php if ($settings['updated_at'] !== '') : ?>
                    <span>最近保存：<?php echo esc_html($settings['updated_at']); ?></span>
                <?php endif; ?>
            </div>

            <div class="kb-sync-command">
                <span>本机守护命令</span>
                <code>python3 scripts/kb-obsidian-sync.py --env-file .env.obsidian --watch</code>
            </div>

            <div class="kb-form-actions">
                <button type="submit">保存同步设置</button>
            </div>
        </form>
    </section>
    <?php

    return home_workflow_kb_shell('sync', home_workflow_kb_compact_html(ob_get_clean()), $categories, $category_counts);
}

function home_workflow_render_kb_accounts_view() {
    if (!home_workflow_kb_can_manage_accounts()) {
        return home_workflow_kb_shell('accounts', '<article class="kb-card kb-empty"><h2>权限不足</h2><p>你没有权限管理账号。</p></article>');
    }

    $categories = home_workflow_kb_categories();
    $category_counts = home_workflow_kb_category_counts($categories, home_workflow_kb_visible_statuses());
    $active_category_id = home_workflow_kb_request_category_id();
    $return_url = home_workflow_kb_home_url_with_category($active_category_id);
    $accounts_url = home_workflow_kb_view_url('accounts', $active_category_id);
    $role_options = home_workflow_kb_account_role_options();
    $users = get_users([
        'orderby' => 'registered',
        'order' => 'DESC',
        'fields' => 'all',
    ]);
    $notice = isset($_GET['kb_account_notice']) ? sanitize_key(wp_unslash($_GET['kb_account_notice'])) : '';
    $notice_map = [
        'created' => '账号已新增。',
        'updated' => '账号权限已更新。',
        'password' => '网页登录密码已更新；Application Password（例如 .env.obsidian 里的 WP_KB_APP_PASSWORD）不会被更改。',
        'deleted' => '账号已删除，原有内容已归还给当前管理员。',
    ];

    ob_start();
    ?>
    <header class="kb-page-head">
        <div>
            <div class="kb-eyebrow">Account Console</div>
            <h1>账号管理</h1>
            <p>为个人知识库添加阅读、整理和发布账号；系统账号和管理员账号会被保护，避免误删导致发布流程中断。</p>
        </div>
        <a href="<?php echo esc_url($return_url); ?>">返回目录</a>
    </header>

    <?php if (isset($notice_map[$notice])) : ?>
        <div class="kb-account-notice"><?php echo esc_html($notice_map[$notice]); ?></div>
        <?php echo home_workflow_kb_action_notice_window($notice_map[$notice], '账号操作完成'); ?>
    <?php endif; ?>

    <section class="kb-account-role-grid" aria-label="账号类型">
        <?php foreach ($role_options as $role => $option) : ?>
            <article class="kb-account-role-card">
                <span><?php echo esc_html($role); ?></span>
                <h2><?php echo esc_html($option['label']); ?></h2>
                <p><?php echo esc_html($option['description']); ?></p>
            </article>
        <?php endforeach; ?>
    </section>

    <div class="kb-account-console">
        <section class="kb-account-create-panel">
            <div class="kb-account-panel-title">
                <span>新增账号</span>
                <p>创建后可立即登录知识库。密码至少 10 个字符。</p>
            </div>
            <form class="kb-account-form" method="post" action="<?php echo esc_url($accounts_url); ?>">
                <input type="hidden" name="home_kb_account_action" value="create">
                <?php wp_nonce_field('home_kb_account_create', 'home_kb_account_nonce'); ?>

                <label class="kb-field">
                    <span>账号名</span>
                    <input type="text" name="home_kb_account_login" autocomplete="off" required>
                </label>
                <label class="kb-field">
                    <span>邮箱</span>
                    <input type="email" name="home_kb_account_email" autocomplete="off" required>
                </label>
                <label class="kb-field">
                    <span>显示名</span>
                    <input type="text" name="home_kb_account_display_name" autocomplete="off">
                </label>
                <label class="kb-field">
                    <span>账号类型</span>
                    <select name="home_kb_account_role" required>
                        <?php foreach ($role_options as $role => $option) : ?>
                            <option value="<?php echo esc_attr($role); ?>"><?php echo esc_html($option['label']); ?></option>
                        <?php endforeach; ?>
                    </select>
                </label>
                <label class="kb-field">
                    <span>初始密码</span>
                    <span class="kb-password-control">
                        <input id="home-kb-account-create-password" type="password" name="home_kb_account_password" minlength="10" autocomplete="new-password" required>
                        <button class="kb-password-toggle" type="button" aria-controls="home-kb-account-create-password" aria-label="显示密码">显示</button>
                    </span>
                </label>

                <div class="kb-form-actions">
                    <button type="submit">新增账号</button>
                </div>
            </form>
        </section>

        <section class="kb-account-list" aria-label="账号列表">
            <div class="kb-account-panel-title">
                <span>账号列表</span>
                <p>受保护账号只允许改网页登录密码，不允许删除或降权。Application Password 需要在 WordPress 后台或服务器 .env 中单独维护。</p>
            </div>
            <?php foreach ($users as $user) : ?>
                <?php
                if (!$user instanceof WP_User) {
                    continue;
                }
                $primary_role = home_workflow_kb_account_primary_role($user);
                $is_protected = home_workflow_kb_account_is_protected($user);
                $is_current = (int) $user->ID === get_current_user_id();
                $registered = $user->user_registered ? mysql2date('Y.m.d', $user->user_registered) : '';
                ?>
                <article class="kb-account-row <?php echo $is_protected ? 'is-protected' : ''; ?>">
                    <div class="kb-account-main">
                        <span><?php echo esc_html(home_workflow_kb_account_role_label($primary_role)); ?></span>
                        <h2><?php echo esc_html($user->display_name ?: $user->user_login); ?></h2>
                        <p>
                            <strong><?php echo esc_html($user->user_login); ?></strong>
                            <?php if ($user->user_email) : ?>
                                <small><?php echo esc_html($user->user_email); ?></small>
                            <?php endif; ?>
                            <?php if ($registered) : ?>
                                <small><?php echo esc_html($registered); ?></small>
                            <?php endif; ?>
                            <?php if ($is_current || $is_protected) : ?>
                                <small><?php echo esc_html($is_current ? '当前登录' : '受保护'); ?></small>
                            <?php endif; ?>
                        </p>
                    </div>
                    <div class="kb-account-actions">
                        <?php if (!$is_protected && !$is_current) : ?>
                            <form method="post" action="<?php echo esc_url($accounts_url); ?>">
                                <input type="hidden" name="home_kb_account_action" value="role">
                                <input type="hidden" name="home_kb_account_user_id" value="<?php echo esc_attr((string) $user->ID); ?>">
                                <?php wp_nonce_field('home_kb_account_role_' . $user->ID, 'home_kb_account_nonce'); ?>
                                <label>
                                    <span class="screen-reader-text">修改账号类型</span>
                                    <select name="home_kb_account_role">
                                        <?php foreach ($role_options as $role => $option) : ?>
                                            <option value="<?php echo esc_attr($role); ?>" <?php selected($primary_role, $role); ?>><?php echo esc_html($option['label']); ?></option>
                                        <?php endforeach; ?>
                                    </select>
                                </label>
                                <button type="submit">更新权限</button>
                            </form>
                            <form method="post" action="<?php echo esc_url($accounts_url); ?>" onsubmit="return confirm('确定删除这个账号吗？账号名会消失，文章会归还给当前管理员。');">
                                <input type="hidden" name="home_kb_account_action" value="delete">
                                <input type="hidden" name="home_kb_account_user_id" value="<?php echo esc_attr((string) $user->ID); ?>">
                                <?php wp_nonce_field('home_kb_account_delete_' . $user->ID, 'home_kb_account_nonce'); ?>
                                <button class="is-danger" type="submit">删除</button>
                            </form>
                        <?php endif; ?>
                        <form class="kb-account-password-form" method="post" action="<?php echo esc_url($accounts_url); ?>">
                            <input type="hidden" name="home_kb_account_action" value="password">
                            <input type="hidden" name="home_kb_account_user_id" value="<?php echo esc_attr((string) $user->ID); ?>">
                            <?php wp_nonce_field('home_kb_account_password_' . $user->ID, 'home_kb_account_nonce'); ?>
                            <label>
                                <span class="screen-reader-text">网页登录新密码</span>
                                <span class="kb-password-control">
                                    <input id="home-kb-account-password-<?php echo esc_attr((string) $user->ID); ?>" type="password" name="home_kb_account_password" minlength="10" autocomplete="new-password" placeholder="网页登录新密码" required>
                                    <button class="kb-password-toggle" type="button" aria-controls="home-kb-account-password-<?php echo esc_attr((string) $user->ID); ?>" aria-label="显示密码">显示</button>
                                </span>
                            </label>
                            <button type="submit">改登录密码</button>
                        </form>
                    </div>
                </article>
            <?php endforeach; ?>
        </section>
    </div>
    <script>
        (function () {
            document.addEventListener('click', function (event) {
                var button = event.target.closest('.kb-password-toggle');
                if (!button) {
                    return;
                }
                var input = document.getElementById(button.getAttribute('aria-controls'));
                if (!input) {
                    return;
                }
                var visible = input.type === 'password';
                input.type = visible ? 'text' : 'password';
                button.textContent = visible ? '隐藏' : '显示';
                button.setAttribute('aria-label', visible ? '隐藏密码' : '显示密码');
            });
        })();
    </script>
    <?php

    return home_workflow_kb_shell('accounts', home_workflow_kb_compact_html(ob_get_clean()), $categories, $category_counts);
}

function home_workflow_render_kb_trash_view() {
    if (!current_user_can('delete_posts')) {
        return home_workflow_kb_shell('trash', '<article class="kb-card kb-empty"><h2>权限不足</h2><p>你没有权限查看回收站。</p></article>');
    }

    $categories = home_workflow_kb_categories();
    $category_counts = home_workflow_kb_category_counts($categories, home_workflow_kb_visible_statuses());
    $active_category_id = home_workflow_kb_request_category_id();
    $return_url = home_workflow_kb_home_url_with_category($active_category_id);
    $trash_action_url = home_workflow_kb_view_url('trash', $active_category_id);
    $trash_page_url = function ($page) use ($active_category_id) {
        return home_workflow_kb_view_url('trash', $active_category_id, ['kb_trash_page' => $page]);
    };
    $posts_per_page = 8;
    $requested_page = isset($_GET['kb_trash_page']) ? max(1, absint($_GET['kb_trash_page'])) : 1;
    $trash_query = new WP_Query([
        'post_type' => 'post',
        'post_status' => 'trash',
        'posts_per_page' => $posts_per_page,
        'paged' => $requested_page,
        'orderby' => 'modified',
        'order' => 'DESC',
    ] + (current_user_can('delete_others_posts') ? [] : ['author' => get_current_user_id()]));
    $max_pages = max(1, (int) $trash_query->max_num_pages);
    $current_page = min($requested_page, $max_pages);

    ob_start();
    ?>
    <header class="kb-page-head">
        <div>
            <div class="kb-eyebrow">Trash</div>
            <h1>回收站</h1>
            <p>移入回收站的资料可以恢复；永久删除会同时清理这篇文章关联的附件。</p>
        </div>
        <a href="<?php echo esc_url($return_url); ?>">返回目录</a>
    </header>

    <section class="kb-trash-list" aria-label="回收站文章">
        <?php if ($trash_query->have_posts()) : ?>
            <?php while ($trash_query->have_posts()) : $trash_query->the_post(); ?>
                <?php
                $post_id = get_the_ID();
                $attachment_count = count(home_workflow_kb_attachment_ids_for_post($post_id)) + count(home_workflow_kb_static_video_paths_for_post($post_id));
                ?>
                <article class="kb-trash-card">
                    <div>
                        <time datetime="<?php echo esc_attr(get_the_modified_date('c')); ?>"><?php echo esc_html(get_the_modified_date('Y.m.d H:i')); ?></time>
                        <h2><?php echo esc_html(get_the_title()); ?></h2>
                        <p><?php echo esc_html(wp_trim_words(wp_strip_all_tags(get_the_excerpt(), true), 42)); ?></p>
                        <small><?php echo esc_html((string) $attachment_count); ?> 个关联附件/静态视频</small>
                    </div>
                    <div class="kb-trash-actions">
                        <form method="post" action="<?php echo esc_url($trash_action_url); ?>">
                            <input type="hidden" name="home_kb_post_id" value="<?php echo esc_attr((string) $post_id); ?>">
                            <input type="hidden" name="home_kb_trash_action" value="restore">
                            <?php wp_nonce_field('home_kb_trash_restore_' . $post_id, 'home_kb_trash_nonce'); ?>
                            <button type="submit">恢复</button>
                        </form>
                        <form method="post" action="<?php echo esc_url($trash_action_url); ?>" onsubmit="return confirm('确定永久删除这篇文章和关联附件吗？这个操作不能撤销。');">
                            <input type="hidden" name="home_kb_post_id" value="<?php echo esc_attr((string) $post_id); ?>">
                            <input type="hidden" name="home_kb_trash_action" value="delete">
                            <?php wp_nonce_field('home_kb_trash_delete_' . $post_id, 'home_kb_trash_nonce'); ?>
                            <button class="is-danger" type="submit">永久删除</button>
                        </form>
                    </div>
                </article>
            <?php endwhile; ?>
            <?php wp_reset_postdata(); ?>
        <?php else : ?>
            <article class="kb-card kb-empty">
                <h2>回收站是空的</h2>
                <p>首页删除的文章会先显示在这里。</p>
            </article>
        <?php endif; ?>

        <?php if ($max_pages > 1) : ?>
            <nav class="kb-pagination" aria-label="回收站分页">
                <?php if ($current_page > 1) : ?>
                    <a href="<?php echo esc_url($trash_page_url($current_page - 1)); ?>">上一页</a>
                <?php else : ?>
                    <span class="is-disabled">上一页</span>
                <?php endif; ?>

                <?php foreach (home_workflow_kb_pagination_pages($current_page, $max_pages) as $page_item) : ?>
                    <?php if ($page_item === 'ellipsis') : ?>
                        <span class="is-ellipsis">...</span>
                    <?php elseif ((int) $page_item === $current_page) : ?>
                        <span class="is-current" aria-current="page"><?php echo esc_html((string) $page_item); ?></span>
                    <?php else : ?>
                        <a href="<?php echo esc_url($trash_page_url($page_item)); ?>"><?php echo esc_html((string) $page_item); ?></a>
                    <?php endif; ?>
                <?php endforeach; ?>

                <?php if ($current_page < $max_pages) : ?>
                    <a href="<?php echo esc_url($trash_page_url($current_page + 1)); ?>">下一页</a>
                <?php else : ?>
                    <span class="is-disabled">下一页</span>
                <?php endif; ?>
            </nav>
        <?php endif; ?>
    </section>
    <?php

    return home_workflow_kb_shell('trash', home_workflow_kb_compact_html(ob_get_clean()), $categories, $category_counts);
}

add_shortcode('kb_archive_home', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return '';
    }

    $can_edit = current_user_can('edit_posts');
    $kb_view = isset($_GET['kb_view']) ? sanitize_key(wp_unslash($_GET['kb_view'])) : '';
    if ($kb_view === 'new') {
        return home_workflow_render_kb_new_view();
    }
    if ($kb_view === 'trash') {
        return home_workflow_render_kb_trash_view();
    }
    if ($kb_view === 'sync') {
        return home_workflow_render_kb_sync_view();
    }
    if ($kb_view === 'accounts') {
        return home_workflow_render_kb_accounts_view();
    }

    $search_query = isset($_GET['s'])
        ? sanitize_text_field(wp_unslash($_GET['s']))
        : '';
    $category_id = isset($_GET['kb_category']) ? absint($_GET['kb_category']) : 0;
    $tag_id = isset($_GET['kb_tag']) ? absint($_GET['kb_tag']) : 0;
    $selected_category = $category_id ? get_category($category_id) : null;
    $selected_tag = $tag_id ? get_term($tag_id, 'post_tag') : null;
    $visible_statuses = home_workflow_kb_visible_statuses();
    $posts_per_page = 8;
    $requested_page = isset($_GET['kb_page']) ? max(1, absint($_GET['kb_page'])) : 1;

    $base_query_args = [
        'post_type' => 'post',
        'post_status' => $visible_statuses,
        'ignore_sticky_posts' => true,
    ];
    if ($search_query !== '') {
        $base_query_args['s'] = $search_query;
        $base_query_args['kb_source_search'] = $search_query;
    }
    if ($selected_category instanceof WP_Term) {
        $base_query_args['cat'] = $selected_category->term_id;
    }
    if ($selected_tag instanceof WP_Term) {
        $base_query_args['tag_id'] = $selected_tag->term_id;
    }

    $all_ids_query = new WP_Query(array_merge($base_query_args, [
        'posts_per_page' => -1,
        'fields' => 'ids',
        'no_found_rows' => true,
    ]));
    $all_ids = array_map('intval', $all_ids_query->posts);
    wp_reset_postdata();

    $sticky_lookup = array_flip(array_map('intval', (array) get_option('sticky_posts', [])));
    $sticky_ids = [];
    $regular_ids = [];
    foreach ($all_ids as $post_id) {
        if (isset($sticky_lookup[$post_id])) {
            $sticky_ids[] = $post_id;
        } else {
            $regular_ids[] = $post_id;
        }
    }

    $ordered_ids = array_merge($sticky_ids, $regular_ids);
    $total_matches = count($ordered_ids);
    $max_pages = max(1, (int) ceil($total_matches / $posts_per_page));
    $current_page = min($requested_page, $max_pages);
    $page_ids = array_slice($ordered_ids, ($current_page - 1) * $posts_per_page, $posts_per_page);
    $posts = new WP_Query([
        'post_type' => 'post',
        'post_status' => $visible_statuses,
        'post__in' => $page_ids ?: [0],
        'orderby' => 'post__in',
        'posts_per_page' => $page_ids ? count($page_ids) : 1,
        'ignore_sticky_posts' => true,
        'no_found_rows' => true,
    ]);

    $categories = array_values(array_filter(
        get_categories([
            'hide_empty' => false,
            'orderby' => 'name',
            'order' => 'ASC',
        ]),
        function ($category) {
            return $category->slug !== 'uncategorized';
        }
    ));
    $category_counts = [];
    foreach ($categories as $category) {
        $category_count_query = new WP_Query([
            'post_type' => 'post',
            'post_status' => $visible_statuses,
            'posts_per_page' => 1,
            'fields' => 'ids',
            'cat' => $category->term_id,
        ]);
        $category_counts[$category->term_id] = (int) $category_count_query->found_posts;
        wp_reset_postdata();
    }
    $can_manage_keywords = home_workflow_kb_can_manage_keywords();
    $tags = get_tags([
        'hide_empty' => false,
        'number' => 14,
        'orderby' => 'count',
        'order' => 'DESC',
    ]);
    if ($selected_tag instanceof WP_Term) {
        $tag_ids = array_map(
            function ($tag) {
                return (int) $tag->term_id;
            },
            $tags
        );
        if (!in_array((int) $selected_tag->term_id, $tag_ids, true)) {
            $tags[] = $selected_tag;
        }
    }
    $total_posts = wp_count_posts('post');
    $publish_count = (int) $total_posts->publish;
    $draft_count = in_array('draft', $visible_statuses, true) ? (int) $total_posts->draft : 0;
    $private_count = in_array('private', $visible_statuses, true) ? (int) $total_posts->private : 0;
    $visible_count = $publish_count + $draft_count + $private_count;
    $category_count = count($categories);
    $active_filter_count = 0;
    $active_filter_count += $search_query !== '' ? 1 : 0;
    $active_filter_count += $selected_category instanceof WP_Term ? 1 : 0;
    $active_filter_count += $selected_tag instanceof WP_Term ? 1 : 0;
    $section_title = '最近更新';
    if ($search_query !== '') {
        $section_title = '搜索：' . $search_query;
    } elseif ($selected_category instanceof WP_Term) {
        $section_title = '分类：' . $selected_category->name;
    } elseif ($selected_tag instanceof WP_Term) {
        $section_title = '标签：' . $selected_tag->name;
    }
    $make_filter_url = function (array $changes = []) use ($search_query, $category_id, $tag_id) {
        $args = [];
        if ($search_query !== '') {
            $args['s'] = $search_query;
        }
        if ($category_id) {
            $args['kb_category'] = (string) $category_id;
        }
        if ($tag_id) {
            $args['kb_tag'] = (string) $tag_id;
        }

        foreach ($changes as $key => $value) {
            if ($value === null || $value === '') {
                unset($args[$key]);
            } else {
                $args[$key] = (string) $value;
            }
        }

        return add_query_arg($args, home_url('/'));
    };
    $new_view_url = home_workflow_kb_view_url('new', $category_id);
    $trash_view_url = home_workflow_kb_view_url('trash', $category_id);

    ob_start();
    ?>
    <div class="kb-shell">
        <?php
        echo home_workflow_kb_sidebar('home', $categories, $category_counts, $can_edit, [
            'active_category_id' => $selected_category instanceof WP_Term ? (int) $selected_category->term_id : 0,
            'home_active' => $active_filter_count === 0,
            'search_active' => $search_query !== '',
            'new_url' => $new_view_url,
            'trash_url' => $trash_view_url,
            'category_manager_url' => '#kb-category-manager',
            'category_url_callback' => function ($category) use ($make_filter_url) {
                return $make_filter_url([
                    'kb_category' => $category->term_id,
                    'kb_tag' => null,
                ]);
            },
        ]);
        ?>

        <section class="kb-main">
            <header class="kb-hero">
                <div>
                    <div class="kb-eyebrow">Personal Knowledge Archive</div>
                    <h1>安静整理，持续积累</h1>
                    <p>把链接、资料、摘要与全文归档放到同一个安静界面里，检索、归类、回读都更顺手。</p>
                </div>
                <div class="kb-stats" aria-label="资料统计">
                    <span><?php echo esc_html((string) $visible_count); ?></span>
                    <small>条资料</small>
                    <em><?php echo esc_html((string) $category_count); ?> 个分类</em>
                </div>
            </header>

            <form class="kb-search" role="search" method="get" action="<?php echo esc_url(home_url('/')); ?>">
                <label class="screen-reader-text" for="kb-search-input">搜索资料</label>
                <?php if ($selected_category instanceof WP_Term) : ?>
                    <input type="hidden" name="kb_category" value="<?php echo esc_attr((string) $selected_category->term_id); ?>">
                <?php endif; ?>
                <?php if ($selected_tag instanceof WP_Term) : ?>
                    <input type="hidden" name="kb_tag" value="<?php echo esc_attr((string) $selected_tag->term_id); ?>">
                <?php endif; ?>
                <input id="kb-search-input" type="search" name="s" placeholder="搜索链接、主题、来源或备注" value="<?php echo esc_attr(get_search_query()); ?>">
                <button type="submit">搜索</button>
            </form>

            <?php if ($active_filter_count > 0) : ?>
                <div class="kb-active-filters" aria-label="当前筛选">
                    <span>当前筛选</span>
                    <?php if ($search_query !== '') : ?>
                        <a href="<?php echo esc_url($make_filter_url(['s' => null])); ?>">关键词：<?php echo esc_html($search_query); ?></a>
                    <?php endif; ?>
                    <?php if ($selected_category instanceof WP_Term) : ?>
                        <a href="<?php echo esc_url($make_filter_url(['kb_category' => null])); ?>">分类：<?php echo esc_html($selected_category->name); ?></a>
                    <?php endif; ?>
                    <?php if ($selected_tag instanceof WP_Term) : ?>
                        <a href="<?php echo esc_url($make_filter_url(['kb_tag' => null])); ?>">标签：<?php echo esc_html($selected_tag->name); ?></a>
                    <?php endif; ?>
                    <a class="kb-reset-filter" href="<?php echo esc_url(home_url('/')); ?>">清除全部</a>
                </div>
            <?php endif; ?>

            <?php if ($can_manage_keywords) : ?>
                <div class="kb-keyword-tools" aria-label="关键字管理">
                    <form class="kb-keyword-add-form" method="post" action="<?php echo esc_url(home_url('/')); ?>">
                        <input type="hidden" name="home_kb_tag_action" value="add">
                        <?php wp_nonce_field('home_kb_tag_add', 'home_kb_tag_nonce'); ?>
                        <label>
                            <span class="screen-reader-text">新增关键字</span>
                            <input type="text" name="home_kb_tag_name" placeholder="新增关键字" maxlength="40" required>
                        </label>
                        <button type="submit">添加</button>
                    </form>
                </div>
            <?php endif; ?>

            <?php if ($tags) : ?>
                <?php
                $keyword_list_style = $can_manage_keywords
                    ? 'display:flex;flex-wrap:wrap;align-items:center;gap:8px;width:min(100%, 560px);max-width:min(100%, 560px);overflow:visible;white-space:normal;'
                    : '';
                ?>
                <div class="kb-tags <?php echo $can_manage_keywords ? 'is-manage' : ''; ?>" aria-label="关键字" <?php echo $keyword_list_style !== '' ? 'style="' . esc_attr($keyword_list_style) . '"' : ''; ?>>
                    <?php foreach ($tags as $tag) : ?>
                        <?php
                        $is_active_tag = $selected_tag instanceof WP_Term && (int) $selected_tag->term_id === (int) $tag->term_id;
                        $delete_confirm = sprintf(
                            '确定删除“%s”关键字吗？文章不会删除，只会移除这个关键字。',
                            $tag->name
                        );
                        ?>
                        <div class="kb-tag-chip <?php echo $can_manage_keywords ? 'has-delete' : ''; ?>">
                            <a href="<?php echo esc_url($make_filter_url(['kb_tag' => $tag->term_id])); ?>" class="<?php echo $is_active_tag ? 'is-active' : ''; ?>" title="<?php echo esc_attr($tag->name); ?>" <?php echo $is_active_tag ? 'aria-current="page"' : ''; ?>>
                                <?php echo esc_html($tag->name); ?>
                            </a>
                            <?php if ($can_manage_keywords) : ?>
                                <form class="kb-tag-delete-form" method="post" action="<?php echo esc_url(home_url('/')); ?>" onsubmit="return confirm('<?php echo esc_js($delete_confirm); ?>');">
                                    <input type="hidden" name="home_kb_tag_action" value="delete">
                                    <input type="hidden" name="home_kb_tag_id" value="<?php echo esc_attr((string) $tag->term_id); ?>">
                                    <?php wp_nonce_field('home_kb_tag_delete_' . $tag->term_id, 'home_kb_tag_nonce'); ?>
                                    <button class="kb-tag-delete" type="submit" aria-label="<?php echo esc_attr('删除关键字：' . $tag->name); ?>">×</button>
                                </form>
                            <?php endif; ?>
                        </div>
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>

            <div class="kb-content-row <?php echo $can_edit ? 'has-status-panel' : 'is-reader-view'; ?>">
                <section class="kb-grid" aria-label="最近更新">
                    <div class="kb-section-heading">
                        <div>
                            <span><?php echo esc_html($section_title); ?></span>
                            <small><?php echo esc_html((string) $total_matches); ?> 条匹配资料<?php echo $max_pages > 1 ? ' · 第 ' . esc_html((string) $current_page) . ' / ' . esc_html((string) $max_pages) . ' 页' : ''; ?></small>
                        </div>
                        <?php if (current_user_can('manage_categories')) : ?>
                            <a href="#kb-category-manager">分类管理</a>
                        <?php endif; ?>
                    </div>

                    <?php if ($posts->have_posts()) : ?>
                        <?php while ($posts->have_posts()) : $posts->the_post(); ?>
                            <?php
                            $source_url = get_post_meta(get_the_ID(), 'source_url', true);
                            $source_site = get_post_meta(get_the_ID(), 'source_site', true);
                            $status = get_post_status();
                            $card_categories = array_values(array_filter(
                                get_the_category(),
                                function ($category) {
                                    return $category->slug !== 'uncategorized';
                                }
                            ));
                            $category_label = $card_categories ? $card_categories[0]->name : '未分类';
                            $current_category_id = $card_categories ? (int) $card_categories[0]->term_id : 0;
                            $content_text = trim(preg_replace('/\s+/u', ' ', wp_strip_all_tags(get_the_content(null, false, get_the_ID()), true)));
                            $content_length = function_exists('mb_strlen') ? mb_strlen($content_text, 'UTF-8') : strlen($content_text);
                            $read_minutes = max(1, (int) ceil($content_length / 650));
                            $excerpt = trim(preg_replace('/\s+/u', ' ', wp_strip_all_tags(get_the_excerpt(), true)));
                            if (function_exists('mb_strlen') && mb_strlen($excerpt, 'UTF-8') > 180) {
                                $excerpt = mb_substr($excerpt, 0, 180, 'UTF-8') . '...';
                            }
                            ?>
                            <article class="kb-card">
                                <div class="kb-card-meta">
                                    <time datetime="<?php echo esc_attr(get_the_date('c')); ?>"><?php echo esc_html(get_the_date('Y.m.d')); ?></time>
                                    <?php if (is_sticky()) : ?>
                                        <mark class="is-sticky">置顶</mark>
                                    <?php endif; ?>
                                    <span><?php echo esc_html($category_label); ?></span>
                                    <small><?php echo esc_html((string) $read_minutes); ?> 分钟</small>
                                    <?php if ($can_edit && $status !== 'publish') : ?>
                                        <mark><?php echo esc_html($status === 'draft' ? '草稿' : '私密'); ?></mark>
                                    <?php endif; ?>
                                </div>
                                <h2><a href="<?php the_permalink(); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html(get_the_title()); ?></a></h2>
                                <div class="kb-card-excerpt"><p><?php echo esc_html($excerpt); ?></p></div>
                                <div class="kb-card-footer">
                                    <span><?php echo esc_html($source_site ?: '个人整理'); ?></span>
                                    <div class="kb-card-actions">
                                        <a href="<?php the_permalink(); ?>" target="_blank" rel="noopener noreferrer">阅读</a>
                                        <?php if ($source_url) : ?>
                                            <a href="<?php echo esc_url($source_url); ?>" target="_blank" rel="noopener noreferrer">来源</a>
                                        <?php endif; ?>
                                        <?php if ($can_edit && current_user_can('edit_post', get_the_ID())) : ?>
                                            <form class="kb-sticky-form" method="post" action="<?php echo esc_url(home_url('/')); ?>">
                                                <input type="hidden" name="home_kb_post_id" value="<?php echo esc_attr((string) get_the_ID()); ?>">
                                                <input type="hidden" name="home_kb_sticky_action" value="<?php echo is_sticky() ? 'unstick' : 'stick'; ?>">
                                                <?php wp_nonce_field('home_kb_sticky_' . get_the_ID(), 'home_kb_sticky_nonce'); ?>
                                                <button type="submit"><?php echo is_sticky() ? '取消置顶' : '置顶'; ?></button>
                                            </form>
                                        <?php endif; ?>
                                        <?php if ($can_edit && current_user_can('edit_post', get_the_ID()) && current_user_can('assign_categories') && $categories) : ?>
                                            <form class="kb-card-category-form" method="post" action="<?php echo esc_url(home_url('/')); ?>">
                                                <input type="hidden" name="home_kb_post_id" value="<?php echo esc_attr((string) get_the_ID()); ?>">
                                                <input type="hidden" name="home_kb_post_action" value="category">
                                                <?php wp_nonce_field('home_kb_post_category_' . get_the_ID(), 'home_kb_post_nonce'); ?>
                                                <label>
                                                    <span class="screen-reader-text">修改文章分类</span>
                                                    <select name="home_kb_post_category">
                                                        <?php foreach ($categories as $category) : ?>
                                                            <option value="<?php echo esc_attr((string) $category->term_id); ?>" <?php selected($current_category_id, (int) $category->term_id); ?>><?php echo esc_html($category->name); ?></option>
                                                        <?php endforeach; ?>
                                                    </select>
                                                </label>
                                                <button type="submit">改分类</button>
                                            </form>
                                        <?php endif; ?>
                                        <?php if ($can_edit && current_user_can('delete_post', get_the_ID())) : ?>
                                            <form class="kb-delete-form" method="post" action="<?php echo esc_url(home_url('/')); ?>" onsubmit="return confirm('确定把这篇文章移入回收站吗？');">
                                                <input type="hidden" name="home_kb_post_id" value="<?php echo esc_attr((string) get_the_ID()); ?>">
                                                <input type="hidden" name="home_kb_post_action" value="trash">
                                                <?php wp_nonce_field('home_kb_post_trash_' . get_the_ID(), 'home_kb_post_nonce'); ?>
                                                <button type="submit">删除</button>
                                            </form>
                                        <?php endif; ?>
                                    </div>
                                </div>
                            </article>
                        <?php endwhile; ?>
                        <?php wp_reset_postdata(); ?>
                    <?php else : ?>
                        <article class="kb-card kb-empty">
                            <h2><?php echo ($search_query || $selected_category || $selected_tag) ? '没有匹配资料' : '还没有资料'; ?></h2>
                            <p><?php echo $can_edit ? '资料进入草稿后会显示在这里。' : '目前还没有可阅读的已发布资料。'; ?></p>
                        </article>
                    <?php endif; ?>

                    <?php if ($max_pages > 1) : ?>
                        <nav class="kb-pagination" aria-label="资料分页">
                            <?php if ($current_page > 1) : ?>
                                <a href="<?php echo esc_url($make_filter_url(['kb_page' => $current_page - 1])); ?>">上一页</a>
                            <?php else : ?>
                                <span class="is-disabled">上一页</span>
                            <?php endif; ?>

                            <?php foreach (home_workflow_kb_pagination_pages($current_page, $max_pages) as $page_item) : ?>
                                <?php if ($page_item === 'ellipsis') : ?>
                                    <span class="is-ellipsis">...</span>
                                <?php elseif ((int) $page_item === $current_page) : ?>
                                    <span class="is-current" aria-current="page"><?php echo esc_html((string) $page_item); ?></span>
                                <?php else : ?>
                                    <a href="<?php echo esc_url($make_filter_url(['kb_page' => $page_item])); ?>"><?php echo esc_html((string) $page_item); ?></a>
                                <?php endif; ?>
                            <?php endforeach; ?>

                            <?php if ($current_page < $max_pages) : ?>
                                <a href="<?php echo esc_url($make_filter_url(['kb_page' => $current_page + 1])); ?>">下一页</a>
                            <?php else : ?>
                                <span class="is-disabled">下一页</span>
                            <?php endif; ?>
                        </nav>
                    <?php endif; ?>
                </section>

                <?php if ($can_edit) : ?>
                    <aside class="kb-status-panel" aria-label="资料状态">
                        <div class="kb-status-title">资料状态</div>
                        <div class="kb-status-row"><strong><?php echo esc_html((string) $draft_count); ?></strong><small>草稿</small></div>
                        <div class="kb-status-row"><strong><?php echo esc_html((string) $private_count); ?></strong><small>私密</small></div>
                        <div class="kb-status-row"><strong><?php echo esc_html((string) $publish_count); ?></strong><small>已发布</small></div>
                        <div class="kb-status-tags">
                            <?php foreach (array_slice($tags, 0, 5) as $tag) : ?>
                                <a href="<?php echo esc_url($make_filter_url(['kb_tag' => $tag->term_id])); ?>"><?php echo esc_html($tag->name); ?></a>
                            <?php endforeach; ?>
                        </div>
                        <?php if (current_user_can('manage_categories')) : ?>
                            <div id="kb-category-manager" class="kb-category-manager">
                                <div class="kb-status-title">分类管理</div>
                                <form class="kb-category-add-form" method="post" action="<?php echo esc_url(home_url('/')); ?>">
                                    <input type="hidden" name="home_kb_category_action" value="add">
                                    <?php wp_nonce_field('home_kb_category_add', 'home_kb_category_nonce'); ?>
                                    <label>
                                        <span class="screen-reader-text">新增分类名称</span>
                                        <input type="text" name="home_kb_category_name" placeholder="新增分类" maxlength="40" required>
                                    </label>
                                    <button type="submit">添加</button>
                                </form>
                                <div class="kb-category-list">
                                    <?php $fallback_category_id = home_kb_uncategorized_category_id(true); ?>
                                    <?php foreach ($categories as $category) : ?>
                                        <?php
                                        $is_default_category = (int) $category->term_id === (int) get_option('default_category');
                                        $is_fallback_category = (int) $category->term_id === (int) $fallback_category_id;
                                        $delete_confirm = sprintf(
                                            '确定删除“%s”分类吗？该分类下的文章会先移到“未分类”，文章本身不会删除。',
                                            $category->name
                                        );
                                        ?>
                                        <div class="kb-category-row">
                                            <span class="kb-category-name">
                                                <?php echo esc_html($category->name); ?>
                                                <small><?php echo esc_html((string) ($category_counts[$category->term_id] ?? 0)); ?></small>
                                            </span>
                                            <?php if (!$is_default_category && !$is_fallback_category && $category->slug !== 'uncategorized') : ?>
                                                <form method="post" action="<?php echo esc_url(home_url('/')); ?>" onsubmit="return confirm('<?php echo esc_js($delete_confirm); ?>');">
                                                    <input type="hidden" name="home_kb_category_action" value="delete">
                                                    <input type="hidden" name="home_kb_category_id" value="<?php echo esc_attr((string) $category->term_id); ?>">
                                                    <?php wp_nonce_field('home_kb_category_delete_' . $category->term_id, 'home_kb_category_nonce'); ?>
                                                    <button type="submit">删除</button>
                                                </form>
                                            <?php endif; ?>
                                        </div>
                                    <?php endforeach; ?>
                                </div>
                            </div>
                        <?php endif; ?>
                    </aside>
                <?php endif; ?>
            </div>
        </section>
    </div>
    <?php
    return home_workflow_kb_compact_html(ob_get_clean());
});

add_filter('the_content', function ($content) {
    if (!is_singular('post')) {
        return $content;
    }

    $share_tools = home_workflow_public_share_controls(get_the_ID());
    if ($share_tools !== '') {
        $content = $share_tools . $content;
    }

    if (home_workflow_current_request_is_public_share()) {
        $content = '<aside class="source-note public-share-note"><strong>分享阅读：</strong>你正在通过公开分享链接阅读这篇文章，站内其他内容仍需要登录。</aside>' . $content;
    }

    $url = get_post_meta(get_the_ID(), 'source_url', true);
    if (!$url) {
        return $content;
    }

    $site = get_post_meta(get_the_ID(), 'source_site', true);
    $author = get_post_meta(get_the_ID(), 'source_author', true);
    $bits = [];

    if ($site) {
        $bits[] = esc_html($site);
    }
    if ($author) {
        $bits[] = esc_html($author);
    }

    $label = $bits ? implode(' / ', $bits) : '来源链接';
    $source = sprintf(
        '<aside class="source-note"><strong>来源：</strong><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></aside>',
        esc_url($url),
        $label
    );

    return $source . $content;
}, 12);

function home_workflow_open_content_links_in_new_tab($content) {
    if (!is_singular(['post', 'page']) || !class_exists('WP_HTML_Tag_Processor')) {
        return $content;
    }

    $processor = new WP_HTML_Tag_Processor($content);
    while ($processor->next_tag('A')) {
        $href = trim((string) $processor->get_attribute('href'));
        if ($href === '' || str_starts_with($href, '#')) {
            continue;
        }

        $scheme = strtolower((string) wp_parse_url($href, PHP_URL_SCHEME));
        if (in_array($scheme, ['javascript', 'mailto', 'tel'], true)) {
            continue;
        }

        $processor->set_attribute('target', '_blank');

        $rel = strtolower(trim((string) $processor->get_attribute('rel')));
        $rel_tokens = preg_split('/\s+/', $rel, -1, PREG_SPLIT_NO_EMPTY);
        foreach (['noopener', 'noreferrer'] as $token) {
            if (!in_array($token, $rel_tokens, true)) {
                $rel_tokens[] = $token;
            }
        }
        $processor->set_attribute('rel', implode(' ', $rel_tokens));
    }

    return $processor->get_updated_html();
}

add_filter('the_content', 'home_workflow_open_content_links_in_new_tab', 30);

add_filter('wp_headers', function ($headers) {
    $headers['X-Content-Type-Options'] = 'nosniff';
    $headers['Referrer-Policy'] = 'strict-origin-when-cross-origin';
    $headers['X-Frame-Options'] = 'SAMEORIGIN';
    $headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), interest-cohort=()';
    $headers['X-Robots-Tag'] = 'noindex, nofollow';
    return $headers;
});

add_filter('xmlrpc_enabled', '__return_false');
remove_action('wp_head', 'wp_generator');

add_action('template_redirect', function () {
    if (is_author()) {
        wp_safe_redirect(home_url('/'), 301);
        exit;
    }
});

add_filter('login_headerurl', function () {
    return home_url('/');
});

add_filter('login_headertext', function () {
    return home_workflow_site_profile()['title'];
});

add_action('login_header', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return;
    }
    ?>
    <div class="home-login-scene" aria-hidden="true">
        <div class="home-scene-copy">
            <span>PERSONAL KNOWLEDGE ARCHIVE</span>
            <h2>安静整理<br>持续积累</h2>
            <p>把链接、资料、摘要与全文归档放到同一个安静界面里。</p>
        </div>
        <div class="home-scene-nav">
            <span><b>01</b> 目录</span>
            <span><b>02</b> 检索</span>
            <span><b>03</b> 分类</span>
            <span><b>04</b> 回读</span>
        </div>
        <div class="home-desktop">
            <div class="home-login-feature">
                <span>QUIET ARCHIVE</span>
                <strong>整理 · 思考 · 沉淀</strong>
                <p>安静记录，持续积累，回到资料本身。</p>
            </div>
            <div class="home-login-index">
                <span><b>技术</b><small>工程、系统与工具</small></span>
                <span><b>健康</b><small>报告、疗法与记录</small></span>
                <span><b>资料</b><small>链接、全文与来源</small></span>
                <span><b>生活</b><small>长期主义的碎片</small></span>
            </div>
        </div>
    </div>
    <?php
});

add_filter('login_body_class', function ($classes) {
    $classes[] = home_workflow_site_profile()['body_class'];
    return $classes;
});

add_filter('login_message', function ($message) {
    if ($message) {
        return $message;
    }

    $profile = home_workflow_site_profile();
    return sprintf(
        '<div class="home-login-intro"><span>%s</span><strong>%s</strong><p>%s</p></div>',
        esc_html($profile['eyebrow']),
        esc_html($profile['title']),
        esc_html($profile['subtitle'])
    );
});

add_filter('login_redirect', function ($redirect_to, $requested_redirect_to, $user) {
    if ($user instanceof WP_User && home_workflow_site_kind() === 'kb') {
        return home_url('/');
    }

    return $redirect_to;
}, 10, 3);

add_filter('gettext', function ($translation, $text, $domain) {
    if ($domain !== 'default' || $GLOBALS['pagenow'] !== 'wp-login.php') {
        return $translation;
    }

    $map = [
        'Username or Email Address' => '账号',
        'Password' => '密码',
        'Remember Me' => '记住我',
        'Log In' => '登录',
        'Lost your password?' => '忘记密码？',
        '&larr; Go to %s' => '&larr; 返回 %s',
    ];

    return $map[$text] ?? $translation;
}, 10, 3);

add_action('login_enqueue_scripts', function () {
    $profile = home_workflow_site_profile();
    ?>
    <style>
        body.login {
            --home-bg: #f5f0e7;
            --home-paper: rgba(251, 248, 241, 0.82);
            --home-paper-soft: #fbf8f1;
            --home-ink: #201c17;
            --home-muted: #756f66;
            --home-line: rgba(32, 28, 23, 0.16);
            --home-line-strong: rgba(32, 28, 23, 0.42);
            --home-accent: #c24f35;
            --home-accent-strong: #4f6350;
            --home-serif: Georgia, "Songti SC", "Noto Serif SC", "Source Han Serif SC", serif;
            min-height: 100vh;
            box-sizing: border-box;
            background:
                linear-gradient(90deg, rgba(32, 28, 23, 0.022) 1px, transparent 1px),
                linear-gradient(180deg, rgba(32, 28, 23, 0.02) 1px, transparent 1px),
                linear-gradient(180deg, var(--home-bg) 0%, var(--home-paper-soft) 54%, #efe8dc 100%);
            background-size: 42px 42px, 42px 42px, auto;
            color: var(--home-ink);
            font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", "Noto Sans SC", "Microsoft YaHei", sans-serif;
        }

        body.login *,
        body.login *::before,
        body.login *::after {
            box-sizing: border-box;
        }

        body.login.home-login-kb {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            place-items: center;
            box-sizing: border-box;
            min-height: 100vh;
            padding: clamp(28px, 7vw, 64px) 18px;
            overflow: auto;
        }

        body.login.home-login-kb::before {
            content: "";
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background:
                radial-gradient(circle at 70% 14%, rgba(255, 255, 250, 0.56), transparent 22rem),
                linear-gradient(180deg, rgba(32, 28, 23, 0.035), transparent 38%);
            mix-blend-mode: multiply;
        }

        body.login.home-login-family {
            --home-bg: #fbf4e7;
            --home-paper: rgba(255, 250, 240, 0.92);
            --home-ink: #332a23;
            --home-muted: #7a6553;
            --home-line: rgba(155, 117, 88, 0.24);
            --home-accent: #b46a45;
            --home-accent-strong: #8c4d32;
            background:
                radial-gradient(circle at 15% 10%, rgba(180, 106, 69, 0.14), transparent 24rem),
                linear-gradient(135deg, rgba(155, 117, 88, 0.08) 0 25%, transparent 25% 50%, rgba(155, 117, 88, 0.05) 50% 75%, transparent 75%),
                var(--home-bg);
            background-size: auto, 22px 22px, auto;
        }

        .home-login-scene,
        .login #login {
            position: relative;
            z-index: 2;
        }

        .home-login-scene {
            width: min(620px, 100%);
            min-height: min(64vh, 620px);
            align-self: center;
            display: none;
            grid-template-columns: 104px minmax(0, 1fr);
            grid-template-rows: auto auto;
            gap: 24px 28px;
            padding-top: 26px;
            border-top: 2px solid var(--home-line-strong);
            border-bottom: 1px solid var(--home-line-strong);
        }

        .home-scene-copy {
            grid-column: 2;
            align-self: end;
        }

        .home-scene-copy span {
            display: inline-flex;
            align-items: center;
            gap: 9px;
            color: var(--home-accent);
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .home-scene-copy span::before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--home-accent);
        }

        .home-scene-copy h2 {
            margin: 18px 0 0;
            color: var(--home-ink);
            font-family: var(--home-serif);
            font-size: clamp(38px, 4.2vw, 50px);
            font-weight: 900;
            line-height: 1.04;
            letter-spacing: 0;
        }

        .home-scene-copy p {
            margin: 18px 0 0;
            max-width: 42rem;
            color: var(--home-muted);
            font-size: 15px;
            line-height: 1.9;
            letter-spacing: 0;
        }

        .home-scene-nav {
            grid-row: 2;
            display: grid;
            align-content: start;
            gap: 0;
            border-top: 1px solid var(--home-line);
            background: transparent;
        }

        .home-scene-nav span {
            position: relative;
            min-height: 46px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid var(--home-line);
            color: var(--home-muted);
            font-size: 13px;
            font-weight: 700;
        }

        .home-scene-nav b {
            color: rgba(32, 28, 23, 0.28);
            font-family: var(--home-serif);
            font-size: 26px;
            line-height: 1;
        }

        .home-desktop {
            grid-column: 2;
            grid-row: 2;
            position: relative;
            min-height: 300px;
            padding: 26px 0 34px;
            border-top: 1px solid var(--home-line);
            border-bottom: 0;
            background:
                linear-gradient(90deg, transparent 0 52%, rgba(32, 28, 23, 0.08) 52% calc(52% + 1px), transparent calc(52% + 1px)),
                transparent;
        }

        .home-login-feature {
            max-width: 560px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--home-line-strong);
        }

        .home-login-feature span {
            color: var(--home-accent);
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .home-login-feature strong {
            display: block;
            margin-top: 13px;
            color: var(--home-ink);
            font-family: var(--home-serif);
            font-size: clamp(24px, 3.4vw, 42px);
            font-weight: 900;
            line-height: 1.15;
        }

        .home-login-feature p {
            margin: 12px 0 0;
            max-width: 36rem;
            color: var(--home-muted);
            font-size: 14px;
            line-height: 1.85;
        }

        .home-login-index {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0 36px;
            margin-top: 28px;
        }

        .home-login-index span {
            min-height: 74px;
            display: grid;
            align-content: center;
            gap: 8px;
            border-top: 1px solid var(--home-line);
        }

        .home-login-index b {
            color: var(--home-ink);
            font-family: var(--home-serif);
            font-size: 20px;
            line-height: 1.2;
        }

        .home-login-index small {
            color: var(--home-muted);
            font-size: 12px;
            line-height: 1.5;
        }

        .home-books {
            position: absolute;
            left: 36px;
            bottom: 132px;
            display: flex;
            align-items: end;
            gap: 6px;
        }

        .home-books i {
            width: 44px;
            height: 205px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 10px 0;
            border: 1px solid rgba(76, 68, 58, 0.2);
            background: linear-gradient(90deg, #c4bca8, #eee5d4);
            color: #2f2b27;
            font-style: normal;
            writing-mode: vertical-rl;
            letter-spacing: 0.08em;
            box-shadow: inset -7px 0 16px rgba(47, 43, 39, 0.07);
        }

        .home-books i:nth-child(2) {
            height: 224px;
            background: linear-gradient(90deg, #b8b29f, #e5ddca);
        }

        .home-books i:nth-child(4) {
            height: 194px;
        }

        .home-keeper {
            position: absolute;
            left: 282px;
            bottom: 132px;
            width: 138px;
            height: 178px;
            border: 1px solid rgba(76, 68, 58, 0.18);
            background: linear-gradient(180deg, #d4c7ac, #b9aa8f);
            box-shadow: 14px 0 0 rgba(82, 57, 34, 0.42);
        }

        .home-keeper span {
            position: absolute;
            inset: 48px 34px auto;
            min-height: 66px;
            display: grid;
            place-items: center;
            background: rgba(255, 252, 245, 0.38);
            color: rgba(47, 43, 39, 0.72);
            font-size: 12px;
        }

        .home-vase {
            position: absolute;
            left: 500px;
            bottom: 118px;
            width: 88px;
            height: 122px;
            border-radius: 46% 46% 42% 42%;
            background: radial-gradient(circle at 36% 24%, #e2d5bd, #b9aa8f 70%);
            box-shadow: inset 10px -10px 22px rgba(47, 43, 39, 0.12);
        }

        .home-vase span {
            position: absolute;
            left: 40px;
            bottom: 96px;
            width: 1px;
            height: 190px;
            background: #6f7f68;
            transform-origin: bottom;
        }

        .home-vase span:nth-child(1) {
            transform: rotate(-22deg);
        }

        .home-vase span:nth-child(2) {
            height: 158px;
            transform: rotate(18deg);
        }

        .home-vase span:nth-child(3) {
            height: 130px;
            transform: rotate(42deg);
        }

        .home-vase span::after {
            content: "";
            position: absolute;
            top: 10px;
            left: -10px;
            width: 20px;
            height: 12px;
            border-radius: 100% 0;
            background: rgba(111, 127, 104, 0.72);
            box-shadow: 22px 28px 0 rgba(111, 127, 104, 0.52), -18px 58px 0 rgba(111, 127, 104, 0.46);
        }

        .home-paper-stack {
            position: absolute;
            left: 24px;
            bottom: 22px;
            width: 210px;
            height: 116px;
            transform: rotate(-6deg);
            border: 1px solid rgba(76, 68, 58, 0.14);
            background:
                linear-gradient(180deg, transparent 29px, rgba(76, 68, 58, 0.12) 30px, transparent 31px),
                #efe6d3;
            box-shadow: 10px 10px 0 rgba(220, 211, 194, 0.8), 22px 20px 26px rgba(47, 43, 39, 0.08);
        }

        .home-paper-stack span {
            position: absolute;
            top: 20px;
            left: 26px;
            color: rgba(76, 68, 58, 0.56);
            font-size: 14px;
        }

        .home-open-note {
            position: absolute;
            left: 280px;
            bottom: 4px;
            width: 250px;
            height: 132px;
            transform: rotate(3deg);
            border: 1px solid rgba(76, 68, 58, 0.12);
            background:
                linear-gradient(90deg, transparent 49%, rgba(76, 68, 58, 0.12) 50%, transparent 51%),
                repeating-linear-gradient(90deg, rgba(76, 68, 58, 0.12) 0 1px, transparent 1px 18px),
                #f4ecd9;
            box-shadow: 18px 20px 36px rgba(47, 43, 39, 0.08);
        }

        .home-tag-card {
            position: absolute;
            right: 22px;
            bottom: 16px;
            width: 158px;
            min-height: 70px;
            display: grid;
            place-items: center;
            transform: rotate(-5deg);
            border: 1px solid rgba(76, 68, 58, 0.16);
            background: #e4d7be;
            color: rgba(47, 43, 39, 0.72);
            font-size: 14px;
            line-height: 1.7;
            text-align: center;
        }

        .login #login {
            box-sizing: border-box;
            width: min(430px, calc(100vw - 44px));
            max-width: min(430px, calc(100vw - 44px));
            padding: 0;
            margin: max(6vh, 32px) auto !important;
            justify-self: center;
            border: 1px solid var(--home-line);
            border-radius: 0;
            background: rgba(251, 248, 241, 0.74);
            box-shadow: 0 22px 70px rgba(32, 28, 23, 0.08);
            padding: 38px 42px 32px;
        }

        body.login #login h1.wp-login-logo,
        body.login #login h1.wp-login-logo a {
            display: none !important;
        }

        .home-login-intro {
            margin: 0 0 24px;
            text-align: center;
        }

        .home-login-intro span {
            display: block;
            margin-bottom: 8px;
            color: var(--home-accent);
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .home-login-intro strong {
            display: block;
            color: var(--home-ink);
            font-family: var(--home-serif);
            font-size: 34px;
            font-weight: 900;
            letter-spacing: 0;
        }

        .home-login-intro strong::after {
            content: "";
            display: block;
            width: min(260px, 72%);
            height: 1px;
            margin: 18px auto 0;
            background: var(--home-line-strong);
        }

        .home-login-intro p {
            margin: 18px auto 0;
            max-width: 22rem;
            color: var(--home-muted);
            font-size: 14px;
            line-height: 1.78;
            overflow-wrap: anywhere;
        }

        .login #login form {
            margin-top: 0;
            padding: 0;
            border: 0 !important;
            border-radius: 0;
            background: transparent !important;
            box-shadow: none !important;
        }

        .login #login form p,
        .login .user-pass-wrap {
            margin: 0 0 12px;
        }

        .login .user-pass-wrap label {
            display: block;
            margin: 0 0 6px;
        }

        .login label {
            color: var(--home-muted);
            font-size: 11px;
            font-weight: 700;
            line-height: 1.25;
        }

        .login form .input,
        .login input[type="text"] {
            min-height: 38px;
            border: 1px solid var(--home-line);
            border-radius: 0;
            background: rgba(255, 252, 245, 0.72);
            color: var(--home-ink);
            font-size: 14px;
            box-shadow: none;
            padding: 0 12px;
        }

        .login form .input:focus,
        .login input[type="text"]:focus {
            border-color: var(--home-accent);
            box-shadow: 0 0 0 1px var(--home-accent);
        }

        .login .button.wp-hide-pw {
            width: 38px;
            height: 38px;
            min-height: 38px;
            color: #3d58ee;
        }

        .login .button.wp-hide-pw .dashicons {
            width: 18px;
            height: 18px;
            font-size: 18px;
        }

        .login .forgetmenot {
            float: none;
            display: flex;
            align-items: center;
            margin: 0 0 8px !important;
        }

        .login input[type="checkbox"] {
            width: 16px;
            height: 16px;
            min-width: 16px;
            margin: 0 8px 0 0;
            border-color: var(--home-line-strong);
        }

        .login .forgetmenot label {
            display: inline-flex;
            align-items: center;
            color: var(--home-muted);
            font-size: 12px;
            line-height: 1.2;
        }

        .login .submit {
            margin: 0 !important;
            padding: 0;
        }

        .wp-core-ui .button-primary {
            width: 100%;
            min-height: 40px;
            margin-top: 6px;
            border: 0 !important;
            border-radius: 0 !important;
            background: var(--home-accent-strong) !important;
            color: #fffaf0 !important;
            font-size: 14px !important;
            font-weight: 800;
        }

        .wp-core-ui .button-primary:hover,
        .wp-core-ui .button-primary:focus {
            background: var(--home-ink) !important;
        }

        .login #nav {
            margin: 24px 0 0;
            padding-top: 18px;
            border-top: 1px solid var(--home-line);
            text-align: center;
        }

        .login #backtoblog {
            display: none;
        }

        .login #nav a,
        .login .privacy-policy-page-link a {
            color: var(--home-muted);
        }

        @media (min-width: 1181px) {
            body.login.home-login-kb {
                display: grid;
                grid-template-columns: minmax(0, 620px) minmax(340px, 380px);
                align-items: center;
                justify-content: center;
                gap: clamp(34px, 4vw, 54px);
                padding: clamp(32px, 4vw, 56px);
                overflow: hidden;
            }

            .home-login-scene {
                display: grid;
            }

            .login #login {
                width: min(380px, 100%) !important;
                max-width: min(380px, 100%) !important;
                margin: 0 !important;
                justify-self: end;
                transform: none;
                padding: 36px 34px 30px;
            }
        }

        @media (max-width: 1180px) {
            body.login.home-login-kb {
                --login-card-width: clamp(238px, 38vw, 310px);
                --login-card-padding-x: clamp(14px, 2.7vw, 20px);
                --login-card-padding-y: clamp(13px, 2.6vw, 18px);
                --login-title-size: clamp(19px, 2.9vw, 22px);
                --login-copy-size: clamp(10px, 1.8vw, 12px);
                --login-control-height: clamp(28px, 4vw, 32px);
                --login-button-height: clamp(30px, 4.3vw, 34px);
                --login-row-gap: clamp(7px, 1.5vw, 9px);
                align-content: center;
                gap: clamp(20px, 4.5vh, 32px);
                padding: clamp(30px, 6vh, 56px) 16px;
            }

            .home-login-scene {
                width: min(370px, calc(100vw - 36px));
                min-height: 0;
                max-height: none;
                display: grid;
                grid-template-columns: 54px minmax(0, 1fr);
                grid-template-rows: auto auto;
                gap: 9px 12px;
                padding: 12px 0 10px;
                overflow: visible;
            }

            .home-scene-copy {
                grid-column: 2;
            }

            .home-scene-copy span {
                gap: 6px;
                font-size: 8px;
            }

            .home-scene-copy span::before {
                width: 5px;
                height: 5px;
            }

            .home-scene-copy h2 {
                margin-top: 6px;
                font-size: clamp(22px, 4.7vw, 26px);
                line-height: 1.12;
            }

            .home-scene-copy p {
                display: none;
            }

            .home-scene-nav {
                grid-row: 2;
            }

            .home-scene-nav span {
                min-height: 21px;
                gap: 5px;
                font-size: 9px;
            }

            .home-scene-nav b {
                font-size: 14px;
            }

            .home-desktop {
                grid-column: 2;
                grid-row: 2;
                min-height: 0;
                padding: 8px 0 0;
                background: none;
            }

            .home-login-feature {
                padding-bottom: 8px;
            }

            .home-login-feature span {
                font-size: 9px;
            }

            .home-login-feature strong {
                margin-top: 5px;
                font-size: clamp(16px, 3.8vw, 19px);
                line-height: 1.24;
            }

            .home-login-feature p {
                display: none;
            }

            .home-login-index {
                display: none;
            }

            .login #login {
                width: min(var(--login-card-width), calc(100vw - 40px)) !important;
                max-width: min(var(--login-card-width), calc(100vw - 40px)) !important;
                margin: 0 auto !important;
                background: rgba(251, 248, 241, 0.94);
                padding: var(--login-card-padding-y) var(--login-card-padding-x) calc(var(--login-card-padding-y) - 2px);
            }

            .home-login-intro strong {
                font-size: var(--login-title-size);
                line-height: 1.16;
                letter-spacing: 0;
            }

            .home-login-intro {
                margin-bottom: 14px;
                text-align: center;
            }

            .home-login-intro span {
                margin-bottom: 6px;
                font-size: 9px;
            }

            .home-login-intro strong::after {
                width: min(210px, 64%);
                margin-top: 12px;
            }

            .home-login-intro p {
                margin-top: 12px;
                margin-left: auto;
                max-width: 15.5rem;
                font-size: var(--login-copy-size);
                line-height: 1.55;
            }

            .login form .input,
            .login input[type="text"] {
                min-height: var(--login-control-height);
            }

            .login #login form p,
            .login .user-pass-wrap {
                margin-bottom: var(--login-row-gap);
            }

            .login .button.wp-hide-pw {
                width: var(--login-control-height);
                height: var(--login-control-height);
                min-height: var(--login-control-height);
            }

            .wp-core-ui .button-primary {
                min-height: var(--login-button-height);
                font-size: 14px !important;
            }

            .login #nav {
                margin-top: 14px;
                padding-top: 12px;
            }
        }

        @media (max-width: 700px) {
            body.login.home-login-kb {
                --login-card-width: clamp(226px, 50vw, 280px);
                --login-card-padding-x: clamp(12px, 3.3vw, 16px);
                --login-card-padding-y: clamp(12px, 3.5vw, 16px);
                --login-title-size: clamp(18px, 4.8vw, 20px);
                --login-copy-size: clamp(10px, 2.7vw, 11px);
                --login-control-height: clamp(27px, 5.5vw, 30px);
                --login-button-height: clamp(29px, 5.8vw, 32px);
                gap: 14px;
                padding: 18px 12px 24px;
            }

            .home-login-scene {
                width: min(300px, calc(100vw - 28px));
                max-height: none;
                grid-template-columns: minmax(0, 1fr);
                grid-template-rows: auto auto;
                gap: 7px;
                padding: 8px 0;
            }

            .home-scene-copy {
                grid-column: 1;
                align-self: start;
            }

            .home-scene-copy span {
                font-size: 7px;
            }

            .home-scene-copy h2 {
                margin-top: 5px;
                font-size: 18px;
                line-height: 1.1;
            }

            .home-scene-nav {
                display: none;
            }

            .home-login-feature {
                padding: 6px 0 0;
                border-top: 1px solid var(--home-line);
                border-bottom: 0;
            }

            .home-login-feature strong {
                margin-top: 4px;
                font-size: 14px;
                line-height: 1.2;
            }

            .home-login-index {
                display: none;
            }

            .login #login {
                width: min(var(--login-card-width), calc(100vw - 32px)) !important;
                max-width: min(var(--login-card-width), calc(100vw - 32px)) !important;
                padding: var(--login-card-padding-y) var(--login-card-padding-x) calc(var(--login-card-padding-y) - 2px);
            }

            .home-login-intro strong {
                font-size: var(--login-title-size);
            }

            .home-login-intro p {
                max-width: 16rem;
                font-size: var(--login-copy-size);
                line-height: 1.5;
            }

            .login form .input,
            .login input[type="text"] {
                min-height: var(--login-control-height);
            }

            .wp-core-ui .button-primary {
                min-height: var(--login-button-height);
            }
        }

        @media (max-width: 520px) {
            body.login.home-login-kb {
                --login-card-width: clamp(216px, 66vw, 264px);
                --login-card-padding-x: clamp(10px, 3.4vw, 14px);
                --login-card-padding-y: clamp(11px, 3.5vw, 16px);
                --login-title-size: clamp(18px, 5vw, 20px);
                --login-control-height: clamp(27px, 6.6vw, 30px);
                --login-button-height: clamp(29px, 6.8vw, 32px);
                padding: 16px 12px 22px;
                gap: 12px;
            }

            .home-login-scene {
                width: min(282px, calc(100vw - 24px));
                max-height: none;
                grid-template-columns: minmax(0, 1fr);
                gap: 6px;
                padding: 7px 0;
            }

            .home-scene-copy h2 {
                font-size: 17px;
            }

            .home-scene-copy p {
                display: none;
            }

            .home-login-feature strong {
                font-size: 13px;
            }

            .home-login-index {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .home-login-index small {
                display: none;
            }

            .login #login {
                width: min(var(--login-card-width), calc(100vw - 28px)) !important;
                max-width: min(var(--login-card-width), calc(100vw - 28px)) !important;
                padding: var(--login-card-padding-y) var(--login-card-padding-x);
            }

            .home-login-intro strong {
                font-size: var(--login-title-size);
            }

            .home-login-intro strong::after {
                margin-top: 10px;
            }

            .home-login-intro p {
                margin-top: 10px;
                font-size: 11px;
                line-height: 1.45;
            }

            .login form .input,
            .login input[type="text"] {
                min-height: var(--login-control-height);
            }

            .login input[type="checkbox"] {
                width: 14px;
                height: 14px;
                min-width: 14px;
                margin-right: 7px;
            }

            .login .forgetmenot label {
                font-size: 11px;
            }

            .wp-core-ui .button-primary {
                min-height: var(--login-button-height);
            }

            .login #nav {
                margin-top: 12px;
                padding-top: 10px;
            }
        }
    </style>
    <?php
});

add_action('login_footer', function () {
    if (home_workflow_site_kind() !== 'kb') {
        return;
    }
    ?>
    <script>
        (function () {
            var query = '(max-width: 700px)';
            if (!window.matchMedia || !window.matchMedia(query).matches) {
                return;
            }

            function settleLoginTop() {
                var userField = document.getElementById('user_login');
                if (userField) {
                    userField.removeAttribute('autofocus');
                    if (document.activeElement === userField) {
                        userField.blur();
                    }
                }
                window.scrollTo(0, 0);
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', settleLoginTop);
            } else {
                settleLoginTop();
            }
            window.setTimeout(settleLoginTop, 80);
            window.setTimeout(settleLoginTop, 240);
        })();
    </script>
    <?php
});

add_filter('show_admin_bar', function ($show) {
    if (!is_admin() && home_workflow_site_kind() === 'kb') {
        return false;
    }

    return $show;
});
