/* paper-tutor — reading surface behaviour.
   No dependencies, no network, works from file:// . */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var body = document.body;
  var main = document.querySelector('[data-main]');
  var side = document.querySelector('[data-side]');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.para'));
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-p'));
  var tocSecs = Array.prototype.slice.call(document.querySelectorAll('.toc-sec'));
  var counterCur = document.querySelector('[data-cur]');
  var counterTotal = document.querySelector('[data-total]');
  var progressBar = document.querySelector('[data-progress]');
  var searchInput = document.querySelector('[data-search]');
  var searchCount = document.querySelector('[data-search-count]');
  var toTop = document.querySelector('[data-act="top"]');
  var fontButtonUp = document.querySelector('[data-act="font-up"]');

  var state = { list: cards.slice(), cur: 0, query: '', ticking: false };

  var store = {
    get: function (key, fallback) {
      try {
        var raw = localStorage.getItem('pcr.' + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (err) {
        return fallback;
      }
    },
    set: function (key, value) {
      try {
        localStorage.setItem('pcr.' + key, JSON.stringify(value));
      } catch (err) {
        /* private mode: ignore */
      }
    }
  };

  function cardTop(card) {
    var rect = card.getBoundingClientRect();
    return rect.top + main.scrollTop - main.getBoundingClientRect().top;
  }

  function goTo(card, smooth) {
    if (!card) {
      return;
    }
    var top = Math.max(0, cardTop(card) - 6);
    main.scrollTo({ top: top, behavior: smooth && !reduceMotion ? 'smooth' : 'auto' });
  }

  function flash(card) {
    if (!card) {
      return;
    }
    card.classList.remove('flash');
    void card.offsetWidth;
    card.classList.add('flash');
    window.setTimeout(function () {
      card.classList.remove('flash');
    }, 1500);
  }

  function markActive(index, reveal) {
    if (!state.list.length) {
      return;
    }
    index = Math.max(0, Math.min(state.list.length - 1, index));
    if (index === state.cur && reveal) {
      return;
    }
    state.cur = index;
    var card = state.list[index];
    cards.forEach(function (item) {
      item.classList.toggle('active', item === card);
    });
    var id = card.getAttribute('data-id');
    tocLinks.forEach(function (link) {
      link.classList.toggle('active', link.getAttribute('data-target') === id);
    });
    if (counterCur) {
      counterCur.textContent = String(index + 1);
    }
    if (progressBar) {
      var ratio = state.list.length > 1 ? index / (state.list.length - 1) : 1;
      progressBar.style.transform = 'scaleX(' + ratio.toFixed(4) + ')';
    }
    if (reveal) {
      var active = tocLinks.filter(function (link) {
        return link.getAttribute('data-target') === id;
      })[0];
      if (active && side && side.scrollHeight > side.clientHeight) {
        var box = active.getBoundingClientRect();
        var panel = side.getBoundingClientRect();
        if (box.top < panel.top + 10 || box.bottom > panel.bottom - 10) {
          active.scrollIntoView({ block: 'nearest' });
        }
      }
    }
  }

  function currentIndexFromScroll() {
    var probe = main.getBoundingClientRect().top + 110;
    var found = 0;
    for (var i = 0; i < state.list.length; i += 1) {
      var rect = state.list[i].getBoundingClientRect();
      if (rect.height === 0) {
        continue;
      }
      if (rect.top <= probe) {
        found = i;
      } else {
        break;
      }
    }
    return found;
  }

  function onScroll() {
    if (state.ticking) {
      return;
    }
    state.ticking = true;
    window.requestAnimationFrame(function () {
      state.ticking = false;
      if (state.list.length) {
        markActive(currentIndexFromScroll(), true);
      }
      if (toTop) {
        var offset = main.scrollTop;
        toTop.classList.toggle('show', offset > 520);
      }
    });
  }

  function step(delta) {
    if (!state.list.length) {
      return;
    }
    var next = Math.max(0, Math.min(state.list.length - 1, state.cur + delta));
    markActive(next, true);
    goTo(state.list[next], true);
  }

  /* ---------- theme ---------- */

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
    store.set('theme', theme === 'dark' ? 'dark' : 'light');
  }

  /* ---------- font size ---------- */

  function applyFont(px) {
    var size = Math.max(13, Math.min(21, Math.round(px * 2) / 2));
    document.documentElement.style.setProperty('--fs', size + 'px');
    store.set('font', size);
    return size;
  }

  /* ---------- content width ---------- */

  var WIDTH = { min: 860, max: 2200, step: 20, def: 1120 };
  var widthBtn = document.querySelector('[data-act="width"]');
  var widthPanel = document.querySelector('[data-width-panel]');
  var widthRange = document.querySelector('[data-width-range]');
  var widthValue = document.querySelector('[data-width-value]');
  var widthNow = WIDTH.def;

  function clampWidth(px) {
    var value = Number(px);
    if (!isFinite(value)) {
      value = WIDTH.def;
    }
    value = Math.round(value / WIDTH.step) * WIDTH.step;
    return Math.max(WIDTH.min, Math.min(WIDTH.max, value));
  }

  function paintWidth(value) {
    var full = value === 'none';
    if (widthRange) {
      widthRange.value = String(full ? WIDTH.max : value);
    }
    if (widthValue) {
      widthValue.textContent = full ? '满宽' : value + 'px';
    }
    if (widthBtn) {
      widthBtn.title = '内容宽度 ' + (full ? '满宽' : value + 'px') + '（快捷键 [ ]）';
    }
  }

  function applyWidth(raw, persist) {
    var value = raw === 'none' ? 'none' : clampWidth(raw);
    widthNow = value;
    document.documentElement.style.setProperty('--content-w', value === 'none' ? 'none' : value + 'px');
    if (persist !== false) {
      store.set('width', value);
    }
    paintWidth(value);
    return value;
  }

  function widthOpen() {
    return Boolean(widthPanel && widthPanel.classList.contains('open'));
  }

  function openWidth(open) {
    if (!widthPanel || !widthBtn) {
      return;
    }
    widthPanel.classList.toggle('open', open);
    widthBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function closeWidth() {
    openWidth(false);
  }

  /* ---------- search ---------- */

  function applyQuery(raw) {
    var query = String(raw || '').trim().toLowerCase();
    state.query = query;
    var matched = [];

    cards.forEach(function (card) {
      var hit = !query || card.textContent.toLowerCase().indexOf(query) !== -1;
      card.classList.toggle('hide', !hit);
      if (hit) {
        matched.push(card);
      }
    });

    var ids = {};
    matched.forEach(function (card) {
      ids[card.getAttribute('data-id')] = true;
    });
    tocLinks.forEach(function (link) {
      link.classList.toggle('hide', Boolean(query) && !ids[link.getAttribute('data-target')]);
    });
    tocSecs.forEach(function (section) {
      var visible = section.querySelectorAll('.toc-p:not(.hide)').length;
      section.classList.toggle('hide', Boolean(query) && visible === 0);
    });

    state.list = matched;
    state.cur = 0;
    if (counterTotal) {
      counterTotal.textContent = String(matched.length);
    }
    if (searchCount) {
      searchCount.textContent = query ? matched.length + '/' + cards.length : '';
    }
    if (matched.length) {
      markActive(0, false);
    } else if (progressBar) {
      progressBar.style.transform = 'scaleX(0)';
    }
    if (query && matched.length) {
      goTo(matched[0], false);
    }
  }

  var searchTimer = 0;
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      window.clearTimeout(searchTimer);
      var value = searchInput.value;
      searchTimer = window.setTimeout(function () {
        applyQuery(value);
      }, 130);
    });
    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        searchInput.value = '';
        applyQuery('');
        searchInput.blur();
        event.stopPropagation();
      } else if (event.key === 'Enter') {
        window.clearTimeout(searchTimer);
        applyQuery(searchInput.value);
      }
    });
  }

  /* ---------- pane toggles ---------- */

  function applyPane(name, visible) {
    body.classList.toggle('hide-' + name, !visible);
    store.set('pane.' + name, visible);
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-pane]'), function (box) {
    var key = box.getAttribute('data-pane');
    var saved = store.get('pane.' + key, true);
    box.checked = saved;
    body.classList.toggle('hide-' + key, !saved);
    box.addEventListener('change', function () {
      applyPane(key, box.checked);
    });
  });

  /* ---------- drawer ---------- */

  var backdrop = document.createElement('div');
  backdrop.className = 'side-backdrop';
  body.appendChild(backdrop);

  function closeDrawer() {
    if (!side) {
      return;
    }
    side.classList.remove('open');
    backdrop.classList.remove('show');
  }

  function toggleDrawer() {
    if (!side) {
      return;
    }
    var open = !side.classList.contains('open');
    side.classList.toggle('open', open);
    backdrop.classList.toggle('show', open);
  }

  backdrop.addEventListener('click', closeDrawer);

  /* ---------- buttons ---------- */

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-act]');
    if (!trigger) {
      return;
    }
    var action = trigger.getAttribute('data-act');
    if (action === 'prev') {
      step(-1);
    } else if (action === 'next') {
      step(1);
    } else if (action === 'theme') {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next);
    } else if (action === 'font-up') {
      applyFont(parseFloat(store.get('font', 15.5)) + 0.5);
    } else if (action === 'font-down') {
      applyFont(parseFloat(store.get('font', 15.5)) - 0.5);
    } else if (action === 'menu') {
      toggleDrawer();
    } else if (action === 'width') {
      openWidth(!widthOpen());
    } else if (action === 'top') {
      main.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    }
  });

  if (widthRange) {
    widthRange.addEventListener('input', function () {
      applyWidth(widthRange.value, false);
    });
    widthRange.addEventListener('change', function () {
      applyWidth(widthRange.value);
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-width]'), function (button) {
    button.addEventListener('click', function () {
      applyWidth(button.getAttribute('data-width'));
      closeWidth();
    });
  });

  document.addEventListener('click', function (event) {
    if (!widthOpen()) {
      return;
    }
    if (event.target.closest('[data-width-panel]') || event.target.closest('[data-act="width"]')) {
      return;
    }
    closeWidth();
  });

  /* ---------- figures: lightbox, 1:1 inspection, byte-exact download ---------- */

  var lightbox = null;
  var lightboxImg = null;
  var lastFigureTrigger = null;

  function objectUrl(src, done) {
    if (src.indexOf('data:') !== 0) {
      done(src);
      return;
    }
    fetch(src).then(function (response) {
      return response.blob();
    }).then(function (blob) {
      done(URL.createObjectURL(blob));
    }).catch(function () {
      done(src);
    });
  }

  function ensureLightbox() {
    if (lightbox) {
      return lightbox;
    }
    lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.setAttribute('role', 'dialog');
    lightbox.setAttribute('aria-modal', 'true');
    lightbox.setAttribute('aria-label', '查看论文原图');
    lightbox.innerHTML =
      '<div class="lightbox-inner">' +
      '<div class="lightbox-bar">' +
      '<span class="lb-label"></span>' +
      '<span class="lb-meta"></span>' +
      '<button type="button" data-lb="fit">适应窗口</button>' +
      '<button type="button" data-lb="actual">1:1</button>' +
      '<button type="button" data-lb="download">下载原图</button>' +
      '<button type="button" data-lb="close">关闭（Esc）</button>' +
      '</div>' +
      '<div class="lightbox-stage"><img alt=""></div>' +
      '</div>';
    document.body.appendChild(lightbox);
    lightboxImg = lightbox.querySelector('img');
    lightbox.addEventListener('click', function (event) {
      var button = event.target.closest ? event.target.closest('[data-lb]') : null;
      if (!button) {
        if (event.target === lightbox) {
          closeLightbox();
        }
        return;
      }
      var act = button.getAttribute('data-lb');
      if (act === 'close') {
        closeLightbox();
      } else if (act === 'fit') {
        lightbox.classList.remove('actual');
        button.blur();
      } else if (act === 'actual') {
        lightbox.classList.add('actual');
        button.blur();
      } else if (act === 'download') {
        downloadFigure();
        button.blur();
      }
    });
    return lightbox;
  }

  function downloadFigure() {
    if (!lightboxImg || !lightboxImg.src) {
      return;
    }
    var name = lightboxImg.getAttribute('data-name') || 'figure';
    objectUrl(lightboxImg.src, function (href) {
      var link = document.createElement('a');
      link.href = href;
      link.download = name;
      document.body.appendChild(link);
      link.click();
      link.remove();
    });
  }

  function openLightbox(img, label) {
    if (!img || !img.src) {
      return;
    }
    ensureLightbox();
    var sha = img.getAttribute('data-sha256') || '';
    lightbox.classList.remove('actual');
    lightboxImg.src = img.src;
    lightboxImg.alt = img.getAttribute('alt') || '';
    lightboxImg.setAttribute('data-name', img.getAttribute('data-name') || 'figure');
    var bits = [];
    if (sha) {
      bits.push('sha256 ' + sha.slice(0, 12) + '…');
    }
    if (img.naturalWidth && img.naturalHeight) {
      bits.push(img.naturalWidth + '×' + img.naturalHeight + ' px');
    }
    bits.push('原始字节，未做任何处理');
    var labelEl = lightbox.querySelector('.lb-label');
    var metaEl = lightbox.querySelector('.lb-meta');
    if (labelEl) {
      labelEl.textContent = label || '原图';
    }
    if (metaEl) {
      metaEl.textContent = bits.join(' · ');
    }
    lightbox.classList.add('open');
    lastFigureTrigger = img;
  }

  function closeLightbox() {
    if (!lightbox || !lightbox.classList.contains('open')) {
      return false;
    }
    lightbox.classList.remove('open');
    lightbox.classList.remove('actual');
    lightboxImg.removeAttribute('src');
    if (lastFigureTrigger && lastFigureTrigger.focus) {
      lastFigureTrigger.focus({ preventScroll: true });
    }
    return true;
  }

  document.addEventListener('click', function (event) {
    var zoom = event.target.closest ? event.target.closest('.fig-zoom') : null;
    if (zoom) {
      event.preventDefault();
      event.stopPropagation();
      openLightbox(zoom.querySelector('img'), zoom.getAttribute('data-label'));
      return;
    }
    var raw = event.target.closest ? event.target.closest('.fig-raw[data-download]') : null;
    if (raw) {
      event.preventDefault();
      var figure = raw.closest('.fig');
      var img = figure ? figure.querySelector('img') : null;
      if (!img) {
        return;
      }
      objectUrl(img.src, function (href) {
        var link = document.createElement('a');
        link.href = href;
        link.download = raw.getAttribute('data-name') || img.getAttribute('data-name') || 'figure';
        document.body.appendChild(link);
        link.click();
        link.remove();
      });
    }
  }, true);

  /* ---------- keyboard ---------- */

  document.addEventListener('keydown', function (event) {
    var tag = (event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    if (event.key === 'Escape' && closeLightbox()) {
      event.preventDefault();
      return;
    }
    if (lightbox && lightbox.classList.contains('open')) {
      return;
    }
    if (event.key === 'ArrowRight' || event.key === 'j') {
      step(1);
      event.preventDefault();
    } else if (event.key === 'ArrowLeft' || event.key === 'k') {
      step(-1);
      event.preventDefault();
    } else if (event.key === 'Home') {
      markActive(0, true);
      goTo(state.list[0], true);
      event.preventDefault();
    } else if (event.key === 'End') {
      markActive(state.list.length - 1, true);
      goTo(state.list[state.list.length - 1], true);
      event.preventDefault();
    } else if (event.key === '/') {
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
        event.preventDefault();
      }
    } else if (event.key === '[') {
      applyWidth(clampWidth(widthNow === 'none' ? WIDTH.max : widthNow) - WIDTH.step);
      event.preventDefault();
    } else if (event.key === ']') {
      applyWidth(clampWidth(widthNow === 'none' ? WIDTH.max : widthNow) + WIDTH.step);
      event.preventDefault();
    } else if (event.key === 'Escape') {
      closeDrawer();
      closeWidth();
    }
  });

  /* ---------- anchors & deep links ---------- */

  function jumpFromHash() {
    var id = (window.location.hash || '').replace('#', '');
    if (!id) {
      return;
    }
    var target = id === 'paper-start' ? null : document.getElementById(id);
    if (!target) {
      return;
    }
    if (target.classList.contains('para')) {
      var index = state.list.indexOf(target);
      if (index !== -1) {
        markActive(index, true);
      }
      goTo(target, false);
      flash(target);
    }
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest('a[href^="#"]');
    if (!link) {
      return;
    }
    var id = link.getAttribute('href').slice(1);
    var target = document.getElementById(id);
    if (!target) {
      return;
    }
    if (target.classList.contains('para')) {
      var index = state.list.indexOf(target);
      if (index !== -1) {
        markActive(index, true);
      }
      goTo(target, true);
      flash(target);
    } else if (target.classList.contains('sec')) {
      var top = Math.max(0, cardTop(target) - 12);
      main.scrollTo({ top: top, behavior: reduceMotion ? 'auto' : 'smooth' });
    }
    closeDrawer();
  });

  /* ---------- init ---------- */

  var prefersDark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  applyTheme(store.get('theme', prefersDark ? 'dark' : 'light'));
  applyFont(store.get('font', 15.5));
  applyWidth(store.get('width', WIDTH.def), false);

  main.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', function () {
    onScroll();
  });

  markActive(0, false);
  onScroll();
  window.setTimeout(jumpFromHash, 40);
  window.addEventListener('hashchange', jumpFromHash);
})();
