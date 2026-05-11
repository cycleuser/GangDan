// ============================================
// UI Utilities
// ============================================

var _learningModules = ['question', 'guide', 'research', 'lecture', 'exam'];
var _kbSections = ['docs', 'gallery', 'wiki', 'preprint'];
var _teachingSections = ['question', 'guide', 'research', 'lecture', 'exam'];
var _learningInited = {};

// ============================================
// App State Manager — localStorage + URL hash
// ============================================

var AppState = (function() {
    var STORAGE_KEY = 'gangdan_app_state';

    function load() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (e) {
            return {};
        }
    }

    function save(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {}
    }

    function get(key, fallback) {
        var state = load();
        return state.hasOwnProperty(key) ? state[key] : fallback;
    }

    function set(key, value) {
        var state = load();
        state[key] = value;
        save(state);
    }

    function remove(key) {
        var state = load();
        delete state[key];
        save(state);
    }

    function saveNav(panel, section) {
        set('panel', panel);
        if (section) set('panelSection', section);
    }

    function getNav() {
        return {
            panel: get('panel', 'chat'),
            section: get('panelSection', '')
        };
    }

    function setHash(panel, section) {
        var hash = '#' + panel;
        if (section) hash += '-' + section;
        try {
            history.replaceState(null, '', hash);
        } catch (e) {}
    }

    function getHash() {
        var hash = (window.location.hash || '').replace('#', '');
        if (!hash) return { panel: '', section: '' };
        var parts = hash.split('-');
        return { panel: parts[0] || '', section: parts.slice(1).join('-') || '' };
    }

    return {
        load: load,
        save: save,
        get: get,
        set: set,
        remove: remove,
        saveNav: saveNav,
        getNav: getNav,
        setHash: setHash,
        getHash: getHash
    };
})();

function showPanel(name, btn) {
    document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });

    if (name === 'kb') {
        document.getElementById('panel-kb').classList.add('active');
        var tabBtn = btn || document.getElementById('tab-kb');
        if (tabBtn) tabBtn.classList.add('active');
        var savedSection = AppState.get('panelSection', 'docs');
        var sectionItem = document.querySelector('.kb-nav-item[data-section="' + savedSection + '"]') || document.querySelector('.kb-nav-item');
        if (sectionItem) switchKbSection(savedSection, sectionItem);
        AppState.saveNav('kb', savedSection);
        AppState.setHash('kb', savedSection);
        return;
    }

    if (name === 'teaching') {
        document.getElementById('panel-teaching').classList.add('active');
        var tabBtn = btn || document.getElementById('tab-teaching');
        if (tabBtn) tabBtn.classList.add('active');
        var savedSection = AppState.get('panelSection', 'question');
        var sectionItem = document.querySelector('.teaching-nav-item[data-section="' + savedSection + '"]') || document.querySelector('.teaching-nav-item');
        if (sectionItem) switchTeachingSection(savedSection, sectionItem);
        AppState.saveNav('teaching', savedSection);
        AppState.setHash('teaching', savedSection);
        return;
    }

    activatePanel(name);
    var tabBtn = btn || document.querySelector('.tab[data-panel="' + name + '"]');
    if (tabBtn) tabBtn.classList.add('active');
    AppState.saveNav(name);
    AppState.setHash(name);
}

function switchKbSection(name, btn) {
    var kbContent = document.querySelector('.kb-content');
    if (kbContent) {
        kbContent.querySelectorAll('.panel').forEach(function(p) {
            p.classList.remove('active');
        });
    }
    var panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.add('active');

    document.querySelectorAll('.kb-nav-item').forEach(function(item) {
        item.classList.remove('active');
    });
    if (btn) btn.classList.add('active');

    if (_kbSections.indexOf(name) >= 0) {
        activateLazyInit(name);
    }

    AppState.saveNav('kb', name);
    AppState.setHash('kb', name);
    
    // Refresh translations for newly shown panel
    if (typeof invalidateI18nCache === 'function') {
        setTimeout(function() {
            if (typeof invalidateI18nCache === 'function') invalidateI18nCache();
            if (typeof updateAllUIText === 'function') updateAllUIText();
        }, 100);
    }
}

function switchTeachingSection(name, btn) {
    var teachingContent = document.querySelector('.teaching-content');
    if (teachingContent) {
        teachingContent.querySelectorAll('.panel').forEach(function(p) {
            p.classList.remove('active');
        });
    }
    var panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.add('active');

    document.querySelectorAll('.teaching-nav-item').forEach(function(item) {
        item.classList.remove('active');
    });
    if (btn) btn.classList.add('active');

    activateLazyInit(name);

    AppState.saveNav('teaching', name);
    AppState.setHash('teaching', name);
    
    // Refresh translations for newly shown panel
    if (typeof invalidateI18nCache === 'function') {
        setTimeout(function() {
            if (typeof invalidateI18nCache === 'function') invalidateI18nCache();
            if (typeof updateAllUIText === 'function') updateAllUIText();
        }, 100);
    }
}

