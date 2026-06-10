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

function kanso_minimal_pwa_enabled() {
    return !function_exists('home_workflow_site_kind') || home_workflow_site_kind() === 'kb';
}

function kanso_minimal_pwa_version() {
    $style_path = get_stylesheet_directory() . '/style.css';
    return file_exists($style_path) ? (string) filemtime($style_path) : (string) wp_get_theme()->get('Version');
}

function kanso_minimal_pwa_manifest_url() {
    return home_url('/kb-app.webmanifest');
}

function kanso_minimal_pwa_service_worker_url() {
    return home_url('/kb-service-worker.js');
}

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

function kanso_minimal_pwa_head() {
    if (!kanso_minimal_pwa_enabled()) {
        return;
    }

    $version = kanso_minimal_pwa_version();
    $touch_icon = add_query_arg('v', $version, get_theme_file_uri('assets/kb-icon-192.png'));
    ?>
    <link rel="manifest" href="<?php echo esc_url(add_query_arg('v', $version, kanso_minimal_pwa_manifest_url())); ?>">
    <meta name="theme-color" content="#f7f3ea">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="个人知识库">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <link rel="apple-touch-icon" href="<?php echo esc_url($touch_icon); ?>">
    <?php
}

add_action('wp_head', 'kanso_minimal_pwa_head', 98);
add_action('login_head', 'kanso_minimal_pwa_head', 98);

function kanso_minimal_pwa_register_script() {
    if (!kanso_minimal_pwa_enabled() || is_admin()) {
        return;
    }
    ?>
    <script>
    (function () {
        if (!('serviceWorker' in navigator)) {
            return;
        }

        window.addEventListener('load', function () {
            navigator.serviceWorker.register('<?php echo esc_js(kanso_minimal_pwa_service_worker_url()); ?>', { scope: '/' }).catch(function () {});
        });
    }());
    </script>
    <?php
}

add_action('wp_footer', 'kanso_minimal_pwa_register_script', 99);
add_action('login_footer', 'kanso_minimal_pwa_register_script', 99);

function kanso_minimal_pwa_request_path() {
    $path = parse_url((string) ($_SERVER['REQUEST_URI'] ?? ''), PHP_URL_PATH);
    return is_string($path) ? $path : '';
}

function kanso_minimal_pwa_send_headers($content_type) {
    status_header(200);
    nocache_headers();
    header('Content-Type: ' . $content_type . '; charset=utf-8');
}

function kanso_minimal_pwa_manifest() {
    $version = kanso_minimal_pwa_version();
    $icon_192 = add_query_arg('v', $version, get_theme_file_uri('assets/kb-icon-192.png'));
    $icon_512 = add_query_arg('v', $version, get_theme_file_uri('assets/kb-icon-512.png'));

    return [
        'id' => home_url('/'),
        'name' => '个人知识库',
        'short_name' => '知识库',
        'description' => '自托管个人知识库，用于资料归档、检索、分类和回读。',
        'start_url' => home_url('/?source=pwa'),
        'scope' => home_url('/'),
        'display' => 'standalone',
        'background_color' => '#f7f3ea',
        'theme_color' => '#526f5a',
        'categories' => ['productivity', 'books', 'utilities'],
        'icons' => [
            [
                'src' => esc_url_raw($icon_192),
                'sizes' => '192x192',
                'type' => 'image/png',
                'purpose' => 'any maskable',
            ],
            [
                'src' => esc_url_raw($icon_512),
                'sizes' => '512x512',
                'type' => 'image/png',
                'purpose' => 'any maskable',
            ],
        ],
        'shortcuts' => [
            [
                'name' => '新资料',
                'short_name' => '新增',
                'description' => '打开前台 Markdown 新增资料入口。',
                'url' => home_url('/?kb_view=new'),
                'icons' => [
                    [
                        'src' => esc_url_raw($icon_192),
                        'sizes' => '192x192',
                    ],
                ],
            ],
            [
                'name' => '检索资料',
                'short_name' => '检索',
                'description' => '打开知识库检索入口。',
                'url' => home_url('/#kb-search-input'),
                'icons' => [
                    [
                        'src' => esc_url_raw($icon_192),
                        'sizes' => '192x192',
                    ],
                ],
            ],
        ],
        'share_target' => [
            'action' => home_url('/?kb_view=new'),
            'method' => 'GET',
            'enctype' => 'application/x-www-form-urlencoded',
            'params' => [
                'title' => 'title',
                'text' => 'text',
                'url' => 'url',
            ],
        ],
    ];
}

