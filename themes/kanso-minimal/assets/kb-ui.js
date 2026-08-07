(function () {
  'use strict';

  document.documentElement.classList.add('kb-ui-ready');

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function onReady(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, { once: true });
      return;
    }
    callback();
  }

  function initMobileNavigation() {
    var sidebar = document.querySelector('[data-kb-mobile-nav]');
    if (!sidebar) {
      return;
    }

    var button = sidebar.querySelector('.kb-mobile-nav-toggle');
    var panel = sidebar.querySelector('.kb-sidebar-panel');
    if (!button || !panel) {
      return;
    }

    var mobile = window.matchMedia('(max-width: 900px)');

    function setOpen(open, returnFocus) {
      var shouldOpen = mobile.matches && open;
      sidebar.classList.toggle('is-open', shouldOpen);
      document.body.classList.toggle('kb-mobile-nav-open', shouldOpen);
      button.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
      button.setAttribute('title', shouldOpen ? '关闭菜单' : '打开菜单');

      var icon = button.querySelector('.kb-mobile-nav-icon');
      if (icon) {
        icon.textContent = shouldOpen ? '×' : '☰';
      }

      if (mobile.matches) {
        panel.setAttribute('aria-hidden', shouldOpen ? 'false' : 'true');
      } else {
        panel.removeAttribute('aria-hidden');
      }

      if (returnFocus) {
        button.focus();
      }
    }

    function syncViewport() {
      setOpen(false, false);
    }

    button.addEventListener('click', function () {
      setOpen(!sidebar.classList.contains('is-open'), false);
    });

    panel.addEventListener('click', function (event) {
      if (event.target.closest('a')) {
        setOpen(false, false);
      }
    });

    document.addEventListener('click', function (event) {
      if (sidebar.classList.contains('is-open') && !sidebar.contains(event.target)) {
        setOpen(false, false);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && sidebar.classList.contains('is-open')) {
        setOpen(false, true);
      }
    });

    if (typeof mobile.addEventListener === 'function') {
      mobile.addEventListener('change', syncViewport);
    } else {
      mobile.addListener(syncViewport);
    }

    syncViewport();
  }

  function initCardMenus() {
    var menus = Array.prototype.slice.call(document.querySelectorAll('.kb-card-manage'));
    if (!menus.length) {
      return;
    }

    function closeMenus(except) {
      menus.forEach(function (menu) {
        if (menu !== except) {
          menu.open = false;
        }
      });
    }

    menus.forEach(function (menu) {
      menu.addEventListener('toggle', function () {
        if (menu.open) {
          closeMenus(menu);
        }
      });
    });

    document.addEventListener('click', function (event) {
      if (!event.target.closest('.kb-card-manage')) {
        closeMenus(null);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') {
        return;
      }

      var openMenu = document.querySelector('.kb-card-manage[open]');
      if (!openMenu) {
        return;
      }

      openMenu.open = false;
      var summary = openMenu.querySelector('summary');
      if (summary) {
        summary.focus();
      }
    });
  }

  function initReaderTools() {
    var tools = Array.prototype.slice.call(document.querySelectorAll('.kb-reader-tool'));
    tools.forEach(function (tool) {
      tool.addEventListener('toggle', function () {
        if (!tool.open) {
          return;
        }
        tools.forEach(function (other) {
          if (other !== tool) {
            other.open = false;
          }
        });
      });
    });
  }

  function headingSlug(text, index) {
    var normalized = text;
    if (typeof normalized.normalize === 'function') {
      normalized = normalized.normalize('NFKC');
    }

    normalized = normalized
      .toLowerCase()
      .replace(/[^a-z0-9\u3400-\u9fff\uf900-\ufaff]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 72);

    return 'kb-section-' + (normalized || String(index + 1));
  }

  function ensureHeadingIds(headings) {
    var used = new Set();
    document.querySelectorAll('[id]').forEach(function (element) {
      if (element.id) {
        used.add(element.id);
      }
    });

    headings.forEach(function (heading, index) {
      if (heading.id) {
        return;
      }

      var base = headingSlug(heading.textContent.trim(), index);
      var candidate = base;
      var suffix = 2;
      while (used.has(candidate)) {
        candidate = base + '-' + suffix;
        suffix += 1;
      }
      heading.id = candidate;
      used.add(candidate);
    });
  }

  function initReaderToc(content, headings) {
    if (headings.length < 3) {
      return null;
    }

    ensureHeadingIds(headings);

    var toc = document.createElement('details');
    toc.className = 'kb-reader-toc';

    var summary = document.createElement('summary');
    summary.textContent = '本文目录';
    toc.appendChild(summary);

    var nav = document.createElement('nav');
    nav.setAttribute('aria-label', '本文目录');
    var list = document.createElement('ol');
    var links = [];

    headings.forEach(function (heading) {
      var item = document.createElement('li');
      item.className = heading.tagName === 'H3' ? 'is-level-3' : 'is-level-2';

      var link = document.createElement('a');
      link.href = '#' + encodeURIComponent(heading.id);
      link.textContent = heading.textContent.trim();
      link.addEventListener('click', function (event) {
        event.preventDefault();
        if (!window.matchMedia('(min-width: 1180px)').matches) {
          toc.open = false;
        }

        window.requestAnimationFrame(function () {
          heading.scrollIntoView({
            behavior: reduceMotion.matches ? 'auto' : 'smooth',
            block: 'start'
          });
          window.history.replaceState(null, '', '#' + encodeURIComponent(heading.id));
        });
      });

      item.appendChild(link);
      list.appendChild(item);
      links.push(link);
    });

    nav.appendChild(list);
    toc.appendChild(nav);

    var readerHead = document.querySelector('.kb-reader-head');
    if (readerHead && readerHead.parentNode) {
      readerHead.insertAdjacentElement('afterend', toc);
    } else {
      content.parentNode.insertBefore(toc, content);
    }

    var wide = window.matchMedia('(min-width: 1180px)');
    function syncTocMode() {
      toc.open = wide.matches;
    }
    if (typeof wide.addEventListener === 'function') {
      wide.addEventListener('change', syncTocMode);
    } else {
      wide.addListener(syncTocMode);
    }
    syncTocMode();

    var activeIndex = -1;
    function updateActiveLink() {
      var marker = window.pageYOffset + Math.min(window.innerHeight * 0.28, 190);
      var nextIndex = 0;
      headings.forEach(function (heading, index) {
        var top = heading.getBoundingClientRect().top + window.pageYOffset;
        if (top <= marker) {
          nextIndex = index;
        }
      });

      if (nextIndex === activeIndex) {
        return;
      }
      activeIndex = nextIndex;
      links.forEach(function (link, index) {
        link.classList.toggle('is-active', index === activeIndex);
        if (index === activeIndex) {
          link.setAttribute('aria-current', 'location');
        } else {
          link.removeAttribute('aria-current');
        }
      });
    }

    return {
      element: toc,
      update: updateActiveLink
    };
  }

  function fallbackCopy(text) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    var copied = document.execCommand('copy');
    textarea.remove();
    return copied ? Promise.resolve() : Promise.reject(new Error('copy failed'));
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return fallbackCopy(text);
  }

  function initCodeCopy(content) {
    content.querySelectorAll('pre').forEach(function (block) {
      if (block.querySelector('.kb-code-copy')) {
        return;
      }

      var source = block.textContent.replace(/\s+$/, '');
      if (!source) {
        return;
      }

      block.classList.add('kb-code-block');
      var button = document.createElement('button');
      button.className = 'kb-code-copy';
      button.type = 'button';
      button.textContent = '复制';
      button.setAttribute('aria-label', '复制代码');

      var resetTimer = 0;
      button.addEventListener('click', function () {
        window.clearTimeout(resetTimer);
        copyText(source).then(function () {
          button.textContent = '已复制';
          resetTimer = window.setTimeout(function () {
            button.textContent = '复制';
          }, 1600);
        }).catch(function () {
          button.textContent = '复制失败';
          resetTimer = window.setTimeout(function () {
            button.textContent = '复制';
          }, 1800);
        });
      });

      block.insertBefore(button, block.firstChild);
    });
  }

  function initReader() {
    var article = document.querySelector('.kb-reader-article');
    var content = article ? article.querySelector('.wp-block-post-content') : null;
    if (!article || !content) {
      return;
    }

    var progress = document.createElement('div');
    progress.className = 'kb-reading-progress';
    progress.setAttribute('role', 'progressbar');
    progress.setAttribute('aria-label', '阅读进度');
    progress.setAttribute('aria-valuemin', '0');
    progress.setAttribute('aria-valuemax', '100');
    progress.setAttribute('aria-valuenow', '0');
    progress.innerHTML = '<span></span>';
    document.body.appendChild(progress);

    var backToTop = document.createElement('button');
    backToTop.className = 'kb-back-to-top';
    backToTop.type = 'button';
    backToTop.setAttribute('aria-label', '返回顶部');
    backToTop.setAttribute('title', '返回顶部');
    backToTop.textContent = '↑';
    document.body.appendChild(backToTop);

    backToTop.addEventListener('click', function () {
      window.scrollTo({
        top: 0,
        behavior: reduceMotion.matches ? 'auto' : 'smooth'
      });
    });

    var headings = Array.prototype.slice.call(content.children).filter(function (element) {
      return element.tagName === 'H2' || element.tagName === 'H3';
    });
    var toc = initReaderToc(content, headings);
    initCodeCopy(content);

    var scheduled = false;
    function updateReaderState() {
      scheduled = false;
      var scrollTop = Math.max(window.pageYOffset, document.documentElement.scrollTop || 0);
      var scrollRange = Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);
      var percent = scrollRange > 0 ? Math.min(100, Math.max(0, (scrollTop / scrollRange) * 100)) : 0;

      progress.classList.toggle('is-active', scrollRange > 240);
      progress.firstElementChild.style.transform = 'scaleX(' + (percent / 100) + ')';
      progress.setAttribute('aria-valuenow', String(Math.round(percent)));
      backToTop.classList.toggle('is-visible', scrollTop > Math.max(640, window.innerHeight * 0.75));

      if (toc) {
        toc.update();
      }
    }

    function scheduleUpdate() {
      if (scheduled) {
        return;
      }
      scheduled = true;
      window.requestAnimationFrame(updateReaderState);
    }

    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    scheduleUpdate();

    if (window.location.hash) {
      var targetId = window.location.hash.slice(1);
      try {
        targetId = decodeURIComponent(targetId);
      } catch (error) {
        targetId = window.location.hash.slice(1);
      }
      var target = document.getElementById(targetId);
      if (target && headings.indexOf(target) !== -1) {
        window.requestAnimationFrame(function () {
          target.scrollIntoView({ block: 'start' });
        });
      }
    }
  }

  onReady(function () {
    initMobileNavigation();
    initCardMenus();
    initReaderTools();
    initReader();
  });
}());