function activatePanel(name) {
    var panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.add('active');

    if (name === 'settings') {
        if (typeof onResearchProviderChange === 'function') onResearchProviderChange();
    }

    activateLazyInit(name);
}

function activateLazyInit(name) {
    if (_learningModules.indexOf(name) >= 0 || _kbSections.indexOf(name) >= 0) {
        if (!_learningInited._kbLoaded) {
            _learningInited._kbLoaded = true;
            if (typeof invalidateI18nCache === 'function') invalidateI18nCache();
            if (typeof loadSharedKbList === 'function') loadSharedKbList();
        }
        if (!_learningInited[name]) {
            _learningInited[name] = true;
            var modMap = {
                question: 'QuestionModule', guide: 'GuideModule',
                research: 'ResearchModule', lecture: 'LectureModule', exam: 'ExamModule'
            };
            var mod = window[modMap[name]];
            if (mod && typeof mod.init === 'function') mod.init();
        }
    }
}

// Toast notification
function showToast(message, type) {
    type = type || '';
    var toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(function() { toast.classList.remove('show'); }, 3000);
}

// ============================================
// Theme Manager
// ============================================

var ThemeManager = (function() {
    var STORAGE_KEY = 'gangdan-theme';
    var DEFAULT_THEME = 'dark';
    
    function init() {
        var saved = localStorage.getItem(STORAGE_KEY);
        var systemPref = getSystemPreference();
        var theme = saved || systemPref || DEFAULT_THEME;
        apply(theme, false);
        watchSystemPreference();
        
        // Apply theme immediately to prevent flash
        if (document.readyState === 'loading') {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }
    
    function getSystemPreference() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            return 'light';
        }
        return 'dark';
    }
    
    function apply(theme, save) {
        document.documentElement.setAttribute('data-theme', theme);
        if (save !== false) {
            localStorage.setItem(STORAGE_KEY, theme);
        }
        updateToggleIcon(theme);
        updateColorScheme(theme);
    }
    
    function updateColorScheme(theme) {
        document.documentElement.style.colorScheme = theme;
    }
    
    function updateToggleIcon(theme) {
        var toggle = document.getElementById('themeToggle');
        if (!toggle) return;
        
        var darkIcon = toggle.querySelector('.theme-icon-dark');
        var lightIcon = toggle.querySelector('.theme-icon-light');
        
        if (darkIcon && lightIcon) {
            darkIcon.style.display = theme === 'dark' ? 'inline' : 'none';
            lightIcon.style.display = theme === 'light' ? 'inline' : 'none';
        }
    }
    
    function toggle() {
        var current = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
        var newTheme = current === 'dark' ? 'light' : 'dark';
        apply(newTheme, true);
        
        // Show toast notification
        var themeName = newTheme === 'dark' ? (getT('dark_theme') || 'Dark Theme') : (getT('light_theme') || 'Light Theme');
        showToast(themeName, 'success');
    }
    
    function watchSystemPreference() {
        if (!window.matchMedia) return;
        
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            // Only auto-switch if user hasn't set a preference
            if (!localStorage.getItem(STORAGE_KEY)) {
                apply(e.matches ? 'dark' : 'light', false);
            }
        });
    }
    
    function getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
    }
    
    // Initialize immediately to prevent flash of wrong theme
    init();
    
    // Public API
    return {
        init: init,
        toggle: toggle,
        apply: apply,
        getCurrentTheme: getCurrentTheme
    };
})();

function restoreNavState() {
    var hashNav = AppState.getHash();
    var panel = hashNav.panel || AppState.get('panel', '');
    var section = hashNav.section || AppState.get('panelSection', '');

    if (!panel) return;

    if (panel === 'kb' || panel === 'teaching') {
        showPanel(panel);
    } else {
        var tabBtn = document.querySelector('.tab[data-panel="' + panel + '"]');
        showPanel(panel, tabBtn);
    }
}

// Handle browser back/forward via hash changes
window.addEventListener('hashchange', function() {
    var nav = AppState.getHash();
    if (nav.panel) {
        if (nav.panel === 'kb' || nav.panel === 'teaching') {
            showPanel(nav.panel);
        } else {
            var tabBtn = document.querySelector('.tab[data-panel="' + nav.panel + '"]');
            showPanel(nav.panel, tabBtn);
        }
    }
});

// Initialize theme on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    ThemeManager.init();
});

// Save state before page unload to prevent data loss
window.addEventListener('beforeunload', function() {
    if (typeof AppConfigUtil !== 'undefined' && typeof AppConfigUtil.syncChatModel === 'function') {
        AppConfigUtil.syncChatModel();
        AppConfigUtil.syncResearchModel();
    }
    if (typeof saveChatHistory === 'function') {
        saveChatHistory();
    }
});