function kanso_minimal_pwa_service_worker() {
    $version = kanso_minimal_pwa_version();
    $cache_name = 'personal-kb-shell-' . preg_replace('/[^A-Za-z0-9_-]/', '', $version);
    $offline_url = home_url('/kb-offline/');
    $asset_urls = [
        $offline_url,
        add_query_arg('v', $version, kanso_minimal_pwa_manifest_url()),
        add_query_arg('v', $version, get_stylesheet_uri()),
        add_query_arg('v', $version, get_theme_file_uri('assets/kb-favicon.svg')),
        add_query_arg('v', $version, get_theme_file_uri('assets/kb-icon-192.png')),
        add_query_arg('v', $version, get_theme_file_uri('assets/kb-icon-512.png')),
    ];

    ob_start();
    ?>
const CACHE_NAME = <?php echo wp_json_encode($cache_name); ?>;
const OFFLINE_URL = <?php echo wp_json_encode($offline_url); ?>;
const ASSET_URLS = <?php echo wp_json_encode(array_values($asset_urls)); ?>;

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(ASSET_URLS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key.indexOf('personal-kb-shell-') === 0 && key !== CACHE_NAME) {
          return caches.delete(key);
        }
        return Promise.resolve();
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  var url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.indexOf('/wp-admin/') === 0 || url.pathname.indexOf('/wp-json/') === 0 || url.pathname.indexOf('/xmlrpc.php') === 0) {
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(function () {
        return caches.match(OFFLINE_URL);
      })
    );
    return;
  }

  if (['style', 'script', 'image', 'font', 'manifest'].indexOf(request.destination) !== -1) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        if (cached) {
          return cached;
        }

        return fetch(request).then(function (response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(CACHE_NAME).then(function (cache) {
              cache.put(request, copy);
            });
          }
          return response;
        });
      })
    );
  }
});
    <?php

    return trim(ob_get_clean());
}

function kanso_minimal_pwa_offline_page() {
    $icon = esc_url(add_query_arg('v', kanso_minimal_pwa_version(), get_theme_file_uri('assets/kb-favicon.svg')));
    $home = esc_url(home_url('/'));

    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f3ea"><title>个人知识库离线</title><style>body{min-height:100vh;margin:0;display:grid;place-items:center;background:#f7f3ea;color:#2f2b27;font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}.offline{width:min(28rem,calc(100% - 40px));padding:32px;border:1px solid rgba(76,68,58,.16);background:rgba(255,252,245,.76)}img{width:52px;height:52px}h1{margin:18px 0 8px;font-size:24px}p{margin:0 0 22px;color:#6c6257}a{display:inline-flex;min-height:40px;align-items:center;padding:0 14px;border-radius:6px;background:#2f4d5a;color:#fff;text-decoration:none}</style></head><body><main class="offline"><img src="' . $icon . '" alt=""><h1>当前离线</h1><p>已保存 App 外壳，私密资料正文不会默认离线缓存。网络恢复后再刷新知识库。</p><a href="' . $home . '">重新打开</a></main></body></html>';
}

add_action('parse_request', function () {
    if (!kanso_minimal_pwa_enabled()) {
        return;
    }

    $path = kanso_minimal_pwa_request_path();

    if ($path === '/kb-app.webmanifest') {
        kanso_minimal_pwa_send_headers('application/manifest+json');
        echo wp_json_encode(kanso_minimal_pwa_manifest(), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
        exit;
    }

    if ($path === '/kb-service-worker.js') {
        kanso_minimal_pwa_send_headers('application/javascript');
        header('Service-Worker-Allowed: /');
        echo kanso_minimal_pwa_service_worker();
        exit;
    }

    if ($path === '/kb-offline') {
        wp_safe_redirect(home_url('/kb-offline/'), 301);
        exit;
    }

    if ($path === '/kb-offline/') {
        kanso_minimal_pwa_send_headers('text/html');
        echo kanso_minimal_pwa_offline_page();
        exit;
    }
}, 0);
